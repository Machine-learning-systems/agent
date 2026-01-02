import time
from pathlib import Path

from loguru import logger

from core.api.client import APIClient
from core.models.config import Config
from core.models.task import Task, TaskResult
from core.services.container import ContainerManager
from core.services.handlers import TaskHandlerRegistry
from core.services.hardware import HardwareCollector
from core.services.metrics_collector import ContainerMetricsCollector


class Agent:
    """Main agent orchestrator."""

    def __init__(
        self,
        secret_key: str,
        config: Config | None = None,
        agent_id_file: str = ".agent_id",
    ):
        self.secret_key = secret_key
        self.config = config or Config.load()
        self.agent_id_file = Path(agent_id_file)
        self.agent_id: str | None = None

        self.api_client = APIClient(
            base_url=self.config.api.base_url,
            secret_key=secret_key,
        )
        self.container_manager = ContainerManager(self.config)
        self.hardware = HardwareCollector()
        self.metrics_collector = ContainerMetricsCollector(
            container_manager=self.container_manager,
            prefix="task_",
        )

        self._load_agent_id()

    def _load_agent_id(self) -> None:
        """Load saved agent_id from file."""
        if self.agent_id_file.exists():
            self.agent_id = self.agent_id_file.read_text().strip()
            self.api_client.agent_id = self.agent_id
            logger.info(f"Loaded agent_id: {self.agent_id}")

    def _save_agent_id(self, agent_id: str) -> None:
        """Save agent_id to file."""
        try:
            self.agent_id_file.write_text(agent_id)
        except OSError as e:
            logger.warning(f"Failed to save agent_id to file: {e}")
        self.agent_id = agent_id
        self.api_client.agent_id = agent_id
        logger.info(f"Saved agent_id: {agent_id}")

    def initialize(self) -> bool:
        """Initialize the agent."""
        logger.info("Initializing agent...")

        if not self.container_manager.check_and_install_docker():
            logger.error("Docker is required but not available")
            return False

        gpu_support = self.container_manager.check_docker_gpu_support()
        if not gpu_support:
            logger.warning("GPU support not available")

        system_data = self.hardware.collect_system_data()

        if not self.agent_id:
            logger.info("First run - confirming with server...")
            agent_id = self.api_client.confirm_agent(system_data)
            if not agent_id:
                logger.error("Failed to confirm agent")
                return False
            self._save_agent_id(agent_id)

        success = self.api_client.send_init_data(system_data)
        if not success:
            logger.warning("Failed to send init data, continuing...")

        # Initialize container metrics collector
        if not self.metrics_collector.initialize():
            logger.warning("Container metrics disabled (no GPU)")

        logger.info("Agent initialized successfully")
        return True

    def process_task(self, task: Task) -> TaskResult | None:
        """Process a received task."""
        logger.info(f"Processing task {task.id}: {task.task_data.operation}")
        try:
            handler = TaskHandlerRegistry.get_handler(
                task.task_data.operation,
                self.container_manager,
            )
            result = handler.handle(task)
            logger.info(f"Task {task.id} completed: {result.status}")
            return result
        except ValueError as e:
            logger.error(f"Unknown operation for task {task.id}: {e}")
            return TaskResult(
                status="failed",
                error_message=str(e),
            )
        except Exception as e:
            logger.exception(f"Task {task.id} processing failed: {e}")
            return TaskResult(
                status="failed",
                error_message=str(e),
            )

    def run(self) -> None:
        """Run the agent main loop."""
        logger.info("Starting GpuGo Agent...")

        if not self.initialize():
            logger.error("Agent initialization failed, exiting")
            return

        self.api_client.start_polling(self.process_task)

        # Heartbeat every 60 seconds with container metrics
        heartbeat_interval = 60
        heartbeat_counter = 0
        check_interval = 60

        try:
            while True:
                time.sleep(check_interval)
                heartbeat_counter += check_interval

                if heartbeat_counter >= heartbeat_interval:
                    monitoring_data = self.hardware.collect_monitoring_data()

                    # Collect container metrics if available
                    container_metrics = None
                    if self.metrics_collector.available:
                        try:
                            report = self.metrics_collector.collect()
                            container_metrics = report.model_dump()
                        except Exception as e:
                            logger.debug(f"Container metrics failed: {e}")

                    # Extended heartbeat payload
                    heartbeat_payload = {
                        **monitoring_data.model_dump(),
                        "container_metrics": container_metrics,
                    }

                    self.api_client.send_heartbeat(heartbeat_payload)
                    heartbeat_counter = 0
                    logger.debug("Heartbeat sent")

        except KeyboardInterrupt:
            logger.info("Received interrupt, shutting down...")
        finally:
            self.api_client.close()
            logger.info("Agent shutdown complete")
