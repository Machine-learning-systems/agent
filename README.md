# GpuGo Agent

Интеллектуальный агент для подключения к GpuGo


# Требования
- Ubuntu 22.04 LTS или 24.04 LTS
- Широкополосный интернет
- NVIDIA GPU с установленными драйверами

## Установка зависимостей

### Установка Python 

```bash
sudo apt update
sudo apt install -y git
wget -qO- https://astral.sh/uv/install.sh | sh
```

### Установка Docker

Рекомендуемый способ — через официальный репозиторий Docker.
https://docs.docker.com/engine/install/ubuntu (здесь можно ознакомиться с инструкцией подробнее)

1) Удалить старые пакеты (если были):
```bash
for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do sudo apt-get remove $pkg; done
```

2) Установка зависимостей:
```bash
# Add Docker's official GPG key:
sudo apt-get update
sudo apt-get install ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Add the repository to Apt sources:
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
```

3) Установка Docker Engine:
```bash
sudo apt-get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

4) Запуск и доступ без sudo:
```bash
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
newgrp docker
```

5) Проверка:
```bash
docker --version
docker run --rm hello-world
```

Если Вы получили вывод "Hello from Docker! ...", значит установка прошла успешно.

### NVIDIA Cuda Toolkit

Требуется перейти по ссылке и выбрать подходящие параметры для скачивания.

https://developer.nvidia.com/cuda-downloads

Operating System: Linux
Architecture: x86_64
Distribution: Ubuntu
Version: 22.04 или 24.04
Installer Type: deb (local)


### NVIDIA Container Toolkit

Примечание: на Ubuntu 24.04 официальный список NVIDIA для libnvidia-container может отсутствовать. Используйте список для Ubuntu 22.04 (jammy) — он совместим с 24.04.
```bash
# 1) Ключ
sudo apt update
sudo apt install -y ca-certificates curl gnupg
sudo install -m 0755 -d /usr/share/keyrings
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit.gpg

# 2) Репозиторий (jammy, совместим с 24.04)
distribution=ubuntu22.04
curl -fsSL https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# 3) Установка и настройка
sudo apt update
sudo apt install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker || true
sudo systemctl restart docker
```
Если `nvidia-ctk` недоступен, добавьте runtime вручную:
```bash
sudo tee /etc/docker/daemon.json >/dev/null <<'JSON'
{
  "runtimes": {
    "nvidia": {
      "path": "nvidia-container-runtime",
      "runtimeArgs": []
    }
  }
}
JSON
sudo systemctl restart docker
```
Установка драйверов NVIDIA (если не установлены):
```bash
sudo ubuntu-drivers autoinstall
sudo reboot
```
Проверка GPU в контейнере:
```bash
# Современный способ
docker run --rm --gpus all nvidia/cuda:12.6.2-base-ubuntu24.04 nvidia-smi

# Способ, совместимый с --runtime=nvidia
docker run --rm --runtime=nvidia nvidia/cuda:12.6.2-base-ubuntu24.04 nvidia-smi

# Если 24.04 тег недоступен, используйте 22.04
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

### Быстрый старт (Ubuntu 24.04)

1. Клонирование репозитория
```bash
git clone https://github.com/Machine-learning-systems/agent.git
```

2. Переход в директорию проекта
```bash
cd agent
```

3. Запуск (должен быть установлен uv из шага "Установка зависимостей > Установка Python")
```bash
uv run agent.py <YOUR_SECRET_KEY>
```

6. Запуск агента в фоне через nohup
```bash
nohup uv run agent.py <YOUR_SECRET_KEY> > agent.log 2>&1 &
```

Проверка логов:
```bash
tail -f agent.log
```

---
Репозиторий: https://github.com/Machine-learning-systems/agent