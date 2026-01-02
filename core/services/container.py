import socket
import subprocess
import time
from dataclasses import dataclass

from loguru import logger

from core.models.config import Config
from core.models.task import ServiceConfig


@dataclass
class ContainerStartResult:
    container_id: str
    container_name: str
    port_mapping: dict[int, int]


class ContainerManager:
    def __init__(self, config: Config | None = None):
        self.config = config or Config.load()

    def _run(
        self,
        args: list[str],
        check: bool = True,
        capture_output: bool = False,
        quiet: bool = False,
    ) -> subprocess.CompletedProcess:
        if not quiet:
            logger.debug(f"Running: {' '.join(args)}")
        return subprocess.run(
            args, check=check, capture_output=capture_output, text=True
        )

    def _exists(self, name: str) -> bool:
        out = self._run(
            ["docker", "ps", "-a", "--format", "{{.Names}}"],
            capture_output=True,
            quiet=True,
        ).stdout.splitlines()
        return name in out

    def _running(self, name: str) -> bool:
        out = self._run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            quiet=True,
        ).stdout.splitlines()
        return name in out

    def _ensure_image(self, image: str) -> bool:
        cp = self._run(
            ["docker", "image", "inspect", image],
            check=False,
            capture_output=True,
            quiet=True,
        )
        if cp.returncode == 0:
            logger.info(f" Image found: {image}")
            return True

        logger.info(f" Image not found locally: {image}")
        logger.info(" Pulling image...")
        pull_result = self._run(
            ["docker", "pull", image],
            check=False,
            capture_output=False,
            quiet=False,
        )
        if pull_result.returncode == 0:
            logger.info(f" Image pulled: {image}")
            return True

        logger.error(f" Failed to pull image: {image}")
        return False

    def _port_free(self, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            try:
                s.bind(("127.0.0.1", port))
                return True
            except OSError:
                return False

    def _assert_ports_free(self, port_mapping: dict[int, int]) -> None:
        bad = [str(p) for p in port_mapping if not self._port_free(p)]
        if bad:
            raise RuntimeError(f"Ports busy: {', '.join(bad)}")

    def start(
        self,
        name: str,
        image: str,
        port_mapping: dict[int, int],
        password: str,
        token: str | None = None,
        gpus: str | None = None,
        cpuset_cpus: str | None = None,
        memory_gb: int | None = None,
        storage_gb: int | None = None,
        shm_size_gb: int | None = None,
        services: ServiceConfig | None = None,
    ) -> ContainerStartResult:
        if self._running(name):
            logger.info(f" Container already running: {name}")
            container_id = self._get_container_id(name)
            return ContainerStartResult(
                container_id=container_id or name,
                container_name=name,
                port_mapping=port_mapping,
            )

        if self._exists(name):
            logger.info(f" Container exists, starting: {name}")
            self._run(["docker", "start", name])
            container_id = self._get_container_id(name)
            return ContainerStartResult(
                container_id=container_id or name,
                container_name=name,
                port_mapping=port_mapping,
            )

        self._assert_ports_free(port_mapping)

        if not self._ensure_image(image):
            raise RuntimeError(f"Image unavailable: {image}")

        work_vol = f"{name}-work"
        self._run(["docker", "volume", "create", work_vol], quiet=True)

        args = self._build_docker_command(
            name=name,
            image=image,
            port_mapping=port_mapping,
            password=password,
            token=token or password,
            gpus=gpus,
            cpuset_cpus=cpuset_cpus,
            memory_gb=memory_gb,
            storage_gb=storage_gb,
            shm_size_gb=shm_size_gb,
            work_vol=work_vol,
            services=services,
        )

        result = self._run(args, capture_output=True)
        container_id = result.stdout.strip()

        logger.info(f" Container started: {name}")
        return ContainerStartResult(
            container_id=container_id,
            container_name=name,
            port_mapping=port_mapping,
        )

    def _build_docker_command(
        self,
        name: str,
        image: str,
        port_mapping: dict[int, int],
        password: str,
        token: str,
        gpus: str | None,
        cpuset_cpus: str | None,
        memory_gb: int | None,
        storage_gb: int | None,
        shm_size_gb: int | None,
        work_vol: str,
        services: ServiceConfig | None,
    ) -> list[str]:
        cfg = self.config.container

        args = [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--ipc",
            "private",
            "--ulimit",
            "memlock=-1",
            "--ulimit",
            f"stack={cfg.ulimit_stack}",
            "--shm-size",
            f"{shm_size_gb}g" if shm_size_gb else cfg.shm_size,
        ]

        match gpus:
            case "all":
                args.extend(["--gpus", "all"])
            case str() as indices if indices:
                args.extend(["--gpus", f"device={indices}"])
            case _:
                pass

        for host_port, container_port in port_mapping.items():
            args.extend(["-p", f"{host_port}:{container_port}"])

        args.extend([
            "-e",
            f"SSH_PASSWORD={password}",
            "-e",
            f"JUPYTER_TOKEN={token}",
            "-e",
            f"CODE_SERVER_PASSWORD={token}",
            "-e",
            f"NVIDIA_DRIVER_CAPABILITIES={self.config.nvidia.capabilities}",
        ])

        if services:
            if not services.enable_ssh:
                args.extend(["-e", "DISABLE_SSH=1"])
            if not services.enable_jupyter:
                args.extend(["-e", "DISABLE_JUPYTER=1"])
            if not services.enable_code_server:
                args.extend(["-e", "DISABLE_CODE_SERVER=1"])
            if services.enable_comfyui:
                args.extend(["-e", "ENABLE_COMFYUI=true"])

        if cpuset_cpus:
            args.extend(["--cpuset-cpus", cpuset_cpus])

        if memory_gb is not None:
            args.extend(["--memory", f"{memory_gb}g"])
            args.extend(["--memory-swap", f"{memory_gb}g"])

        if storage_gb and storage_gb > 0:
            args.extend(["--storage-opt", f"size={storage_gb}G"])

        args.extend([
            "-v",
            f"{work_vol}:/work",
            "--restart",
            cfg.restart_policy,
        ])

        args.append(image)
        return args

    def _get_container_id(self, name: str) -> str | None:
        result = self._run(
            ["docker", "inspect", "--format", "{{.Id}}", name],
            check=False,
            capture_output=True,
            quiet=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()[:12]
        return None

    def stop(self, name: str | None = None) -> None:
        if name is None:
            cp = self._run(
                ["docker", "ps", "-a", "--format", "{{.Names}}"],
                capture_output=True,
                quiet=True,
            )
            names = cp.stdout.splitlines()
            if not names:
                logger.info(" No containers")
                return

            running = [n for n in names if self._running(n)]
            if running:
                self._run(["docker", "stop", *running])
            self._run(["docker", "rm", *names])
            logger.info(f" Removed {len(names)} containers")
        else:
            if self._running(name):
                self._run(["docker", "stop", name])
            if self._exists(name):
                self._run(["docker", "rm", name])
                logger.info(f" Removed: {name}")
            else:
                logger.info(f" Not found: {name}")

    def stop_by_id(self, container_id: str) -> bool:
        cp = self._run(
            ["docker", "stop", container_id],
            check=False,
            capture_output=True,
            quiet=True,
        )
        if cp.returncode == 0:
            return True

        err_out = f"{cp.stderr or ''}{cp.stdout or ''}"
        if "No such container" in err_out or "is not running" in err_out:
            return True

        logger.error(f" docker stop failed for {container_id}: {err_out.strip()}")
        return False

    def remove_by_id(self, container_id: str) -> bool:
        cp = self._run(
            ["docker", "rm", container_id],
            check=False,
            capture_output=True,
            quiet=True,
        )
        if cp.returncode == 0:
            return True

        err_out = f"{cp.stderr or ''}{cp.stdout or ''}"
        if "No such container" in err_out:
            return True

        logger.error(f" docker rm failed for {container_id}: {err_out.strip()}")
        return False

    def restart_by_id(self, container_id: str) -> bool:
        cp = self._run(
            ["docker", "restart", container_id],
            check=False,
            capture_output=True,
            quiet=True,
        )
        if cp.returncode == 0:
            return True

        logger.error(f" docker restart failed: {cp.stderr or cp.stdout}")
        return False

    def list_containers(self, prefix: str = "task_") -> list[dict]:
        result = self._run(
            [
                "docker",
                "ps",
                "-a",
                "--format",
                "{{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Ports}}",
            ],
            capture_output=True,
            quiet=True,
        )
        containers = []
        for line in result.stdout.strip().split("\n"):
            if not line or not line.startswith(prefix):
                continue
            parts = line.split("\t")
            if len(parts) >= 4:
                containers.append({
                    "name": parts[0],
                    "status": parts[1],
                    "image": parts[2],
                    "ports": parts[3],
                })
        return containers

    def check_and_install_docker(self) -> bool:
        try:
            subprocess.run(["docker", "ps"], check=True, capture_output=True)
            logger.info("Docker is working correctly")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.info("Docker not working")

            try:
                subprocess.run(["docker", "--version"], check=True, capture_output=True)
                logger.info("Docker is installed but not working")
                return self.fix_docker_permissions()
            except (subprocess.CalledProcessError, FileNotFoundError):
                logger.info("Docker not found")
                return False

    def fix_docker_permissions(self) -> bool:
        try:
            result = subprocess.run(
                ["docker", "ps"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                logger.info(" Docker permissions OK")
                return True
        except Exception:
            pass

        logger.info(" Fixing Docker permissions...")
        try:
            current_user = subprocess.check_output(["whoami"]).decode().strip()
            subprocess.run(
                ["sudo", "usermod", "-aG", "docker", current_user],
                check=True,
            )
            logger.info(f" Added {current_user} to docker group")
        except Exception as e:
            logger.warning(f" Failed to add user to docker group: {e}")

        try:
            subprocess.run(["sudo", "systemctl", "restart", "docker"], check=True)
            logger.info(" Docker service restarted")
        except Exception as e:
            logger.warning(f" Failed to restart Docker: {e}")

        time.sleep(3)

        try:
            result = subprocess.run(
                ["docker", "ps"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                logger.info(" Docker permissions fixed")
                return True
        except Exception:
            pass

        return False

    def check_docker_gpu_support(self) -> bool:
        logger.info(" Checking Docker GPU support...")

        try:
            result = subprocess.run(
                ["nvidia-container-cli", "info"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                logger.info(" nvidia-container-toolkit found")

                try:
                    result = subprocess.run(
                        [
                            "docker",
                            "run",
                            "--rm",
                            "--gpus",
                            "all",
                            "ubuntu:20.04",
                            "nvidia-smi",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    if result.returncode == 0:
                        logger.info(" Docker GPU support confirmed with --gpus flag")
                        return True
                except Exception:
                    pass

                logger.warning(
                    "nvidia-container-toolkit found but GPU access not working"
                )
                return False
        except Exception:
            pass

        logger.warning(" Docker GPU support not available")
        return False
