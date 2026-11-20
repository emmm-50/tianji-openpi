#include <marvin_qp_controller/qp_controller_core.hpp>
#include <pinocchio/algorithm/kinematics.hpp>
#include <pinocchio/algorithm/frames.hpp>
#include <nlohmann/json.hpp>
#include <Eigen/Geometry>
#include <cmath>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

using nlohmann::json;
using marvin_qp_controller::QpControllerCore;

extern const double native_ik_collision_detection_distance = 0.15;

std::vector<double> numbers(const json& value, std::size_t count) {
  if (!value.is_array() || value.size()!=count) throw std::runtime_error("wrong array length");
  std::vector<double> result;
  for (const auto& item : value) {
    if (!item.is_number()) throw std::runtime_error("expected numeric array");
    const auto x=item.get<double>();
    if (!std::isfinite(x)) throw std::runtime_error("non-finite input");
    result.push_back(x);
  }
  return result;
}

int main(int argc, char** argv) {
  if(argc!=2) { std::cerr << "usage: native_ik /absolute/path/to/ik_tasks.yaml\n"; return 2; }
  try {
    QpControllerCore::Options o;
    o.package_path="/opt/kernelmind/apex/install/marvin_qp_controller/share/marvin_qp_controller";
    o.scene_file=NATIVE_IK_SCENE_FILE;
    o.ik_tasks_file=argv[1];
    o.collision_pairs_file="m6s_696/collision_pairs.json";
    o.velocity_limits_file="m6s_696/velocity_limits.json";
    o.dt=.002; o.posture_cost=0.;
    o.collision_detection_distance=native_ik_collision_detection_distance;
    QpControllerCore core(o); const auto& model=core.model(); pinocchio::Data data(model);
    const auto frame=model.getFrameId("right_tool");
    if(model.nq!=14 || frame>=model.nframes) throw std::runtime_error("unexpected robot model");
    bool initialized=false; std::string line;
    while(std::getline(std::cin,line)) {
      json reply;
      try {
        const auto req=json::parse(line); const auto type=req.at("type").get<std::string>();
        if(type=="init") {
          initialized=false;
          auto q=numbers(req.at("q"),14);
          for(int i=0;i<14;i++) if(q[i]<model.lowerPositionLimit[i] || q[i]>model.upperPositionLimit[i]) throw std::runtime_error("initial joint outside model limits");
          if(!core.sync_configuration_from_positions(q)) throw std::runtime_error("initial configuration rejected");
          core.anchor_tasks_to_configuration(); initialized=true;
          reply={{"ok",true},{"type","init"}};
        } else if(type=="step") {
          if(!initialized) throw std::runtime_error("init required");
          const auto p=numbers(req.at("position"),3); const auto r=numbers(req.at("quaternion_xyzw"),4);
          Eigen::Quaterniond rotation(r[3],r[0],r[1],r[2]);
          if(!std::isfinite(rotation.norm()) || rotation.norm()<1.e-8) throw std::runtime_error("invalid quaternion norm");
          rotation.normalize();
          if(req.contains("gripper_right") && (!req["gripper_right"].is_number() || !std::isfinite(req["gripper_right"].get<double>()))) throw std::runtime_error("invalid gripper");
          pinocchio::SE3 target(rotation.toRotationMatrix(),Eigen::Vector3d(p[0],p[1],p[2]));
          if(!core.set_named_task_target("right_hand",target)) throw std::runtime_error("task target rejected");
          auto result=core.step(); if(!result.ok || result.q.size()!=14) throw std::runtime_error("QP step failed");
          pinocchio::forwardKinematics(model,data,core.q()); pinocchio::updateFramePlacements(model,data);
          const auto& actual=data.oMf[frame];
          std::vector<double> right(result.q.begin()+7,result.q.end());
          reply={{"ok",true},{"jointcmd_right",right},{"position_error_m",(target.translation()-actual.translation()).norm()},{"rotation_error_rad",Eigen::AngleAxisd(target.rotation().transpose()*actual.rotation()).angle()}};
          if(req.contains("gripper_right")) reply["gripper_right"]=req["gripper_right"];
        } else throw std::runtime_error("unknown type");
      } catch(const std::exception& e) { reply={{"ok",false},{"error",e.what()}}; }
      std::cout<<reply.dump()<<std::endl;
    }
  } catch(const std::exception& e) { std::cerr<<e.what()<<std::endl; return 1; }
}
