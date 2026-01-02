from pathlib import Path
from typing import Annotated

import typer

from core import __version__
from core.utils.logging import setup_logging

app = typer.Typer(
    name="gpugo",
    help="GpuGo Agent - GPU container management",
    no_args_is_help=True,
)


@app.command()
def run(
    secret_key: Annotated[
        str, typer.Argument(envvar="GPUGO_SECRET_KEY", help="Agent secret key")
    ],
    config_file: Annotated[
        Path, typer.Option("--config", "-c", help="Config file path")
    ] = Path("config.yaml"),
    log_file: Annotated[
        Path | None, typer.Option("--log", "-l", help="Log file path")
    ] = None,
    debug: Annotated[
        bool, typer.Option("--debug", "-d", help="Enable debug logging")
    ] = False,
) -> None:
    """Run the GpuGo agent."""
    from core.models.config import Config
    from core.services.agent import Agent

    setup_logging(level="DEBUG" if debug else "INFO", log_file=log_file)

    config = Config.load(config_file) if config_file.exists() else Config.load()
    agent = Agent(secret_key=secret_key, config=config)
    agent.run()


@app.command()
def dashboard(
    agent_id: Annotated[
        str | None, typer.Option("--agent-id", "-a", help="Agent ID to display")
    ] = None,
) -> None:
    """Open the TUI dashboard."""
    from core.cli.tui.app import run_dashboard

    saved_id = ""
    agent_id_file = Path(".agent_id")
    if agent_id_file.exists():
        saved_id = agent_id_file.read_text().strip()

    run_dashboard(agent_id=agent_id or saved_id, status="offline")


@app.command()
def containers(
    action: Annotated[str, typer.Argument(help="Action: list, stop, logs")] = "list",
    name: Annotated[str | None, typer.Argument(help="Container name")] = None,
) -> None:
    """Manage containers."""
    import subprocess

    from loguru import logger

    setup_logging()

    if action == "list":
        from core.services.container import ContainerManager

        manager = ContainerManager()
        for c in manager.list_containers():
            status = "UP" if "Up" in c["status"] else "DOWN"
            logger.info(f"{c['name']}: [{status}] {c['image']}")

    elif action == "stop":
        if name:
            subprocess.run(["docker", "stop", name])
            subprocess.run(["docker", "rm", name])
            logger.info(f"Stopped and removed: {name}")
        else:
            from core.services.container import ContainerManager

            manager = ContainerManager()
            manager.stop()
            logger.info("All containers stopped")

    elif action == "logs" and name:
        subprocess.run(["docker", "logs", "-f", "--tail", "100", name])

    else:
        logger.error(f"Unknown action: {action}")


@app.command()
def status() -> None:
    """Show agent status."""
    from loguru import logger

    setup_logging()

    agent_id_file = Path(".agent_id")
    if agent_id_file.exists():
        agent_id = agent_id_file.read_text().strip()
        logger.info(f"Agent ID: {agent_id}")
    else:
        logger.info("Agent not registered yet")

    from core.services.container import ContainerManager

    manager = ContainerManager()
    containers = manager.list_containers()
    running = sum(1 for c in containers if "Up" in c["status"])
    logger.info(f"Containers: {running}/{len(containers)} running")


@app.command()
def version() -> None:
    """Show version information."""
    typer.echo(f"GpuGo Agent v{__version__}")


def main() -> None:
    """CLI entry point."""
    app()


if __name__ == "__main__":
    main()
