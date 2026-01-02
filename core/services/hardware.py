import platform
import re
import subprocess
from typing import Any

import httpx
import psutil
from loguru import logger

from core.models.hardware import CPUInfo, GPUInfo, MonitoringData, SystemInfo


class HardwareCollector:
    """Collects hardware and system information."""

    def __init__(self):
        self._system = platform.system()
        self._cache: dict[str, Any] = {}

    def get_cpu_info(self) -> list[CPUInfo]:
        """Collect CPU information."""
        if "cpu" in self._cache:
            return self._cache["cpu"]

        try:
            if self._system == "Linux":
                return self._get_cpu_linux()
            return self._get_cpu_fallback()
        except Exception as e:
            logger.warning(f"CPU detection failed: {e}")
            return [
                CPUInfo(model="Unknown", cores=psutil.cpu_count(logical=False) or 1)
            ]

    def get_gpu_info(self) -> list[GPUInfo]:
        """Collect GPU information via nvidia-smi."""
        if "gpu" in self._cache:
            return self._cache["gpu"]

        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total",
                    "--format=csv,noheader",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return []

            gpus = []
            for line in result.stdout.strip().split("\n"):
                if line:
                    parts = line.split(",")
                    model = parts[0].strip()
                    vram_match = (
                        re.search(r"(\d+)", parts[1]) if len(parts) > 1 else None
                    )
                    vram_gb = int(vram_match.group(1)) // 1024 if vram_match else 0
                    gpus.append(GPUInfo(model=model, vram_gb=vram_gb))

            self._cache["gpu"] = gpus
            return gpus
        except FileNotFoundError:
            logger.debug("nvidia-smi not found")
            return []
        except Exception as e:
            logger.warning(f"GPU detection failed: {e}")
            return []

    def get_ip_address(self) -> str | None:
        """Get external IP address."""
        for url in ["https://api.ipify.org", "https://ifconfig.me"]:
            try:
                response = httpx.get(url, timeout=5)
                if response.status_code == 200:
                    return response.text.strip()
            except Exception:
                continue
        return None

    def get_location(self, ip: str) -> str:
        """Get location from IP address."""
        try:
            response = httpx.get(f"http://ip-api.com/json/{ip}", timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    return f"{data.get('city', 'Unknown')}, {data.get('country', 'Unknown')}"
        except Exception as e:
            logger.warning(f"Location detection failed: {e}")
        return "Unknown"

    def collect_system_info(self) -> SystemInfo:
        """Collect complete system information."""
        logger.info("Collecting system information...")

        ip_address = self.get_ip_address()
        location = self.get_location(ip_address) if ip_address else "Unknown"
        ram_gb = round(psutil.virtual_memory().total / (1024**3))

        return SystemInfo(
            hostname=platform.node(),
            ip_address=ip_address,
            total_ram_gb=ram_gb,
            ram_type=self._get_ram_type(),
            location=location,
            cpus=self.get_cpu_info(),
            gpus=self.get_gpu_info(),
        )

    def collect_system_data(self) -> dict[str, Any]:
        """Collect system data for API."""
        info = self.collect_system_info()
        monitoring = self.collect_monitoring_data()

        return {
            "hostname": info.hostname,
            "ip_address": info.ip_address,
            "total_ram_gb": info.total_ram_gb,
            "ram_type": info.ram_type,
            "location": info.location,
            "status": "online",
            "cpu_usage": monitoring.cpu_usage,
            "memory_usage": monitoring.memory_usage,
            "gpu_usage": sum(monitoring.gpu_usage.values()) / len(monitoring.gpu_usage)
            if monitoring.gpu_usage
            else 0,
            "hardware_info": {
                "cpus": [c.model_dump() for c in info.cpus],
                "gpus": [g.model_dump() for g in info.gpus],
            },
        }

    def collect_monitoring_data(self) -> MonitoringData:
        """Collect real-time monitoring metrics."""
        return MonitoringData(
            cpu_usage=psutil.cpu_percent(),
            memory_usage=psutil.virtual_memory().percent,
            gpu_usage=self._get_gpu_usage(),
            disk_usage={"/": psutil.disk_usage("/").percent},
        )

    def _get_gpu_usage(self) -> dict[str, float]:
        """Get per-GPU usage."""
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return {
                    f"gpu{i}": float(usage)
                    for i, usage in enumerate(result.stdout.strip().split("\n"))
                    if usage
                }
        except Exception:
            pass
        return {}

    def _get_ram_type(self) -> str:
        """Detect RAM type on Linux."""
        if self._system != "Linux":
            return "Unknown"
        try:
            result = subprocess.run(
                ["sudo", "dmidecode", "-t", "memory"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            match = re.search(r"Type:\s+(DDR\w*)", result.stdout)
            return match.group(1) if match else "Unknown"
        except Exception:
            return "Unknown"

    def _get_cpu_linux(self) -> list[CPUInfo]:
        """Get CPU info on Linux via lscpu."""
        result = subprocess.run(["lscpu"], capture_output=True, text=True, timeout=5)
        output = result.stdout

        model_match = re.search(r"Model name:\s+(.+)", output)
        sockets_match = re.search(r"Socket\(s\):\s+(\d+)", output)
        cores = psutil.cpu_count(logical=False)
        threads = psutil.cpu_count(logical=True)
        sockets = int(sockets_match.group(1)) if sockets_match else 1

        info = CPUInfo(
            model=model_match.group(1).strip() if model_match else "Unknown",
            cores=cores // sockets if cores else 1,
            threads=threads // sockets if threads else 1,
            count=sockets,
        )
        self._cache["cpu"] = [info]
        return [info]

    def _get_cpu_fallback(self) -> list[CPUInfo]:
        """Fallback CPU detection."""
        return [
            CPUInfo(
                model=platform.processor() or "Unknown",
                cores=psutil.cpu_count(logical=False) or 1,
                threads=psutil.cpu_count(logical=True) or 1,
            )
        ]

    def clear_cache(self) -> None:
        """Clear cached hardware info."""
        self._cache.clear()
