from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ServiceConfig(BaseModel):
    enable_ssh: bool = True
    enable_jupyter: bool = True
    enable_code_server: bool = True
    enable_comfyui: bool = False


class ResourceAllocation(BaseModel):
    gpu_required: int = 0
    gpu_enabled_indices: list[int] | None = None
    cpu_allocated_ranges: list[tuple[int, int]] | None = None
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
    cpu_allocated_ranges: list[Any] | None = None
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
        ranges = None
        if self.cpu_allocated_ranges:
            ranges = []
            for r in self.cpu_allocated_ranges:
                if isinstance(r, (list, tuple)) and len(r) == 2:
                    ranges.append((int(r[0]), int(r[1])))

        return ResourceAllocation(
            gpu_required=self.gpu_required,
            gpu_enabled_indices=self.gpu_enabled_indices,
            cpu_allocated_ranges=ranges,
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

    @field_validator("task_data", mode="before")
    @classmethod
    def parse_task_data(cls, v: Any) -> Any:
        if isinstance(v, dict):
            return TaskData.model_validate(v)
        return v

    @field_validator("container_info", mode="before")
    @classmethod
    def parse_container_info(cls, v: Any) -> Any:
        if isinstance(v, dict):
            return ContainerInfo.model_validate(v)
        return v


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
