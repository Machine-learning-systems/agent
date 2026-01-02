from pydantic import BaseModel


class CPUInfo(BaseModel):
    """CPU information model."""

    model: str
    cores: int = 1
    threads: int = 1
    freq_ghz: float | None = None
    count: int = 1


class GPUInfo(BaseModel):
    """GPU information model."""

    model: str
    vram_gb: int = 0
    vendor: str = "NVIDIA"
    max_cuda_version: str | None = None


class DiskInfo(BaseModel):
    """Disk information model."""

    model: str = "Unknown"
    type: str = "Unknown"
    size_gb: float | None = None


class NetworkInfo(BaseModel):
    """Network information model."""

    up_mbps: int | None = None
    down_mbps: int | None = None
    interface: str = "Unknown"


class SystemInfo(BaseModel):
    """Complete system information."""

    hostname: str
    ip_address: str | None = None
    total_ram_gb: int = 0
    ram_type: str = "Unknown"
    location: str = "Unknown"
    cpus: list[CPUInfo] = []
    gpus: list[GPUInfo] = []
    disks: list[DiskInfo] = []


class MonitoringData(BaseModel):
    """Real-time monitoring data."""

    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    gpu_usage: dict[str, float] = {}
    disk_usage: dict[str, float] = {}
