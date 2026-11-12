from pathlib import Path
import tempfile
import numpy as np
from replay import load_observation, example_action
from openpi.models.model import ModelType
from openpi.policies.droid_policy import DroidInputs

with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / "frame.npz"
    ext = np.broadcast_to(np.array([17, 23, 29], np.uint8), (120, 240, 3)).copy()
    wrist = np.full((224, 224, 3), 31, np.uint8)
    np.savez(path, exterior_rgb=ext, wrist_rgb=wrist, joint_position=np.arange(7.),
             gripper_position=np.array([0.25]), prompt="test", metadata_json="{\"kind\":\"synthetic\"}")
    obs, metadata = load_observation(path)
    assert metadata["kind"] == "synthetic"
    out = DroidInputs(ModelType.PI05)(obs)
    np.testing.assert_array_equal(out["state"], [0, 1, 2, 3, 4, 5, 6, .25])
    np.testing.assert_array_equal(out["image"]["base_0_rgb"], ext)
    np.testing.assert_array_equal(out["image"]["left_wrist_0_rgb"], wrist)
    assert bool(out["image_mask"]["base_0_rgb"]) and bool(out["image_mask"]["left_wrist_0_rgb"])
    assert not bool(out["image_mask"]["right_wrist_0_rgb"])
test_actions = np.array([[2., -2., 0., 0., 0., 0., 0., 0.5], [0., 0., 0., 0., 0., 0., 0., 0.5001]])
np.testing.assert_array_equal(example_action(test_actions)[:, -1], [0., 1.])
np.testing.assert_array_equal(example_action(test_actions)[0, :2], [1., -1.])
print("synthetic observation and action semantics: PASS")
