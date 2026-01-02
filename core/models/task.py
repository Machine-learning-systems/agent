from typing import Any, Literal

from loguru import logger
from pydantic import BaseModel, Field, field_validator


class ServiceConfig(BaseModel):
    enable_ssh: bool = True
    enable_jupyter: bool = True
    enable_code_server: bool = True
    enable_comfyui: bool = False


CpuRange = tuple[int, int]


class ResourceAllocation(BaseModel):
    gpu_required: int = 0
    gpu_enabled_indices: list[int] | None = None
    cpu_allocated_ranges: list[CpuRange] | None = None
    ram_allocated_gb: int | None = None
    storage_allocated_gb: int | None = None

    @property
    def gpus_param(self) -> str | None:
        if not self.gpu_required:
            return None
        if self.gpu_enabled_indices:
            return ",".join(str(i) for i in self.gpu_enabled_indices)
        return "all"

    @property
    def cpuset_cpus(self) -> str | None:
        if not self.cpu_allocated_ranges:
            return None
        return ",".join(f"{start}-{end}" for start, end in self.cpu_allocated_ranges)

    @property
    def shm_size_gb(self) -> int | None:
        if self.ram_allocated_gb and self.ram_allocated_gb > 0:
            return max(1, self.ram_allocated_gb // 2)
        return None


class TaskData(BaseModel):
    operation: Literal["start", "stop", "stop_remove", "restart"] = "start"
    docker_image: str | None = None
    container_id: str | None = None
    container_name: str | None = None
    gpu_required: int = 0
    gpu_enabled_indices: list[int] | None = None
    cpu_allocated_ranges: list[list[int] | tuple[int, int]] | None = None
    ram_allocated_gb: int | None = None
    storage_allocated_gb: int | None = None
    services: ServiceConfig = Field(default_factory=ServiceConfig)

    @field_validator("docker_image", mode="before")
    @classmethod
    def normalize_image(cls, v: str | None) -> str | None:
        if not v:
            return None
        if v in ("base", "jupyter", "comfyui"):
            return f"jsg-{v}:latest"
        return v

    @property
    def resources(self) -> ResourceAllocation:
        ranges: list[CpuRange] | None = None
        if self.cpu_allocated_ranges:
            ranges = []
            for r in self.cpu_allocated_ranges:
                if isinstance(r, (list, tuple)) and len(r) == 2:
                    try:
                        ranges.append((int(r[0]), int(r[1])))
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Invalid CPU range {r}: {e}")
                        continue

        return ResourceAllocation(
            gpu_required=self.gpu_required,
            gpu_enabled_indices=self.gpu_enabled_indices,
            cpu_allocated_ranges=ranges if ranges else None,
            ram_allocated_gb=self.ram_allocated_gb,
            storage_allocated_gb=self.storage_allocated_gb,
        )


class ContainerInfo(BaseModel):
    ssh_username: str = "root"
    ssh_password: str | None = None
    ssh_port: int | None = None
    ssh_host: str | None = None
    container_id: str | None = None
    container_name: str | None = None
    port_mapping: dict[int, int] | None = None


class Task(BaseModel):
    id: str | int
    task_data: TaskData = Field(default_factory=TaskData)
    container_info: ContainerInfo = Field(default_factory=ContainerInfo)


class TaskResult(BaseModel):
    status: Literal["running", "completed", "failed"]
    container_id: str | None = None
    container_name: str | None = None
    error_message: str | None = None
    ssh_port: int | None = None
    ssh_host: str | None = None
    ssh_command: str | None = None
    ssh_username: str | None = None
    ssh_password: str | None = None
    port_mapping: dict[int, int] | None = None
    allocated_resources: dict[str, Any] | None = None
