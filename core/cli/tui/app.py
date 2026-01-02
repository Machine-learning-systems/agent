import subprocess
from datetime import datetime

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Footer, Header, Static

from core.cli.tui.widgets import AgentStatus, ContainerTable, GPUMonitor


class LogPanel(Static):
    """Simple log panel widget."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logs: list[str] = []

    def add_log(self, message: str) -> None:
        """Add a log message."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.logs.append(f"[dim]{timestamp}[/] {message}")
        if len(self.logs) > 50:
            self.logs = self.logs[-50:]
        self.refresh()

    def render(self) -> str:
        header = "[bold]Logs[/bold]\n"
        if not self.logs:
            return header + "[dim]No logs yet...[/]"
        return header + "\n".join(self.logs[-15:])


class AgentDashboard(App):
    """GpuGo Agent Dashboard TUI."""

    CSS = """
    Screen {
        layout: grid;
        grid-size: 2 3;
        grid-gutter: 1;
    }

    #status-panel {
        row-span: 1;
        column-span: 1;
        border: solid green;
        padding: 1;
        height: 100%;
    }

    #gpu-panel {
        row-span: 1;
        column-span: 1;
        border: solid blue;
        padding: 1;
        height: 100%;
    }

    #containers-panel {
        row-span: 1;
        column-span: 2;
        border: solid yellow;
        padding: 1;
    }

    #logs-panel {
        row-span: 1;
        column-span: 2;
        border: solid cyan;
        padding: 1;
    }

    DataTable {
        height: 100%;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("s", "stop_container", "Stop"),
        ("d", "remove_container", "Remove"),
        ("l", "show_logs", "Container Logs"),
    ]

    def __init__(self, agent_id: str = "", status: str = "offline"):
        super().__init__()
        self._agent_id = agent_id
        self._status = status
        self._uptime_start = datetime.now()

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Header()
        yield Container(
            AgentStatus(id="status-panel"),
            GPUMonitor(id="gpu-panel"),
            ContainerTable(id="containers-panel"),
            LogPanel(id="logs-panel"),
        )
        yield Footer()

    def on_mount(self) -> None:
        """Initialize on mount."""
        self.title = "GpuGo Agent Dashboard"
        self.sub_title = f"Agent: {self._agent_id or 'Not registered'}"

        status_widget = self.query_one("#status-panel", AgentStatus)
        status_widget.set_status(self._status, self._agent_id)

        self._log("Dashboard started")
        self.set_interval(5, self.action_refresh)

    def action_refresh(self) -> None:
        """Refresh all widgets."""
        uptime = datetime.now() - self._uptime_start
        hours, remainder = divmod(int(uptime.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)

        status_widget = self.query_one("#status-panel", AgentStatus)
        status_widget.uptime = f"{hours}:{minutes:02d}:{seconds:02d}"
        status_widget.refresh_data()

        self.query_one("#gpu-panel", GPUMonitor).refresh_data()
        self.query_one("#containers-panel", ContainerTable).refresh_data()

    def action_stop_container(self) -> None:
        """Stop selected container."""
        table = self.query_one("#containers-panel", ContainerTable)
        container = table.get_selected_container()
        if container:
            try:
                subprocess.run(
                    ["docker", "stop", container], capture_output=True, timeout=30
                )
                self._log(f"Stopped container: {container}")
                table.refresh_data()
            except Exception as e:
                self._log(f"Failed to stop {container}: {e}")
        else:
            self._log("No container selected")

    def action_remove_container(self) -> None:
        """Remove selected container."""
        table = self.query_one("#containers-panel", ContainerTable)
        container = table.get_selected_container()
        if container:
            try:
                subprocess.run(
                    ["docker", "stop", container], capture_output=True, timeout=30
                )
                subprocess.run(
                    ["docker", "rm", container], capture_output=True, timeout=10
                )
                self._log(f"Removed container: {container}")
                table.refresh_data()
            except Exception as e:
                self._log(f"Failed to remove {container}: {e}")
        else:
            self._log("No container selected")

    def action_show_logs(self) -> None:
        """Show logs for selected container."""
        table = self.query_one("#containers-panel", ContainerTable)
        container = table.get_selected_container()
        if container:
            try:
                result = subprocess.run(
                    ["docker", "logs", "--tail", "10", container],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.stdout:
                    for line in result.stdout.strip().split("\n")[-5:]:
                        self._log(f"[{container}] {line[:80]}")
            except Exception as e:
                self._log(f"Failed to get logs for {container}: {e}")
        else:
            self._log("No container selected")

    def _log(self, message: str) -> None:
        """Add message to log panel."""
        try:
            log_panel = self.query_one("#logs-panel", LogPanel)
            log_panel.add_log(message)
        except Exception:
            pass


def run_dashboard(agent_id: str = "", status: str = "offline") -> None:
    """Run the dashboard app."""
    app = AgentDashboard(agent_id=agent_id, status=status)
    app.run()
