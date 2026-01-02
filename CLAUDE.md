# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

GpuGo Agent v2.0 — агент для подключения GPU-машин к платформе GpuGo. Управляет Docker-контейнерами, собирает информацию о железе, общается с API.

## Commands

### Development
```bash
uv run gpugo run <SECRET_KEY>           # запуск агента
uv run gpugo run <SECRET_KEY> --debug   # с debug логами
uv run gpugo dashboard                   # TUI dashboard
uv run gpugo containers list            # список контейнеров
uv run gpugo status                     # статус агента
```

### Production (Systemd)
```bash
./agent-manager.sh install <SECRET_KEY>  # установить и запустить
./agent-manager.sh start|stop|restart    # управление
./agent-manager.sh logs                  # логи
./agent-manager.sh uninstall             # удалить
```

### Linting
```bash
ruff check core/       # проверка
ruff check --fix core/ # автофикс
ruff format core/      # форматирование
```

## Architecture (v2.0)

```
core/
├── api/
│   └── client.py         # APIClient (httpx)
├── cli/
│   ├── main.py           # Typer CLI entry point
│   └── tui/
│       ├── app.py        # Textual dashboard
│       └── widgets/      # Status, GPU, Containers
├── models/
│   ├── config.py         # Config, AgentSettings (Pydantic)
│   ├── task.py           # Task, TaskResult, ResourceAllocation
│   └── hardware.py       # CPUInfo, GPUInfo, SystemInfo
├── services/
│   ├── agent.py          # Agent class — main orchestrator
│   ├── container.py      # ContainerManager (Docker CLI)
│   ├── handlers.py       # TaskHandler pattern
│   └── hardware.py       # HardwareCollector
└── utils/
    └── logging.py        # loguru setup
```

### Core Components

- **core/services/agent.py** — главный класс `Agent`. Инициализация, heartbeat loop, обработка задач. Сохраняет `agent_id` в `.agent_id`.

- **core/api/client.py** — `APIClient` на httpx:
  - `confirm_agent()` — регистрация
  - `send_init_data()` — отправка информации о железе
  - `poll_for_tasks()` — long-polling задач (отдельный thread)
  - `send_task_status()` — результат выполнения
  - `send_heartbeat()` — heartbeat каждые 5 минут

- **core/services/container.py** — `ContainerManager` работает с Docker CLI:
  - Создание контейнеров с `--gpus` флагом
  - Port mapping (SSH:22, Jupyter:8888, code-server:8080, ComfyUI:9000)
  - Resource limits: CPU pinning, memory, storage, shm-size
  - Service toggling через env vars

- **core/services/hardware.py** — `HardwareCollector`:
  - CPU/GPU/RAM/Disk detection
  - nvidia-smi для GPU метрик
  - IP и геолокация

- **core/services/handlers.py** — TaskHandler pattern:
  - `StartHandler`, `StopHandler`, `RestartHandler`
  - `TaskHandlerRegistry` для dispatch по operation

### Task Flow

1. Agent polling `/v1/agents/{agent_id}/tasks/pull`
2. Task содержит `task_data` (image, resources) и `container_info` (credentials, ports)
3. Handler создает/останавливает контейнер
4. Результат отправляется в `/v1/agents/{agent_id}/tasks/{task_id}/status`

### Configuration

Файл `config.yaml`:
- `image.prefix` — префикс образов (jsg)
- `ports.*_base` — базовые порты для сервисов
- `container.*` — shm_size, ulimit, restart policy
- `nvidia.*` — capabilities, visible_devices
- `api.*` — base_url, heartbeat_interval

### Key Patterns

- **Pydantic models** для валидации (config, task, hardware)
- **loguru** вместо print
- **httpx** вместо requests
- **Textual** для TUI
- **Typer** для CLI

## Dependencies

Python 3.12+ with:
- `httpx` — HTTP client
- `pydantic`, `pydantic-settings` — validation
- `loguru` — logging
- `typer` — CLI
- `textual` — TUI
- `psutil` — system metrics
- `pyyaml` — config

External:
- Docker с NVIDIA Container Toolkit
- `uv` для запуска

## MCP Server

Always use Context7 MCP for library docs, code generation, configuration without explicit ask.
