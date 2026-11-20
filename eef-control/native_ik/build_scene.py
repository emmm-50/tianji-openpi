#!/usr/bin/python3
"""Generate the APEX-oriented offline scene from the shared Marvin URDF."""
import copy
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

urdf_path, system_scene_path, output_path = map(Path, sys.argv[1:4])
robot = ET.parse(urdf_path).getroot()
system_scene = ET.parse(system_scene_path).getroot()
links = {link.get('name'): link for link in robot.findall('link')}
children = {}
for joint in robot.findall('joint'):
    parent_name = joint.find('parent').get('link')
    children.setdefault(parent_name, []).append(joint)

# The solver expects the seven left joints before the seven right joints.
def arm_order(joint):
    child_name = joint.find('child').get('link')
    return {'Base_L': 0, 'Base_R': 1}.get(child_name, 2)

children['base_link'].sort(key=arm_order)
scene = ET.Element('mujoco', model='marvin_shared_95mm')
ET.SubElement(scene, 'compiler', angle='radian')
assets = ET.SubElement(scene, 'asset')
world = ET.SubElement(scene, 'worldbody')
world_rotation = Rotation.from_euler('z', np.pi / 2)


def format_values(values):
    return ' '.join(format(float(value), '.17g') for value in values)


def read_origin(element):
    origin = element.find('origin')
    if origin is None:
        return np.zeros(3), Rotation.identity()
    position = np.fromstring(origin.get('xyz', '0 0 0'), sep=' ')
    angles = np.fromstring(origin.get('rpy', '0 0 0'), sep=' ')
    return position, Rotation.from_euler('xyz', angles)


def format_quaternion(rotation):
    x, y, z, w = rotation.as_quat()
    return format_values([w, x, y, z])


def add_inertial(body, link, name):
    inertial = link.find('inertial')
    if inertial is None:
        return
    position, rotation = read_origin(inertial)
    inertia = inertial.find('inertia').attrib
    tensor = np.array([
        [float(inertia['ixx']), float(inertia['ixy']), float(inertia['ixz'])],
        [float(inertia['ixy']), float(inertia['iyy']), float(inertia['iyz'])],
        [float(inertia['ixz']), float(inertia['iyz']), float(inertia['izz'])],
    ])
    if name == 'base_link':
        position = world_rotation.apply(position)
        rotation = world_rotation * rotation
    matrix = rotation.as_matrix()
    tensor = matrix @ tensor @ matrix.T
    full_inertia = [tensor[0, 0], tensor[1, 1], tensor[2, 2],
                    tensor[0, 1], tensor[0, 2], tensor[1, 2]]
    ET.SubElement(body, 'inertial', pos=format_values(position),
                  mass=inertial.find('mass').get('value'),
                  fullinertia=format_values(full_inertia))


def add_joint(body, joint):
    if joint is None or joint.get('type') != 'revolute':
        return
    limit = joint.find('limit')
    effort = float(limit.get('effort'))
    ET.SubElement(body, 'joint', name=joint.get('name'), type='hinge',
                  pos='0 0 0', axis=joint.find('axis').get('xyz'),
                  range=limit.get('lower') + ' ' + limit.get('upper'),
                  actuatorfrcrange=format_values([-effort, effort]))


def add_collision(body, link, name):
    if name in ('base_link', 'Link5_L', 'Link5_R'):
        capsule_name = name + '_collision'
        capsule = copy.deepcopy(system_scene.find(
            ".//geom[@name='" + capsule_name + "']"))
        capsule.attrib.pop('class')
        capsule.set('type', 'capsule')
        capsule.set('contype', '1')
        capsule.set('conaffinity', '1')
        body.append(capsule)
        return
    collision = link.find('collision')
    if collision is None:
        return
    mesh = collision.find('geometry/mesh')
    if mesh is None:
        return
    mesh_name = name + '_collision'
    filename = mesh.get('filename').split('/meshes/', 1)[1]
    mesh_path = (urdf_path.parent.parent / 'meshes' / filename).resolve()
    ET.SubElement(assets, 'mesh', name=mesh_name, file=str(mesh_path),
                  scale=mesh.get('scale', '1 1 1'))
    position, rotation = read_origin(collision)
    ET.SubElement(body, 'geom', name=mesh_name, type='mesh', mesh=mesh_name,
                  contype='1', conaffinity='1', pos=format_values(position),
                  quat=format_quaternion(rotation))


def add_body(parent, name, position, rotation, joint=None):
    body = ET.SubElement(parent, 'body', name=name, pos=format_values(position),
                         quat=format_quaternion(rotation))
    link = links[name]
    add_inertial(body, link, name)
    add_joint(body, joint)
    add_collision(body, link, name)
    for child_joint in children.get(name, []):
        child_position, child_rotation = read_origin(child_joint)
        if name == 'base_link':
            child_position = world_rotation.apply(child_position)
            child_rotation = world_rotation * child_rotation
        child_name = child_joint.find('child').get('link')
        add_body(body, child_name, child_position, child_rotation, child_joint)


add_body(world, 'base_link', np.zeros(3), Rotation.identity())
scene.append(copy.deepcopy(system_scene.find('keyframe')))
ET.indent(scene, space='  ')
ET.ElementTree(scene).write(output_path, encoding='utf-8', xml_declaration=True)
