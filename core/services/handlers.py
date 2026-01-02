from abc import ABC, abstractmethod
from typing import Any

from core.models.task import Task, TaskResult
from core.services.container import ContainerManager


class TaskHandler(ABC):
    def __init__(self, container_manager: ContainerManager):
        self.container_manager = container_manager

    @abstractmethod
    def handle(self, task: Task) -> TaskResult:
        pass

    def _get_container_ids(self, task: Task) -> tuple[str | None, str | None]:
        """Get container_id and container_name from task."""
        container_id = task.task_data.container_id or task.container_info.container_id
        container_name = (
            task.task_data.container_name or task.container_info.container_name
        )
        return container_id, container_name


class StartHandler(TaskHandler):
    def handle(self, task: Task) -> TaskResult:
        task_data = task.task_data
        container_info = task.container_info
        resources = task_data.resources

        container_name = f"task_{task.id}"

        if not task_data.docker_image:
            return TaskResult(
                status="failed",
                container_name=container_name,
                error_message="docker_image not specified",
            )

        if not container_info.ssh_password:
            return TaskResult(
                status="failed",
                container_name=container_name,
                error_message="ssh_password not specified",
            )

        port_mapping: dict[int, int]
        if container_info.port_mapping:
            port_mapping = container_info.port_mapping
        elif container_info.ssh_port:
            port_mapping = {
                container_info.ssh_port: 22,
                container_info.ssh_port + 1: 8888,
            }
            if task_data.services.enable_code_server:
                port_mapping[container_info.ssh_port + 2] = 8080
            if task_data.services.enable_comfyui:
                port_mapping[container_info.ssh_port + 3] = 9000
        else:
            return TaskResult(
                status="failed",
                container_name=container_name,
                error_message="port_mapping or ssh_port required",
            )

        invalid_ports = [p for p in port_mapping if not 1 <= p <= 65535]
        if invalid_ports:
            return TaskResult(
                status="failed",
                container_name=container_name,
                error_message=f"Invalid ports: {invalid_ports}",
            )

        try:
            result = self.container_manager.start(
                name=container_name,
                image=task_data.docker_image,
                port_mapping=port_mapping,
                password=container_info.ssh_password,
                token=container_info.ssh_password,
                gpus=resources.gpus_param,
                cpuset_cpus=resources.cpuset_cpus,
                memory_gb=resources.ram_allocated_gb,
                storage_gb=resources.storage_allocated_gb,
                shm_size_gb=resources.shm_size_gb,
                services=task_data.services,
            )

            ssh_port = next(
                (hp for hp, cp in port_mapping.items() if cp == 22),
                None,
            )

            allocated: dict[str, Any] = {
                "cpu_cpuset": resources.cpuset_cpus,
                "ram_gb": resources.ram_allocated_gb,
                "gpu_count": resources.gpu_required,
                "gpu_devices": resources.gpus_param,
                "storage_gb": resources.storage_allocated_gb,
                "gpu_support": bool(resources.gpus_param),
            }

            return TaskResult(
                status="running",
                container_id=result.container_id,
                container_name=result.container_name,
                ssh_port=ssh_port,
                ssh_host=container_info.ssh_host,
                ssh_command=f"ssh {container_info.ssh_username}@{container_info.ssh_host} -p {ssh_port}"
                if ssh_port and container_info.ssh_host
                else None,
                ssh_username=container_info.ssh_username,
                ssh_password=container_info.ssh_password,
                port_mapping=port_mapping,
                allocated_resources=allocated,
            )

        except Exception as e:
            return TaskResult(
                status="failed",
                container_name=container_name,
                error_message=str(e),
            )


class StopHandler(TaskHandler):
    def handle(self, task: Task) -> TaskResult:
        container_id, container_name = self._get_container_ids(task)

        if not container_id:
            return TaskResult(
                status="failed",
                container_name=container_name,
                error_message="Missing container_id",
            )

        success = self.container_manager.stop_by_id(container_id)

        return TaskResult(
            status="completed" if success else "failed",
            container_id=container_id,
            container_name=container_name,
            error_message=None if success else "Stop failed",
        )


class StopRemoveHandler(TaskHandler):
    def handle(self, task: Task) -> TaskResult:
        container_id, container_name = self._get_container_ids(task)

        if not container_id:
            return TaskResult(
                status="failed",
                container_name=container_name,
                error_message="Missing container_id",
            )

        stop_ok = self.container_manager.stop_by_id(container_id)
        remove_ok = self.container_manager.remove_by_id(container_id)

        errors = []
        if not stop_ok:
            errors.append("stop failed")
        if not remove_ok:
            errors.append("remove failed")

        return TaskResult(
            status="completed" if (stop_ok and remove_ok) else "failed",
            container_id=container_id,
            container_name=container_name,
            error_message=", ".join(errors) if errors else None,
        )


class RestartHandler(TaskHandler):
    def handle(self, task: Task) -> TaskResult:
        container_id, container_name = self._get_container_ids(task)

        if not container_id:
            return TaskResult(
                status="failed",
                container_name=container_name,
                error_message="Missing container_id",
            )

        success = self.container_manager.restart_by_id(container_id)

        return TaskResult(
            status="completed" if success else "failed",
            container_id=container_id,
            container_name=container_name,
            error_message=None if success else "Restart failed",
        )


class TaskHandlerRegistry:
    @classmethod
    def get_handler(cls, operation: str, manager: ContainerManager) -> TaskHandler:
        match operation:
            case "start":
                return StartHandler(manager)
            case "stop":
                return StopHandler(manager)
            case "stop_remove":
                return StopRemoveHandler(manager)
            case "restart":
                return RestartHandler(manager)
            case _:
                raise ValueError(f"Unknown operation: {operation}")
