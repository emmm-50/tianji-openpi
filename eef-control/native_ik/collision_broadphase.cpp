#include <pinocchio/multibody/geometry.hpp>
#include <coal/distance.h>
#include <coal/BVH/BVH_model.h>
#include <coal/shape/geometric_shapes.h>
#include <coal/internal/traversal_node_setup.h>
#include <coal/internal/traversal_recurse.h>
#include <algorithm>
#include <cmath>
#include <limits>
#include <unordered_map>
#include <unordered_set>
#include <vector>

// Linked only into this offline adapter. The vendor core calls the wrapped
// function after clearing the result and only uses witnesses within its
// configured collision detection distance.
extern const double native_ik_collision_detection_distance;
using Distance = coal::ComputeDistance;
using Transform = coal::Transform3s;
using Request = coal::DistanceRequest;
using Result = coal::DistanceResult;
extern "C" double __real__ZNK4coal15ComputeDistanceclERKNS_11Transform3sES3_RKNS_15DistanceRequestERNS_14DistanceResultE(const Distance*, const Transform&, const Transform&, const Request&, Result&);

namespace {
struct ExactResult {
  Transform first, second;
  Request request;
  Result result;
  double value;
  const coal::CollisionGeometry *first_geometry, *second_geometry;
};
std::unordered_set<coal::CollisionGeometry*> initialized;
std::unordered_map<const Distance*, ExactResult> previous;

bool world_box(coal::CollisionGeometry* geometry, const Transform& transform,
               Eigen::Vector3d& center, Eigen::Vector3d& extent) {
  if (initialized.insert(geometry).second) geometry->computeLocalAABB();
  const auto& box = geometry->aabb_local;
  const Eigen::Vector3d local_center = (box.min_ + box.max_) * 0.5;
  const Eigen::Vector3d local_extent = (box.max_ - box.min_) * 0.5;
  center = transform.getRotation() * local_center + transform.getTranslation();
  extent = transform.getRotation().cwiseAbs() * local_extent;
  return center.allFinite() && extent.allFinite() && (local_extent.array() >= 0).all();
}
bool same(const Transform& a, const Transform& b) {
  return (a.getRotation().array() == b.getRotation().array()).all() &&
         (a.getTranslation().array() == b.getTranslation().array()).all();
}
using Mesh = coal::BVHModel<coal::OBBRSS>;
using MeshNode = coal::MeshShapeDistanceTraversalNodeOBBRSS<coal::Capsule>;
struct CapsuleBound {
  Eigen::Vector3d center, axis;
  double upper = 0.;
  bool mesh_first = false;
};

// The OBB encloses every triangle below the node. A sphere around it gives a
// cheap conservative lower bound against the capsule segment and radius.
struct SphereNode : MeshNode {
  Eigen::Vector3d start, segment;
  double segment_squared, radius, vertex_upper;
  double point_distance(const Eigen::Vector3d& point) const {
    const double u = segment_squared > 0
        ? std::clamp((point - start).dot(segment) / segment_squared, 0., 1.) : 0.;
    return (point - (start + u * segment)).norm();
  }
  coal::CoalScalar BVDistanceLowerBound(unsigned int b1, unsigned int b2) const override {
    const auto& obb = model1->getBV(b1).bv.obb;
    const double lower = point_distance(obb.To) - obb.extent.norm() - radius;
    const double margin = 1.e-9 + 1.e-12 * (std::abs(lower) + vertex_upper);
    if (lower > 0 && lower > vertex_upper + margin) return lower - margin;
    return MeshNode::BVDistanceLowerBound(b1, b2);
  }
};

bool sphere_query(const Mesh* mesh, const coal::Capsule* capsule,
                  const Transform& mesh_pose, const Transform& capsule_pose,
                  const Request& request, const CapsuleBound& bound, Result& result) {
  if (!bound.mesh_first || !mesh || !capsule || !std::isfinite(bound.upper) || bound.upper <= 0 ||
      mesh->build_state != coal::BVH_BUILD_STATE_PROCESSED ||
      mesh->getModelType() != coal::BVH_MODEL_TRIANGLES || mesh->getNumBVs() == 0 ||
      !mesh->tri_indices || capsule->getSweptSphereRadius() != 0 ||
      capsule->radius < 0 || capsule->halfLength < 0 || request.abs_err != 0 || request.rel_err != 0 ||
      !mesh_pose.getRotation().allFinite() || !mesh_pose.getTranslation().allFinite() ||
      !capsule_pose.getRotation().allFinite() || !capsule_pose.getTranslation().allFinite()) return false;
  SphereNode node;
  const Eigen::Vector3d half_axis = bound.axis * capsule->halfLength;
  node.start = bound.center - half_axis;
  node.segment = 2 * half_axis;
  node.segment_squared = node.segment.squaredNorm();
  node.radius = capsule->radius;
  node.vertex_upper = bound.upper;
  coal::GJKSolver solver(request);
  Result candidate;
  if (!coal::initialize(static_cast<MeshNode&>(node), *mesh, mesh_pose, *capsule,
                        capsule_pose, &solver, request, candidate)) return false;
  node.preprocess();
  coal::distanceRecurse(&node, 0, 0, nullptr);
  node.postprocess();
  if (!std::isfinite(candidate.min_distance) || candidate.min_distance <= 1.e-9) return false;
  candidate.cached_gjk_guess = solver.cached_guess;
  candidate.cached_support_func_guess = solver.support_func_cached_guess;
  result = candidate;
  request.updateGuess(result);
  return true;
}

// A mesh vertex is a surface point only if some triangle references it.
// Mesh data is fixed for the lifetime of the geometry in this adapter.
bool all_vertices_referenced(const coal::BVHModelBase* mesh) {
  static std::unordered_map<const coal::BVHModelBase*, bool> cache;
  auto found = cache.find(mesh);
  if (found != cache.end()) return found->second;
  if (!mesh->vertices || !mesh->tri_indices || mesh->tri_indices->empty()) return false;
  std::vector<bool> used(mesh->vertices->size(), false);
  for (const auto& triangle : *mesh->tri_indices) {
    for (int i = 0; i < 3; ++i) {
      const auto index = triangle[i];
      if (index >= used.size()) return false;
      used[index] = true;
    }
  }
  const bool all_used = std::all_of(used.begin(), used.end(), [](bool v) { return v; });
  cache.emplace(mesh, all_used);
  return all_used;
}

// A candidate axis may be approximate; the projection includes every mesh
// vertex and the entire capsule, so a positive gap is a geometric lower bound.
double mesh_capsule_gap(const coal::CollisionGeometry* first_geometry, const Transform& first,
                        const coal::CollisionGeometry* second_geometry, const Transform& second,
                        CapsuleBound& bound) {
  auto* first_mesh = dynamic_cast<const coal::BVHModelBase*>(first_geometry);
  auto* second_mesh = dynamic_cast<const coal::BVHModelBase*>(second_geometry);
  auto* first_capsule = dynamic_cast<const coal::Capsule*>(first_geometry);
  auto* second_capsule = dynamic_cast<const coal::Capsule*>(second_geometry);
  const bool mesh_is_first = first_mesh && second_capsule;
  const auto* mesh = mesh_is_first ? first_mesh : (second_mesh && first_capsule ? second_mesh : nullptr);
  const auto* capsule = mesh_is_first ? second_capsule : (mesh ? first_capsule : nullptr);
  if (!mesh || !mesh->vertices || mesh->vertices->empty()) return 0.;

  const auto& mesh_pose = mesh_is_first ? first : second;
  const auto& capsule_pose = mesh_is_first ? second : first;
  const Eigen::Vector3d capsule_center = mesh_pose.getRotation().transpose() *
      (capsule_pose.getTranslation() - mesh_pose.getTranslation());
  const Eigen::Vector3d capsule_axis = mesh_pose.getRotation().transpose() * capsule_pose.getRotation().col(2);
  double nearest_squared = std::numeric_limits<double>::max();
  Eigen::Vector3d separation_axis = Eigen::Vector3d::Zero();
  for (const auto& vertex : *mesh->vertices) {
    const double axial = std::max(-capsule->halfLength,
        std::min(capsule->halfLength, capsule_axis.dot(vertex - capsule_center)));
    const Eigen::Vector3d delta = vertex - (capsule_center + capsule_axis * axial);
    const double squared = delta.squaredNorm();
    if (squared < nearest_squared) {
      nearest_squared = squared;
      separation_axis = delta;
    }
  }
  if (!std::isfinite(nearest_squared) || nearest_squared <= 1.e-20) return 0.;
  bound.center = capsule_center;
  bound.axis = capsule_axis;
  bound.mesh_first = mesh_is_first;
  if (mesh_is_first && all_vertices_referenced(mesh)) {
    bound.upper = std::sqrt(nearest_squared) - capsule->radius;
  } else if (mesh_is_first && mesh->tri_indices && !mesh->tri_indices->empty()) {
    // An isolated vertex is not a surface point. Use the first actual
    // triangle's vertices for a valid (possibly looser) upper bound instead.
    const auto& triangle = (*mesh->tri_indices)[0];
    double nearest_surface_vertex = std::numeric_limits<double>::infinity();
    for (int i = 0; i < 3; ++i) {
      if (triangle[i] >= mesh->vertices->size()) {
        nearest_surface_vertex = std::numeric_limits<double>::infinity();
        break;
      }
      const auto& vertex = (*mesh->vertices)[triangle[i]];
      const double axial = std::clamp(capsule_axis.dot(vertex - capsule_center),
                                      -capsule->halfLength, capsule->halfLength);
      nearest_surface_vertex = std::min(nearest_surface_vertex,
          (vertex - (capsule_center + capsule_axis * axial)).norm());
    }
    if (std::isfinite(nearest_surface_vertex))
      bound.upper = nearest_surface_vertex - capsule->radius;
  }
  separation_axis.normalize();
  double mesh_min = std::numeric_limits<double>::max();
  double mesh_max = -mesh_min;
  for (const auto& vertex : *mesh->vertices) {
    const double projection = separation_axis.dot(vertex);
    mesh_min = std::min(mesh_min, projection);
    mesh_max = std::max(mesh_max, projection);
  }
  const double capsule_mid = separation_axis.dot(capsule_center);
  const double capsule_extent = capsule->halfLength * std::abs(separation_axis.dot(capsule_axis)) +
      capsule->radius + capsule->getSweptSphereRadius();
  return std::max(capsule_mid - capsule_extent - mesh_max,
                  mesh_min - (capsule_mid + capsule_extent));
}

}

