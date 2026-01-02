import subprocess

from textual.reactive import reactive
from textual.widgets import Static


class GPUMonitor(Static):
    """Widget displaying GPU status and metrics."""

    gpus: reactive[list] = reactive([])

    def render(self) -> str:
        lines = ["[bold]GPU Monitor[/bold]", ""]

        if not self.gpus:
            return lines[0] + "\n\nNo GPUs detected or nvidia-smi unavailable"

        for i, gpu in enumerate(self.gpus):
            util = gpu.get("utilization", 0)
            if util < 50:
                util_color = "green"
            elif util < 80:
                util_color = "yellow"
            else:
                util_color = "red"

            temp = gpu.get("temperature", 0)
            if temp < 60:
                temp_color = "green"
            elif temp < 80:
                temp_color = "yellow"
            else:
                temp_color = "red"

            lines.extend([
                f"[bold]GPU {i}:[/bold] {gpu.get('name', 'Unknown')}",
                f"  Usage: [{util_color}]{util}%[/]",
                f"  Memory: {gpu.get('memory_used', 0)}/{gpu.get('memory_total', 0)} MB",
                f"  Temp: [{temp_color}]{temp}°C[/]",
                "",
            ])

        return "\n".join(lines)

    def refresh_data(self) -> None:
        """Refresh GPU data from nvidia-smi."""
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                gpus = []
                for line in result.stdout.strip().split("\n"):
                    if line:
                        parts = [p.strip() for p in line.split(",")]
                        if len(parts) >= 5:
                            gpus.append({
                                "name": parts[0],
                                "utilization": int(parts[1])
                                if parts[1].isdigit()
                                else 0,
                                "memory_used": int(parts[2])
                                if parts[2].isdigit()
                                else 0,
                                "memory_total": int(parts[3])
                                if parts[3].isdigit()
                                else 0,
                                "temperature": int(parts[4])
                                if parts[4].isdigit()
                                else 0,
                            })
                self.gpus = gpus
        except FileNotFoundError:
            self.gpus = []
        except subprocess.TimeoutExpired:
            pass  # Keep previous data on timeout
        except subprocess.SubprocessError:
            pass  # Keep previous data on error
        self.refresh()
