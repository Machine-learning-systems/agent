import threading
import time
from collections.abc import Callable
from typing import Any

import httpx
from loguru import logger

from core.models.task import Task, TaskResult


class APIClient:
    """HTTP client for GpuGo API communication."""

    def __init__(
        self,
        base_url: str = "https://api.gpugo.ru",
        secret_key: str | None = None,
        timeout: float = 15.0,
    ):
        self.base_url = base_url
        self.secret_key = secret_key
        self.agent_id: str | None = None

        self._client = httpx.Client(
            base_url=base_url,
            timeout=httpx.Timeout(connect=5.0, read=timeout, write=5.0, pool=5.0),
            headers={"Content-Type": "application/json"},
        )
        self._polling_active = False
        self._polling_thread: threading.Thread | None = None

    def _get_headers(self) -> dict[str, str]:
        """Get request headers with auth."""
        headers: dict[str, str] = {}
        if self.secret_key:
            headers["X-Agent-Secret-Key"] = self.secret_key
        return headers

    def confirm_agent(self, data: dict[str, Any]) -> str | None:
        """Confirm agent and get agent_id."""
        try:
            response = self._client.post(
                "/v1/agents/confirm",
                json=data,
                headers=self._get_headers(),
            )
            response.raise_for_status()
            result = response.json()
            data_field = result.get("data", {})
            return data_field.get("agent_id") or data_field.get("id")
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Confirm agent HTTP error {e.response.status_code}: {e.response.text}"
            )
        except httpx.RequestError as e:
            logger.error(f"Confirm agent request failed: {e}")
        return None

    def send_init_data(self, data: dict[str, Any]) -> bool:
        """Send initialization data to server."""
        if not self.agent_id:
            logger.error("Agent ID not set")
            return False
        try:
            response = self._client.post(
                f"/v1/agents/{self.agent_id}/init",
                json=data,
                headers=self._get_headers(),
            )
            response.raise_for_status()
            result = response.json()
            return result.get("exception") == 0
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Init data HTTP error {e.response.status_code}: {e.response.text}"
            )
        except httpx.RequestError as e:
            logger.error(f"Init data request failed: {e}")
        return False

    def send_heartbeat(self, monitoring_data: dict[str, Any]) -> bool:
        """Send heartbeat with monitoring data."""
        if not self.agent_id:
            return False
        try:
            response = self._client.post(
                f"/v1/agents/{self.agent_id}/heartbeat",
                json={"status": "online", **monitoring_data},
                headers=self._get_headers(),
            )
            response.raise_for_status()
            return response.json().get("exception") == 0
        except httpx.TimeoutException:
            logger.warning("Heartbeat timeout")
        except httpx.RequestError as e:
            logger.warning(f"Heartbeat failed: {e}")
        return False

    def send_task_status(self, task_id: str, result: TaskResult) -> bool:
        """Send task status update."""
        if not self.agent_id:
            return False
        try:
            response = self._client.post(
                f"/v1/agents/{self.agent_id}/tasks/{task_id}/status",
                json=result.model_dump(exclude_none=True),
                headers=self._get_headers(),
            )
            response.raise_for_status()
            return response.json().get("exception") == 0
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Task status HTTP error {e.response.status_code}: {e.response.text}"
            )
        except httpx.RequestError as e:
            logger.error(f"Task status request failed: {e}")
        return False

    def send_log(self, message: str) -> bool:
        """Send log message to server."""
        if not self.agent_id:
            return False
        try:
            response = self._client.post(
                f"/v1/agents/{self.agent_id}/logs",
                json={"message": str(message)},
                headers={"Content-Type": "application/json"},
                timeout=5.0,
            )
            return response.status_code == 200
        except Exception:
            return False

    def poll_for_tasks(self, callback: Callable[[Task], TaskResult | None]) -> None:
        """Poll for tasks and execute callback."""
        if not self.agent_id:
            logger.error("Agent ID not set, cannot poll")
            return

        consecutive_errors = 0
        max_errors = 5

        while self._polling_active:
            try:
                response = self._client.post(
                    f"/v1/agents/{self.agent_id}/tasks/pull",
                    headers=self._get_headers(),
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json().get("data", {})

                if data.get("task_id") is not None:
                    task = Task.model_validate({
                        "id": data["task_id"],
                        "task_data": data.get("task_data", {}),
                        "container_info": data.get("container_info", {}),
                    })
                    logger.info(f"Received task: {task.id}")
                    result = callback(task)
                    if result:
                        self.send_task_status(str(task.id), result)

                consecutive_errors = 0

            except httpx.TimeoutException:
                logger.debug("Poll timeout, retrying...")
            except httpx.HTTPStatusError as e:
                logger.warning(f"Poll HTTP error {e.response.status_code}")
                consecutive_errors += 1
            except httpx.RequestError as e:
                logger.warning(f"Poll request error: {e}")
                consecutive_errors += 1
            except Exception as e:
                logger.exception(f"Poll unexpected error: {e}")
                consecutive_errors += 1

            wait_time = 60 if consecutive_errors >= max_errors else 10
            if consecutive_errors >= max_errors:
                logger.warning(f"Too many errors ({consecutive_errors}), backing off")
            time.sleep(wait_time)

    def start_polling(self, callback: Callable[[Task], TaskResult | None]) -> None:
        """Start polling in background thread."""
        self._polling_active = True
        self._polling_thread = threading.Thread(
            target=self.poll_for_tasks,
            args=(callback,),
            daemon=True,
        )
        self._polling_thread.start()
        logger.info("Polling thread started")

    def stop_polling(self) -> None:
        """Stop polling."""
        self._polling_active = False
        if self._polling_thread and self._polling_thread.is_alive():
            self._polling_thread.join(timeout=5)
        logger.info("Polling stopped")

    def close(self) -> None:
        """Close client and cleanup."""
        self.stop_polling()
        self._client.close()
