from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class ImageConfig(BaseModel):
    prefix: str = "jsg"
    default: Literal["base", "jupyter", "comfyui"] = "jupyter"


class PortsConfig(BaseModel):
    ssh_base: int = 42200
    jupyter_base: int = 42800
    code_server_base: int = 48000
    comfyui_base: int = 49000


class DebugPortsConfig(BaseModel):
    ssh: int = 2222
    jupyter: int = 8888
    code_server: int = 8080
    comfyui: int = 9000


class ContainerConfig(BaseModel):
    shm_size: str = "16g"
    ulimit_stack: int = 67108864
    restart_policy: str = "unless-stopped"


class NvidiaConfig(BaseModel):
    capabilities: str = "compute,utility"
    visible_devices: str = "all"


class ApiConfig(BaseModel):
    base_url: str = "https://api.gpugo.ru"
    heartbeat_interval: int = 300


class Config(BaseModel):
    image: ImageConfig = Field(default_factory=ImageConfig)
    ports: PortsConfig = Field(default_factory=PortsConfig)
    debug: DebugPortsConfig = Field(default_factory=DebugPortsConfig)
    container: ContainerConfig = Field(default_factory=ContainerConfig)
    nvidia: NvidiaConfig = Field(default_factory=NvidiaConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)

    @classmethod
    def load(cls, path: Path | str = "config.yaml") -> Config:
        path = Path(path)
        if path.exists():
            with path.open() as f:
                data = yaml.safe_load(f) or {}
            return cls.model_validate(data)
        return cls()


class AgentSettings(BaseSettings):
    secret_key: str = Field(alias="GPUGO_SECRET_KEY")
    api_base_url: str = Field(default="https://api.gpugo.ru", alias="API_BASE_URL")
    agent_id_file: str = ".agent_id"

    model_config = {"env_prefix": "GPUGO_", "extra": "ignore", "populate_by_name": True}
