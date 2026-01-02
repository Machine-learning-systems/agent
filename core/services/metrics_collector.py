"""Container GPU metrics collection via nvitop."""

import subprocess
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from nvitop import Device, GpuProcess

from core.models.metrics import (
    ContainerGpuMetrics,
    ContainerMetricsReport,
    DeviceMetrics,
)
from core.services.container import ContainerManager


class ContainerMetricsCollector:
    """Collects per-container GPU metrics using nvitop."""

    def __init__(self, container_manager: ContainerManager, prefix: str = "task_"):
        self.container_manager = container_manager
        self.prefix = prefix
        self._devices: list[Device] = []

    def initialize(self) -> bool:
        """Initialize nvitop devices."""
        try:
            self._devices = Device.all()
            if self._devices:
                logger.info(f"nvitop initialized: {len(self._devices)} GPU(s)")
                return True
            logger.warning("No GPU devices found")
            return False
        except Exception as e:
            logger.warning(f"nvitop initialization failed: {e}")
            return False

    @property
    def available(self) -> bool:
        """Check if nvitop is available."""
        return bool(self._devices)

    def collect(self) -> ContainerMetricsReport:
        """Collect metrics for all containers."""
        timestamp = datetime.now(UTC).isoformat()

        # 1. Collect device-level metrics
        devices = self._collect_device_metrics()

        # 2. Build PID → container mapping
        pid_to_container = self._build_pid_mapping()

        # 3. Collect GPU processes and aggregate by container
        containers = self._collect_container_metrics(pid_to_container, devices)

        return ContainerMetricsReport(
            timestamp=timestamp,
            containers=containers,
            devices=devices,
        )

    def _collect_device_metrics(self) -> list[DeviceMetrics]:
        """Collect GPU device metrics."""
        metrics = []
        for device in self._devices:
            try:
                metrics.append(
                    DeviceMetrics(
                        index=device.index,
                        memory_used_bytes=device.memory_used() or 0,
                        memory_total_bytes=device.memory_total() or 0,
                        gpu_utilization=device.gpu_utilization() or 0,
                        temperature=device.temperature(),
                    )
                )
            except Exception as e:
                logger.debug(f"Device {device.index} metrics failed: {e}")
        return metrics

    def _build_pid_mapping(self) -> dict[int, tuple[str, str]]:
        """Build mapping: PID → (container_id, container_name)."""
        pid_to_container: dict[int, tuple[str, str]] = {}

        containers = self.container_manager.list_containers(prefix=self.prefix)
        for container in containers:
            name = container.get("name")
            if not name or "Up" not in container.get("status", ""):
                continue

            container_id = self._get_container_id(name)
            pids = self._get_container_pids(name)

            for pid in pids:
                pid_to_container[pid] = (container_id or name, name)

        return pid_to_container

    def _get_container_id(self, name: str) -> str | None:
        """Get container ID by name."""
        try:
            result = subprocess.run(
                ["docker", "inspect", "--format", "{{.Id}}", name],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()[:12]
        except subprocess.TimeoutExpired:
            logger.debug(f"docker inspect timeout: {name}")
        except subprocess.SubprocessError as e:
            logger.debug(f"docker inspect failed: {e}")
        return None

    def _get_container_pids(self, name: str) -> set[int]:
        """Get all PIDs running inside a container."""
        pids: set[int] = set()
        try:
            result = subprocess.run(
                ["docker", "top", name, "-o", "pid"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n")[1:]:
                    try:
                        pids.add(int(line.strip()))
                    except ValueError:
                        continue
        except subprocess.TimeoutExpired:
            logger.debug(f"docker top timeout: {name}")
        except subprocess.SubprocessError as e:
            logger.debug(f"docker top failed: {e}")
        return pids

    def _collect_container_metrics(
        self,
        pid_to_container: dict[int, tuple[str, str]],
        devices: list[DeviceMetrics],
    ) -> list[ContainerGpuMetrics]:
        """Collect GPU metrics per container."""
        container_data: dict[str, dict[str, Any]] = {}

        with GpuProcess.failsafe():
            for device in self._devices:
                try:
                    processes = device.processes()
                except Exception:
                    continue

                for pid, proc in processes.items():
                    if pid not in pid_to_container:
                        continue

                    container_id, container_name = pid_to_container[pid]

                    if container_name not in container_data:
                        container_data[container_name] = {
                            "container_id": container_id,
                            "gpu_indices": set(),
                            "gpu_memory_bytes": 0,
                            "gpu_utilization": {},
                            "cpu_percent": 0.0,
                            "process_count": 0,
                        }

                    data = container_data[container_name]
                    data["gpu_indices"].add(device.index)
                    data["gpu_memory_bytes"] += proc.gpu_memory() or 0
                    data["cpu_percent"] += proc.cpu_percent() or 0.0
                    data["process_count"] += 1

                    # GPU utilization: take max per GPU
                    gpu_key = str(device.index)
                    sm_util = proc.gpu_sm_utilization() or 0
                    data["gpu_utilization"][gpu_key] = max(
                        data["gpu_utilization"].get(gpu_key, 0), sm_util
                    )

        # Build result
        result: list[ContainerGpuMetrics] = []
        for name, data in container_data.items():
            # Calculate memory percentage
            total_memory = sum(
                d.memory_total_bytes for d in devices if d.index in data["gpu_indices"]
            )
            memory_percent = (
                (data["gpu_memory_bytes"] / total_memory * 100)
                if total_memory > 0
                else 0.0
            )

            result.append(
                ContainerGpuMetrics(
                    container_id=data["container_id"],
                    container_name=name,
                    gpu_indices=sorted(data["gpu_indices"]),
                    gpu_memory_bytes=data["gpu_memory_bytes"],
                    gpu_memory_percent=round(memory_percent, 2),
                    gpu_utilization=data["gpu_utilization"],
                    cpu_percent=round(data["cpu_percent"], 2),
                    process_count=data["process_count"],
                )
            )

        return result
