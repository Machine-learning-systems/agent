import subprocess

from textual.widgets import DataTable


class ContainerTable(DataTable):
    """Widget displaying container list as a data table."""

    def on_mount(self) -> None:
        """Initialize table columns."""
        self.add_columns("Name", "Status", "Image", "Ports")
        self.cursor_type = "row"
        self.refresh_data()

    def refresh_data(self) -> None:
        """Refresh container list from Docker."""
        self.clear()

        try:
            result = subprocess.run(
                [
                    "docker",
                    "ps",
                    "-a",
                    "--filter",
                    "name=task_",
                    "--format",
                    "{{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Ports}}",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if line:
                        parts = line.split("\t")
                        if len(parts) >= 4:
                            name = parts[0]
                            status = parts[1]
                            image = parts[2]
                            ports = parts[3]

                            if "Up" in status:
                                status_display = f"[green]{status}[/]"
                            elif "Exited" in status:
                                status_display = f"[red]{status}[/]"
                            else:
                                status_display = f"[yellow]{status}[/]"

                            ports_short = (
                                ports[:35] + "..." if len(ports) > 35 else ports
                            )

                            self.add_row(
                                name, status_display, image, ports_short, key=name
                            )
        except FileNotFoundError:
            pass
        except Exception:
            pass

    def get_selected_container(self) -> str | None:
        """Get currently selected container name."""
        if self.cursor_row is not None and self.row_count > 0:
            row_key = self.get_row_at(self.cursor_row)
            if row_key:
                return str(row_key.key.value) if row_key.key else None
        return None
