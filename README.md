# GpuGo Agent

Агент для подключения GPU-машин к платформе GpuGo. Управляет Docker-контейнерами, собирает информацию о железе, общается с API сервером.

Версия 2.0 — полностью переписанная архитектура с CLI, TUI dashboard и нормальным логированием.

## Что нового в v2.0

- Модульная архитектура вместо монолита
- CLI через `gpugo` команду
- TUI dashboard для мониторинга (Textual)
- Логирование через loguru вместо print
- Pydantic модели для валидации
- Поддержка всех сервисов: SSH, Jupyter, code-server, ComfyUI

## Требования

- Ubuntu 22.04 / 24.04 LTS
- Python 3.12+
- Docker с NVIDIA Container Toolkit
- NVIDIA GPU с драйверами

## Быстрый старт

```bash
git clone https://github.com/Machine-learning-systems/agent.git
cd agent
uv sync
uv run gpugo run <YOUR_SECRET_KEY>
```

Или через systemd (рекомендуется для production):

```bash
chmod +x agent-manager.sh
./agent-manager.sh install <YOUR_SECRET_KEY>
```

## CLI команды

После установки доступна команда `gpugo`:

```bash
# Запуск агента
gpugo run <SECRET_KEY>
gpugo run <SECRET_KEY> --debug          # с debug логами
gpugo run <SECRET_KEY> --log agent.log  # логи в файл

# TUI dashboard — удобно смотреть что происходит
gpugo dashboard

# Управление контейнерами
gpugo containers list                   # список
gpugo containers stop task_123          # остановить конкретный
gpugo containers logs task_123          # логи контейнера

# Статус
gpugo status
gpugo version
```

## TUI Dashboard

Запускается через `gpugo dashboard`. Показывает:

- Статус агента и uptime
- Загрузку CPU/RAM
- GPU мониторинг (температура, память, загрузка)
- Список контейнеров с их статусами
- Логи в реальном времени

Горячие клавиши:
- `r` — обновить
- `s` — остановить выбранный контейнер
- `d` — удалить контейнер
- `l` — показать логи контейнера
- `q` — выход

## Конфигурация

Настройки лежат в `config.yaml`:

```yaml
image:
  prefix: jsg
  default: jupyter

ports:
  ssh_base: 42200
  jupyter_base: 42800
  code_server_base: 48000
  comfyui_base: 49000

container:
  shm_size: 16g
  ulimit_stack: 67108864
  restart_policy: unless-stopped

nvidia:
  capabilities: compute,utility
  visible_devices: all

api:
  base_url: https://api.gpugo.ru
  heartbeat_interval: 300
```

## Структура проекта

```
agent/
├── core/
│   ├── api/           # HTTP клиент для API
│   ├── cli/           # CLI и TUI
│   │   ├── main.py    # точка входа
│   │   └── tui/       # Textual dashboard
│   ├── models/        # Pydantic модели
│   ├── services/      # Бизнес-логика
│   │   ├── agent.py   # главный класс
│   │   ├── container.py
│   │   ├── hardware.py
│   │   └── handlers.py
│   └── utils/         # логирование и прочее
├── config.yaml
├── pyproject.toml
└── agent-manager.sh   # systemd wrapper
```

## Управление через systemd

```bash
./agent-manager.sh install <SECRET_KEY>  # установить и запустить
./agent-manager.sh start                  # запустить
./agent-manager.sh stop                   # остановить
./agent-manager.sh restart                # перезапустить
./agent-manager.sh status                 # статус
./agent-manager.sh logs                   # логи (follow)
./agent-manager.sh uninstall              # удалить службу
```

---

## Установка зависимостей (если с нуля)

### Python и uv

```bash
sudo apt update && sudo apt install -y git curl
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Docker

Подробно: https://docs.docker.com/engine/install/ubuntu

Коротко:

```bash
# удалить старое если есть
for pkg in docker.io docker-doc docker-compose podman-docker containerd runc; do
  sudo apt-get remove -y $pkg 2>/dev/null
done

# добавить репозиторий
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# установить
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# настроить
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
newgrp docker

# проверить
docker run --rm hello-world
```

### NVIDIA Container Toolkit

Нужен для запуска контейнеров с GPU.

```bash
# ключ
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit.gpg

# репозиторий (ubuntu22.04 работает и на 24.04)
distribution=ubuntu22.04
curl -fsSL https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# установить
sudo apt update
sudo apt install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# проверить
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

Если `nvidia-ctk` не работает, можно вручную:

```bash
sudo tee /etc/docker/daemon.json <<EOF
{
  "runtimes": {
    "nvidia": {
      "path": "nvidia-container-runtime",
      "runtimeArgs": []
    }
  }
}
EOF
sudo systemctl restart docker
```

### Драйверы NVIDIA

Если ещё не установлены:

```bash
sudo ubuntu-drivers autoinstall
sudo reboot
```

---

## Разработка

```bash
# установить зависимости
uv sync

# запустить линтер
ruff check core/

# форматирование
ruff format core/

# запустить агента локально
uv run gpugo run <SECRET_KEY> --debug
```

## Лицензия

MIT

---

Репозиторий: https://github.com/Machine-learning-systems/agent
