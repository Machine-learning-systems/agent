#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import re
import socket
import subprocess
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Settings:
    image: str = "grigoriybased/gpunix-pytorch:latest"
    name_prefix: str = "jsg"
    ssh_port_base: int = 42200   # SSH порт = 422XX
    jup_port_base: int = 42800   # Jupyter порт = 428XX
    shm_size: str = "1g"
    ulimit_stack: str = "67108864"  # 64 MiB
    runtime: str = "nvidia"  # --runtime=nvidia
    nvidia_caps: str = "compute,utility"


class ContainerManager:
    def __init__(self, settings: Settings = Settings()):
        self.s = settings

    def _run(self, args: List[str], check: bool = True, capture_output: bool = False, quiet: bool = False) -> subprocess.CompletedProcess:
        if not quiet:
            print("[RUN]", " ".join(args))
        try:
            return subprocess.run(args, check=check, capture_output=capture_output, text=True)
        except subprocess.CalledProcessError as e:
            if not quiet:
                print(f"[ERROR] Command failed with return code {e.returncode}")
            raise
        except Exception as e:
            if not quiet:
                print(f"[ERROR] Command execution failed: {e}")
            raise

    def _exists(self, name: str) -> bool:
        out = self._run(["docker", "ps", "-a", "--format", "{{.Names}}"], capture_output=True).stdout.splitlines()
        return name in out

    def _running(self, name: str) -> bool:
        out = self._run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True).stdout.splitlines()
        return name in out

    def _docker_images_has(self, image: str) -> bool:
        cp = self._run(["docker", "image", "inspect", image], check=False, capture_output=True, quiet=True)
        if cp.returncode == 0:
            print(f"[OK]   Образ найден: {image}")
            return True
        else:
            print(f"[INFO] Образ не найден локально: {image}")
            print(f"[INFO] Пытаемся загрузить образ из интернета...")
            try:
                # Пытаемся загрузить образ из интернета
                pull_result = self._run(["docker", "pull", image], check=False, capture_output=False, quiet=False)
                if pull_result.returncode == 0:
                    print(f"[OK]   Образ успешно загружен: {image}")
                    return True
                else:
                    print(f"[ERR]  Не удалось загрузить образ: {image}")
                    print(f"[ERR]  Проверьте доступность образа и подключение к интернету")
                    return False
            except Exception as e:
                print(f"[ERR]  Ошибка при загрузке образа {image}: {e}")
                return False


    def _container_name(self, xx: str) -> str:
        return f"{self.s.name_prefix}-{xx}"

    def _ports_from_xx(self, xx: str) -> tuple[int, int]:
        pid = int(xx)
        return self.s.ssh_port_base + pid, self.s.jup_port_base + pid

    def _port_free(self, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            try:
                s.bind(("127.0.0.1", port))
            except OSError:
                return False
        return True

    def _assert_ports_free(self, ssh_port: int, jup_port: int) -> None:
        bad = []
        if not self._port_free(ssh_port):
            bad.append(str(ssh_port))
        if not self._port_free(jup_port):
            bad.append(str(jup_port))
        if bad:
            raise RuntimeError(f"Порты заняты: {', '.join(bad)}")

    def _assert_port_mapping_free(self, port_mapping: dict) -> None:
        """Проверить, что все порты в маппинге свободны"""
        bad = []
        for host_port in port_mapping.keys():
            if not self._port_free(int(host_port)):
                bad.append(str(host_port))
        if bad:
            raise RuntimeError(f"Порты заняты: {', '.join(bad)}")

    def start(self, container_name: str, ssh_port: int, jup_port: int, ssh_password: str, jupyter_token: str, ssh_username: str = "root", gpus: Optional[str] = None, image: Optional[str] = None, cpuset_cpus: Optional[str] = None, memory_gb: Optional[int] = None, memory_swap_gb: Optional[int] = None, shm_size_gb: Optional[int] = None, storage_gb: Optional[int] = None) -> Optional[str]:
        """
        Запустить/создать контейнер с указанными параметрами.
        - container_name: имя контейнера
        - ssh_port: SSH порт
        - jup_port: Jupyter порт
        - ssh_password: пароль SSH
        - jupyter_token: токен Jupyter
        - ssh_username: имя пользователя SSH (по умолчанию "root" - системный пользователь)
        - gpus: GPU (по умолчанию все или список '0,2,3')
        """
        name = container_name

        if self._running(name):
            print(f"[INFO] Контейнер уже запущен: {name}")
            print(f"[INFO] SSH:     ssh -p {ssh_port} {ssh_username}@<host>  (пароль: {ssh_password})")
            print(f"[INFO] Jupyter: http://<host>:{jup_port}/lab (token:  {jupyter_token})")
            return

        if self._exists(name):
            print(f"[INFO] Контейнер существует, стартуем: {name}")
            self._run(["docker", "start", name])
            print(f"[OK]   Запущено.")
            print(f"[INFO] SSH:     ssh -p {ssh_port} {ssh_username}@<host>  (пароль: {ssh_password})")
            print(f"[INFO] Jupyter: http://<host>:{jup_port}/lab (token:  {jupyter_token})")
            return

        self._assert_ports_free(ssh_port, jup_port)

        image_to_run = image or self.s.image

        if not self._docker_images_has(image_to_run):
            raise RuntimeError(
                f"Образ '{image_to_run}' недоступен. "
                f"Проверьте подключение к интернету и доступность образа в реестре."
            )

        work_vol = f"{name}-work"
        self._run(["docker", "volume", "create", work_vol])

        # legacy GPU runtime 
        env = [
            "-e", f"SSH_PASSWORD={ssh_password}",
            "-e", f"JUPYTER_TOKEN={jupyter_token}",
            "-e", f"NVIDIA_DRIVER_CAPABILITIES={self.s.nvidia_caps}",
            "-e", f"NVIDIA_VISIBLE_DEVICES={'all' if not gpus else gpus}",
        ]

        args = [
            "docker", "run", "-d",
            "--name", name,
            "--runtime", self.s.runtime,
            "--ulimit", "memlock=-1", "--ulimit", f"stack={self.s.ulimit_stack}",
            # shm-size (overridable)
            "--shm-size", (f"{shm_size_gb}g" if shm_size_gb is not None else self.s.shm_size),
            "-p", f"{ssh_port}:22",
            "-p", f"{jup_port}:8888",
            *env,
            "-v", f"{work_vol}:/work",
            "--restart", "unless-stopped",
        ]

        # CPU pinning
        if cpuset_cpus:
            args.extend(["--cpuset-cpus", cpuset_cpus])

        # Memory limits
        if memory_gb is not None:
            args.extend(["--memory", f"{memory_gb}g"])
            # memory-swap: if not provided, pin to same value
            swap_gb = memory_swap_gb if memory_swap_gb is not None else memory_gb
            args.extend(["--memory-swap", f"{swap_gb}g"])

        # Storage size (may depend on storage driver support)
        if storage_gb is not None and storage_gb > 0:
            args.extend(["--storage-opt", f"size={storage_gb}G"])

        # Finally, the image to run
        args.append(image_to_run)
        result = self._run(args, capture_output=True)
        container_id = result.stdout.strip()

        print("[OK]   Контейнер создан и запущен.")
        print(f"[INFO] Name:    {name}")
        print(f"[INFO] SSH:     ssh -p {ssh_port} {ssh_username}@<host>  (пароль: {ssh_password})")
        print(f"[INFO] Jupyter: http://<host>:{jup_port}/lab (token:  {jupyter_token})")
        
        return container_id

    def start_with_port_mapping(self, container_name: str, port_mapping: dict, ssh_password: str, jupyter_token: str, ssh_username: str = "root", gpus: Optional[str] = None, image: Optional[str] = None, cpuset_cpus: Optional[str] = None, memory_gb: Optional[int] = None, memory_swap_gb: Optional[int] = None, shm_size_gb: Optional[int] = None, storage_gb: Optional[int] = None) -> Optional[str]:
        """
        Запустить/создать контейнер с кастомным маппингом портов.
        
        Args:
            container_name: имя контейнера
            port_mapping: словарь {host_port: container_port} (например {42560: 22, 42561: 8888, 42562: 9000})
            ssh_password: пароль SSH
            jupyter_token: токен Jupyter 
            ssh_username: имя пользователя SSH (по умолчанию "root")
            gpus: GPU (по умолчанию все или список '0,2,3')
            остальные параметры аналогично start()
        
        Returns:
            container_id или None при ошибке
        """
        name = container_name

        # Найдем SSH и Jupyter порты для логирования
        ssh_port = None
        jup_port = None
        for host_port, container_port in port_mapping.items():
            if container_port == 22:
                ssh_port = host_port
            elif container_port == 8888:
                jup_port = host_port

        if self._running(name):
            print(f"[INFO] Контейнер уже запущен: {name}")
            if ssh_port:
                print(f"[INFO] SSH:     ssh -p {ssh_port} {ssh_username}@<host>  (пароль: {ssh_password})")
            if jup_port:
                print(f"[INFO] Jupyter: http://<host>:{jup_port}/lab (token:  {jupyter_token})")
            return

        if self._exists(name):
            print(f"[INFO] Контейнер существует, стартуем: {name}")
            self._run(["docker", "start", name])
            print("[OK]   Запущено.")
            if ssh_port:
                print(f"[INFO] SSH:     ssh -p {ssh_port} {ssh_username}@<host>  (пароль: {ssh_password})")
            if jup_port:
                print(f"[INFO] Jupyter: http://<host>:{jup_port}/lab (token:  {jupyter_token})")
            return

        # Проверяем, что все порты свободны
        self._assert_port_mapping_free(port_mapping)

        image_to_run = image or self.s.image

        if not self._docker_images_has(image_to_run):
            raise RuntimeError(
                f"Образ '{image_to_run}' недоступен. "
                f"Проверьте подключение к интернету и доступность образа в реестре."
            )

        work_vol = f"{name}-work"
        self._run(["docker", "volume", "create", work_vol])

        env = [
            "-e", f"SSH_PASSWORD={ssh_password}",
            "-e", f"JUPYTER_TOKEN={jupyter_token}",
            "-e", f"NVIDIA_DRIVER_CAPABILITIES={self.s.nvidia_caps}",
            "-e", f"NVIDIA_VISIBLE_DEVICES={'all' if not gpus else gpus}",
        ]

        args = [
            "docker", "run", "-d",
            "--name", name,
            "--runtime", self.s.runtime,
            "--ulimit", "memlock=-1", "--ulimit", f"stack={self.s.ulimit_stack}",
            # shm-size (overridable)
            "--shm-size", (f"{shm_size_gb}g" if shm_size_gb is not None else self.s.shm_size),
        ]
        
        # Добавляем все порты из маппинга
        for host_port, container_port in port_mapping.items():
            args.extend(["-p", f"{host_port}:{container_port}"])
        
        args.extend(env)
        args.extend(["-v", f"{work_vol}:/work", "--restart", "unless-stopped"])

        # CPU pinning
        if cpuset_cpus:
            args.extend(["--cpuset-cpus", cpuset_cpus])

        # Memory limits
        if memory_gb is not None:
            args.extend(["--memory", f"{memory_gb}g"])
            # memory-swap: if not provided, pin to same value
            swap_gb = memory_swap_gb if memory_swap_gb is not None else memory_gb
            args.extend(["--memory-swap", f"{swap_gb}g"])

        # Storage size (may depend on storage driver support)
        if storage_gb is not None and storage_gb > 0:
            args.extend(["--storage-opt", f"size={storage_gb}G"])

        # Finally, the image to run
        args.append(image_to_run)
        result = self._run(args, capture_output=True)
        container_id = result.stdout.strip()

        print("[OK]   Контейнер создан и запущен.")
        print(f"[INFO] Name:    {name}")
        if ssh_port:
            print(f"[INFO] SSH:     ssh -p {ssh_port} {ssh_username}@<host>  (пароль: {ssh_password})")
        if jup_port:
            print(f"[INFO] Jupyter: http://<host>:{jup_port}/lab (token:  {jupyter_token})")
        
        # Логируем все порты
        print(f"[INFO] Порты:   {dict(port_mapping)}")
        
        return container_id

    def stop(self, container_name: Optional[str] = None) -> None:
        """
        Остановить и удалить:
            - все контейнеры (stop())
            - или один контейнер (stop('my-container'))
        """
        if container_name is None:
            # Соберём все контейнеры
            cp = self._run(["docker", "ps", "-a", "--format", "{{.Names}}"], capture_output=True)
            names = cp.stdout.splitlines()
            if not names:
                print("[INFO] Нет контейнеров")
                return
            # Сначала остановим те, что запущены
            running = [n for n in names if self._running(n)]
            if running:
                self._run(["docker", "stop", *running])
            # Потом удалим все найденные
            self._run(["docker", "rm", *names])
            print(f"[OK]   Удалено контейнеров: {len(names)}")
        else:
            # Остановим, если запущен
            if self._running(container_name):
                self._run(["docker", "stop", container_name])
            # Удалим, если существует
            if self._exists(container_name):
                self._run(["docker", "rm", container_name])
                print("[OK]   Контейнер удалён:", container_name)
            else:
                print("[INFO] Контейнер не найден:", container_name)

    def stop_by_id(self, container_id: str) -> bool:
        """
        Остановить контейнер по ID/имени. Идемпотентно: если уже остановлен или не найден — считаем успехом.
        Возвращает True при успешной/идемпотентной остановке, иначе False.
        """
        try:
            cp = self._run(["docker", "stop", container_id], check=False, capture_output=True, quiet=True)
            if cp.returncode == 0:
                return True
            err_out = f"{cp.stderr or ''}{cp.stdout or ''}"
            # Если контейнер уже не найден или не запущен — операция идемпотентна
            if "No such container" in err_out or "is not running" in err_out:
                return True
            print(f"[ERROR] docker stop failed for {container_id}: {err_out.strip()}")
            return False
        except Exception as e:
            print(f"[ERROR] Exception while stopping {container_id}: {e}")
            return False

    def remove_by_id(self, container_id: str) -> bool:
        """
        Удалить контейнер по ID/имени. Идемпотентно: если контейнера нет — считаем успехом.
        Возвращает True при успешном/идемпотентном удалении, иначе False.
        """
        try:
            cp = self._run(["docker", "rm", container_id], check=False, capture_output=True, quiet=True)
            if cp.returncode == 0:
                return True
            err_out = f"{cp.stderr or ''}{cp.stdout or ''}"
            if "No such container" in err_out:
                return True
            print(f"[ERROR] docker rm failed for {container_id}: {err_out.strip()}")
            return False
        except Exception as e:
            print(f"[ERROR] Exception while removing {container_id}: {e}")
            return False

    def wait_for_ssh_ready(self, host: str, port: int, timeout: int = 60) -> bool:
        """Ждет, пока SSH сервис будет готов к подключению"""
        import time
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(2)
                    result = s.connect_ex((host, port))
                    if result == 0:
                        return True
            except:
                pass
            time.sleep(2)
        return False

    def check_and_install_docker(self) -> bool:
        """Проверяет и устанавливает Docker если необходимо"""
        try:
            # Проверяем, работает ли Docker
            result = subprocess.run(['docker', 'ps'], check=True, capture_output=True)
            print("[INFO] Docker is working correctly")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("[INFO] Docker not working, attempting to fix...")
            
            # Проверяем, установлен ли Docker
            try:
                subprocess.run(['docker', '--version'], check=True, capture_output=True)
                print("[INFO] Docker is installed but not working")
                
                # Исправляем права
                if self.fix_docker_permissions():
                    print("[INFO] Docker permissions fixed successfully")
                    return True
                else:
                    print("[WARNING] Could not fix Docker permissions")
                    return False
                    
            except (subprocess.CalledProcessError, FileNotFoundError):
                print("[INFO] Docker not found, please install Docker manually")
                return False

    def fix_docker_permissions(self) -> bool:
        """Исправляет права доступа к Docker daemon"""
        import time
        try:
            print("[INFO] Checking Docker permissions...")
            
            # Проверяем, работает ли Docker без sudo
            try:
                result = subprocess.run(['docker', 'ps'], capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    print("[INFO] Docker permissions are OK")
                    return True
            except:
                pass
            
            # Пытаемся исправить права
            print("[INFO] Fixing Docker permissions...")
            
            # Добавляем текущего пользователя в группу docker
            try:
                current_user = subprocess.check_output(['whoami']).decode().strip()
                subprocess.run(['sudo', 'usermod', '-aG', 'docker', current_user], check=True)
                print(f"[INFO] Added user {current_user} to docker group")
            except Exception as e:
                print(f"[WARNING] Failed to add user to docker group: {e}")
            
            # Перезапускаем Docker service
            try:
                subprocess.run(['sudo', 'systemctl', 'restart', 'docker'], check=True)
                print("[INFO] Docker service restarted")
            except Exception as e:
                print(f"[WARNING] Failed to restart Docker service: {e}")
            
            # Ждем немного и проверяем снова
            time.sleep(3)
            
            # Проверяем Docker без sudo
            try:
                result = subprocess.run(['docker', 'ps'], capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    print("[INFO] Docker permissions fixed successfully")
                    return True
            except:
                pass
            
            return False
            
        except Exception as e:
            print(f"[ERROR] Failed to fix Docker permissions: {e}")
            return False

    def check_docker_gpu_support(self) -> bool:
        """Проверяет поддержку GPU в Docker"""
        try:
            print("[INFO] Checking Docker GPU support...")
            
            # Проверяем наличие nvidia-container-toolkit
            try:
                result = subprocess.run(['nvidia-container-cli', 'info'], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    print("[INFO] nvidia-container-toolkit found")
                    
                    # Проверяем, работает ли --gpus флаг
                    try:
                        result = subprocess.run(['docker', 'run', '--rm', '--gpus', 'all', 'ubuntu:20.04', 'nvidia-smi'], 
                                              capture_output=True, text=True, timeout=30)
                        if result.returncode == 0:
                            print("[INFO] Docker GPU support confirmed with --gpus flag")
                            return True
                    except:
                        pass
                    
                    # Проверяем --runtime=nvidia
                    try:
                        result = subprocess.run(['docker', 'run', '--rm', '--runtime=nvidia', 'ubuntu:20.04', 'nvidia-smi'], 
                                              capture_output=True, text=True, timeout=30)
                        if result.returncode == 0:
                            print("[INFO] Docker GPU support confirmed with --runtime=nvidia")
                            return True
                    except:
                        pass
                    
                    print("[WARNING] nvidia-container-toolkit found but GPU access not working")
                    return False
            except:
                pass

            # Проверяем наличие nvidia-docker
            try:
                result = subprocess.run(['docker', 'run', '--rm', '--runtime=nvidia', 'ubuntu:20.04', 'nvidia-smi'], 
                                      capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    print("[INFO] Docker GPU support confirmed with nvidia-docker")
                    return True
            except:
                pass
            
            print("[WARNING] Docker GPU support not available")
            return False
        except Exception as e:
            print(f"[WARNING] Docker GPU support check failed: {e}")
            return False


def _parse_cli() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("start", help="start container with specified parameters")
    sp.add_argument("container_name", help="имя контейнера")
    sp.add_argument("ssh_port", type=int, help="SSH порт")
    sp.add_argument("jup_port", type=int, help="Jupyter порт")
    sp.add_argument("ssh_password", help="пароль SSH")
    sp.add_argument("jupyter_token", help="токен Jupyter")
    sp.add_argument("--ssh_username", default="root", help="имя пользователя SSH (по умолчанию: root)")
    sp.add_argument("--gpus", default=None, help="список GPU, напр. '0,2,3'. По умолчанию: все(all)")

    sp2 = sub.add_parser("stop", help="stop and remove containers")
    sp2.add_argument("container_name", nargs="?", default=None, help="имя контейнера (если не указано — все контейнеры)")

    return p.parse_args()


def main() -> None:
    args = _parse_cli()
    mgr = ContainerManager()

    if args.cmd == "start":
        mgr.start(args.container_name, args.ssh_port, args.jup_port, args.ssh_password, args.jupyter_token, 
                 ssh_username=args.ssh_username, gpus=args.gpus)
    elif args.cmd == "stop":
        mgr.stop(args.container_name)
    else:
        raise SystemExit("Unknown command")


if __name__ == "__main__":
    main()

"""
CLI:
    python clean_manager.py start my-container 2222 2223 mypass mytoken            # все GPU, пользователь root
    python clean_manager.py start my-container 2222 2223 mypass mytoken --gpus 0,2,3  # только указанные GPU
    python clean_manager.py start my-container 2222 2223 mypass mytoken --ssh_username dev  # с другим пользователем
    python clean_manager.py stop                # остановить и удалить ВСЕ контейнеры
    python clean_manager.py stop my-container   # остановить и удалить конкретный контейнер
Если предварительно прописать chmod +x clean_manager.py, то можно запускать так:
    ./clean_manager.py start my-container 2222 2223 mypass mytoken ...

As a library:
    from clean_manager import ContainerManager
    m = ContainerManager()
    m.start("my-container", 2222, 2223, "mypass", "mytoken", ssh_username="root", gpus="0,2")
    m.stop("my-container")
"""

