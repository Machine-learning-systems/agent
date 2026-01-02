"""Pydantic models for container GPU metrics."""

from pydantic import BaseModel, Field


class DeviceMetrics(BaseModel):
    """GPU device-level metrics."""

    index: int
    memory_used_bytes: int = 0
    memory_total_bytes: int = 0
    gpu_utilization: int = 0
    temperature: int | None = None

    @property
    def memory_percent(self) -> float:
        """Calculate memory usage percentage."""
        if self.memory_total_bytes == 0:
            return 0.0
        return (self.memory_used_bytes / self.memory_total_bytes) * 100

    @property
    def memory_used_gb(self) -> float:
        """Memory used in gigabytes."""
        return self.memory_used_bytes / (1024**3)

    @property
    def memory_total_gb(self) -> float:
        """Total memory in gigabytes."""
        return self.memory_total_bytes / (1024**3)


class ContainerGpuMetrics(BaseModel):
    """GPU metrics for a single container."""

    container_id: str
    container_name: str
    gpu_indices: list[int] = Field(default_factory=list)
    gpu_memory_bytes: int = 0
    gpu_memory_percent: float = 0.0
    gpu_utilization: dict[str, int] = Field(default_factory=dict)
    cpu_percent: float = 0.0
    process_count: int = 0

    @property
    def gpu_memory_gb(self) -> float:
        """GPU memory used in gigabytes."""
        return self.gpu_memory_bytes / (1024**3)


class ContainerMetricsReport(BaseModel):
    """Complete container metrics report."""

    timestamp: str
    containers: list[ContainerGpuMetrics] = Field(default_factory=list)
    devices: list[DeviceMetrics] = Field(default_factory=list)
