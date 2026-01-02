import psutil
from textual.reactive import reactive
from textual.widgets import Static


class AgentStatus(Static):
    """Widget displaying agent status and system info."""

    status: reactive[str] = reactive("offline")
    agent_id: reactive[str] = reactive("")
    uptime: reactive[str] = reactive("0:00:00")

    def render(self) -> str:
        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory()

        status_color = "green" if self.status == "online" else "red"

        return f"""[bold]Agent Status[/bold]
Status: [{status_color}]{self.status}[/]
Agent ID: {self.agent_id or "Not registered"}
Uptime: {self.uptime}

[bold]System Resources[/bold]
CPU: {cpu:.1f}%
Memory: {mem.percent:.1f}% ({mem.used // (1024**3)}/{mem.total // (1024**3)} GB)
"""

    def refresh_data(self) -> None:
        """Refresh status data."""
        self.refresh()

    def set_status(self, status: str, agent_id: str = "", uptime: str = "") -> None:
        """Update status values."""
        self.status = status
        if agent_id:
            self.agent_id = agent_id
        if uptime:
            self.uptime = uptime
