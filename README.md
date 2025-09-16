## GPUnix Agent

Интеллектуальный агент для подключения к GPUnix

### Платформа
- Ubuntu 24.04 LTS

### Предварительная установка (Ubuntu 24.04)
```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip
```

### Установка Docker (Ubuntu 24.04)

Рекомендуемый способ — через официальный репозиторий Docker.

1) Удалить старые пакеты (если были):
```bash
sudo apt remove -y docker docker-engine docker.io containerd runc || true
```

2) Зависимости и ключ репозитория Docker:
```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
```

3) Подключить репозиторий Docker и установить пакеты:
```bash
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release; echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
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
git clone https://github.com/GPUnix/agent.git
```

2. Переход в директорию проекта
```bash
cd agent
```

3. Создание виртуального окружения
```bash
python3 -m venv .venv
```

4. Активация виртуального окружения
```bash
source .venv/bin/activate
```

5. Установка зависимостей
```bash
pip install -r requirements.txt
```

6. Запуск агента в фоне через nohup
```bash
nohup python3 agent.py <YOUR_SECRET_KEY> > agent.log 2>&1 &
```

Проверка логов:
```bash
tail -f agent.log
```

Остановка процесса (пример):
```bash
pkill -f "python3 agent.py"
```

---
Репозиторий: https://github.com/Machine-learning-systems/agent