extern "C" double __wrap__ZNK4coal15ComputeDistanceclERKNS_11Transform3sES3_RKNS_15DistanceRequestERNS_14DistanceResultE(
    const Distance* distance, const Transform& first, const Transform& second,
    const Request& request, Result& result) {
  auto exact = [&] { return __real__ZNK4coal15ComputeDistanceclERKNS_11Transform3sES3_RKNS_15DistanceRequestERNS_14DistanceResultE(distance, first, second, request, result); };
  auto* pair = dynamic_cast<const pinocchio::ComputeDistance*>(distance);
  if (!pair || request.enable_timings || request.gjk_initial_guess != coal::GJKInitialGuess::DefaultGuess ||
      result.min_distance != std::numeric_limits<double>::max()) return exact();
  auto* g1 = pair->getGeometryObject1().geometry.get();
  auto* g2 = pair->getGeometryObject2().geometry.get();
  Eigen::Vector3d c1, e1, c2, e2;
  const bool boxes_valid = world_box(g1, first, c1, e1) && world_box(g2, second, c2, e2);
  if (boxes_valid) {
    const double lower = ((c1 - c2).cwiseAbs() - e1 - e2).cwiseMax(0.).norm();
    // Roundoff margin keeps all threshold-adjacent pairs on the exact path.
    if (lower > native_ik_collision_detection_distance + 1.e-9) {
      result.min_distance = lower;
      return lower;
    }
  }
  auto old = previous.find(distance);
  if (old != previous.end() && old->second.first_geometry == g1 && old->second.second_geometry == g2 &&
      same(first, old->second.first) && same(second, old->second.second) && request == old->second.request) {
    result = old->second.result;
    request.updateGuess(result);
    return old->second.value;
  }
  CapsuleBound bound;
  const double gap = mesh_capsule_gap(g1, first, g2, second, bound);
  if (gap > native_ik_collision_detection_distance + 1.e-9) {
    result.min_distance = gap;
    return gap;
  }
  const bool accelerated = sphere_query(dynamic_cast<const Mesh*>(g1),
      dynamic_cast<const coal::Capsule*>(g2), first, second, request, bound, result);
  const double value = accelerated ? result.min_distance : exact();
  previous.insert_or_assign(distance, ExactResult{first, second, request, result, value, g1, g2});
  return value;
}
