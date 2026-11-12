#!/bin/bash
p=/home/nvidia/cph_dev/pi05/jax-sm87
cd "$p/jax" || exit 1
export http_proxy=http://127.0.0.1:17890 https_proxy=http://127.0.0.1:17890 HTTP_PROXY=http://127.0.0.1:17890 HTTPS_PROXY=http://127.0.0.1:17890 TMPDIR="$p/cache/tmp" JAX_RELEASE=1
/home/nvidia/cph_dev/pi05/envs/openpi-sm87/bin/python -u build/build.py build --wheels=jax-cuda-pjrt --cuda_compute_capabilities=sm_87 --disable_nccl --clang_path="$p/tools/clang-system-gcc-v2" --output_path="$p/wheels" --bazel_startup_options="--output_user_root=$p/cache/bazel" --bazel_options=--jobs=4 --bazel_options=--local_ram_resources=20480 --bazel_options="--repo_env=LOCAL_CUDA_PATH=$p/tools/cuda" --bazel_options="--repo_env=LOCAL_CUDNN_PATH=$p/tools/cudnn"
status=$?
printf '%s\n' "$status" > "$p/evidence/build-background.exit.tmp"
mv "$p/evidence/build-background.exit.tmp" "$p/evidence/build-background.exit"
exit "$status"
