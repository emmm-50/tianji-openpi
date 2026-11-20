"""Run upstream OpenPI training with the Tianji right-arm dataset."""
import dataclasses
from pathlib import Path
from typing import Literal

import numpy as np
import tqdm
import tyro

from openpi import transforms
from openpi.models.pi0_config import Pi0Config
from openpi.policies.libero_policy import _parse_image
from openpi.shared import normalize
from openpi.training import config, weight_loaders

PROJECT = Path(__file__).resolve().parents[1]
REPO_ID = "tianji/right_orange"


class RightArmInputs(transforms.DataTransformFn):
    def __call__(self, data):
        head = _parse_image(data["head_rgb"])
        wrist = _parse_image(data["wrist_rgb"])
        return {
            "state": np.asarray(data["state"]),
            "actions": np.asarray(data["actions"]),
            "prompt": data["prompt"],
            "image": {
                "base_0_rgb": head,
                "left_wrist_0_rgb": np.zeros_like(wrist),
                "right_wrist_0_rgb": wrist,
            },
            "image_mask": {
                "base_0_rgb": np.True_,
                "left_wrist_0_rgb": np.False_,
                "right_wrist_0_rgb": np.True_,
            },
        }


def make_config(base_params: Path) -> config.TrainConfig:
    model = Pi0Config(
        pi05=True,
        paligemma_variant="gemma_2b_lora",
        action_expert_variant="gemma_300m_lora",
    )
    return config.TrainConfig(
        name="pi05_tianji_right_lora",
        model=model,
        freeze_filter=model.get_freeze_filter(),
        ema_decay=None,
        data=config.SimpleDataConfig(
            repo_id=REPO_ID,
            base_config=config.DataConfig(prompt_from_task=True),
            data_transforms=lambda _: transforms.Group(inputs=[RightArmInputs()]),
        ),
        weight_loader=weight_loaders.CheckpointWeightLoader(str(base_params.resolve())),
        assets_base_dir=str(PROJECT / "cache/tianji-lora/assets"),
        checkpoint_base_dir=str(PROJECT / "cache/tianji-lora/checkpoints"),
        num_workers=0,
        wandb_enabled=False,
    )


def main(
    stage: Literal["stats", "train"],
    *,
    base_params: Path = PROJECT / "weights/pi05_base/params",
    exp_name: str = "smoke",
    batch_size: int = 1,
    steps: int = 1,
    resume: bool = False,
):
    cfg = dataclasses.replace(
        make_config(base_params),
        exp_name=exp_name,
        batch_size=batch_size,
        num_train_steps=steps,
        resume=resume,
    )
    if stage == "train":
        if not base_params.is_dir():
            raise FileNotFoundError(base_params)
        from scripts import train

        train.main(cfg)
        return

    from scripts import compute_norm_stats

    data = cfg.data.create(cfg.assets_dirs, cfg.model)
    loader, batches = compute_norm_stats.create_torch_dataloader(
        data, cfg.model.action_horizon, cfg.batch_size, cfg.model, cfg.num_workers
    )
    stats = {key: normalize.RunningStats() for key in ("state", "actions")}
    for batch in tqdm.tqdm(loader, total=batches):
        for key, stat in stats.items():
            stat.update(np.asarray(batch[key]))
    normalize.save(cfg.assets_dirs / REPO_ID, {key: stat.get_statistics() for key, stat in stats.items()})


if __name__ == "__main__":
    tyro.cli(main)
