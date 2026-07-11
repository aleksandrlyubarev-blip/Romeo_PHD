# Обучающий контейнер для GCP (Vertex AI Custom Job / GKE).
# Базовый образ — CUDA 12.x runtime; xtuner + Sa2VA ставятся при сборке.
#
# Сборка и публикация в Artifact Registry:
#   REGION=us-central1 PROJECT_ID=your-project
#   docker build -t ${REGION}-docker.pkg.dev/${PROJECT_ID}/ml/sa2va-pcba:latest -f ml/Dockerfile .
#   docker push   ${REGION}-docker.pkg.dev/${PROJECT_ID}/ml/sa2va-pcba:latest

FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3-pip python3.11-venv git build-essential ninja-build \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.11 /usr/bin/python3

WORKDIR /workspace

# Python-зависимости (пин делается здесь перед заморозкой образа).
COPY ml/requirements.txt /workspace/requirements.txt
RUN python3 -m pip install --upgrade pip wheel setuptools \
    && python3 -m pip install -r /workspace/requirements.txt

# Sa2VA + SAM2 из исходников.
RUN git clone --depth 1 https://github.com/bytedance/Sa2VA.git /workspace/Sa2VA \
    && python3 -m pip install -e /workspace/Sa2VA

# Код проекта.
COPY ml /workspace/ml

# Точка входа задаётся в job-спеке (см. ml/scripts/train_lora_local.sh и launch_gcp_vertex.sh).
ENTRYPOINT ["/bin/bash", "-lc"]
