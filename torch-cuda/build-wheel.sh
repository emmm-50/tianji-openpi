#!/usr/bin/env bash
set -euo pipefail
root=/home/nvidia/cph_dev/pi05/torch-cuda
cd "$root/source"
export PATH="$root/build-env/bin:/usr/local/cuda/bin:$PATH"
export TMPDIR="$root/tmp"
export HTTP_PROXY=http://127.0.0.1:17890 HTTPS_PROXY=http://127.0.0.1:17890
export http_proxy="$HTTP_PROXY" https_proxy="$HTTPS_PROXY"
export CUDA_HOME=/usr/local/cuda
export CC=/usr/bin/gcc CXX=/usr/bin/g++
export TORCH_CUDA_ARCH_LIST=8.7
export USE_CUDA=1 USE_CUDNN=1 USE_NVRTC=1 USE_NUMPY=1
export BUILD_TEST=0 USE_DISTRIBUTED=0 USE_NCCL=0 USE_CUSPARSELT=0 USE_CUDSS=0
export BLAS=OpenBLAS MAX_JOBS=4
export PYTORCH_BUILD_VERSION=2.7.1 PYTORCH_BUILD_NUMBER=1
"$root/build-env/bin/python" setup.py bdist_wheel --dist-dir "$root/wheels" 2>&1 | tee "$root/logs/build-wheel.log"
