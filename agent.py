#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os
import time
import json
import psutil
import threading
import subprocess
import socket
import re
from typing import Dict, Any, Optional

from hardware_analyzer import HardwareAnalyzer
from api_client import APIClient
from clean_manager import ContainerManager

# Константы
AGENT_ID_FILE = ".agent_id"


class Agent:
    """Основной класс агента"""
    
    def __init__(self, secret_key: str, base_url: str = "https://api.gpugo.ru"):
        self.secret_key = secret_key
        self.base_url = base_url
        self.agent_id = None
        
        # Инициализируем компоненты
        self.hardware_analyzer = HardwareAnalyzer()
        self.api_client = APIClient(base_url=base_url, secret_key=secret_key)
        self.container_manager = ContainerManager()
        
        # Загружаем сохраненный agent_id
        self._load_agent_id()
    
    def _load_agent_id(self):
        """Загружает сохраненный agent_id из файла"""
        if os.path.exists(AGENT_ID_FILE):
            with open(AGENT_ID_FILE, "r") as f:
                self.agent_id = f.read().strip()
                print(f"[INFO] Loaded agent_id from {AGENT_ID_FILE}: {self.agent_id}")
                self.api_client.set_credentials(self.agent_id, self.secret_key)
    
    def _save_agent_id(self, agent_id: str):
        """Сохраняет agent_id в файл"""
        with open(AGENT_ID_FILE, "w") as f:
            f.write(str(agent_id))
        print(f"[INFO] Saved agent_id to {AGENT_ID_FILE}: {agent_id}")
    
    def get_gpu_usage(self) -> Dict[str, Any]:
        """Получение использования GPU"""
        gpu_usage = {}
        
        try:
            total_usage = 0
            gpu_count = 0
            
            # Попробуем получить информацию через nvidia-smi для NVIDIA
            try:
                nvidia_output = subprocess.check_output(['nvidia-smi', '--query-gpu=name,utilization.gpu', '--format=csv,noheader'], stderr=subprocess.DEVNULL).decode(errors='ignore')
                for line in nvidia_output.strip().split('\n'):
                    if line:
                        parts = line.split(',')
                        if len(parts) >= 2:
                            gpu_name = parts[0].strip()
                            usage_str = parts[1].strip()
                            usage_match = re.search(r'(\d+)', usage_str)
                            if usage_match:
                                usage = int(usage_match.group(1))
                                total_usage += usage
                                gpu_count += 1
                                gpu_usage[gpu_name] = usage
            except:
                pass
            
            # Вычисляем среднее использование
            if gpu_count > 0:
                avg_usage = total_usage / gpu_count
                gpu_usage["average"] = round(avg_usage, 1)
                
        except Exception as e:
            print(f"[WARNING] GPU usage detection error: {e}")
        
        return gpu_usage
    
    def get_network_usage(self) -> Dict[str, Any]:
        """Получение использования сети"""
        usage = {}
        
        try:
            # Получаем статистику сети
            counters = psutil.net_io_counters(pernic=True)
            
            # Для Linux используем простой подход
            if os.name == 'posix':
                # Запоминаем начальные значения
                counters_before = {}
                for iface, stats in counters.items():
                    counters_before[iface] = stats.bytes_sent + stats.bytes_recv
                
                # Ждем 0.5 секунды
                time.sleep(0.5)
                
                # Получаем новые значения
                counters_after = psutil.net_io_counters(pernic=True)
                
                # Вычисляем использование для каждого интерфейса
                for iface in counters:
                    if iface in counters_before and iface in counters_after:
                        before = counters_before[iface]
                        after = counters_after[iface].bytes_sent + counters_after[iface].bytes_recv
                        delta_bytes = after - before
                        
                        # Конвертируем в мегабиты в секунду
                        delta_mbps = (delta_bytes * 8 * 2) / (1024 * 1024)
                        usage[iface] = round(delta_mbps, 2)
                    else:
                        usage[iface] = 0.0
            else:
                # Для других систем используем базовый подход
                for iface in counters:
                    usage[iface] = 0.0
                    
        except Exception as e:
            print(f"[WARNING] Network usage calculation error: {e}")
            usage = {}
        
        return usage
    
    def get_cpu_temperature(self) -> Optional[int]:
        """Get CPU temperature in Celsius as integer"""
        temperature = None
        
        try:
            if os.name == 'posix':
                # Попробуем несколько методов для Linux
                temperature_sources = [
                    "/sys/class/thermal/thermal_zone0/temp",
                    "/sys/class/hwmon/hwmon0/temp1_input",
                    "/sys/class/hwmon/hwmon1/temp1_input",
                ]
                
                for source in temperature_sources:
                    try:
                        with open(source, 'r') as f:
                            temp_raw = f.read().strip()
                            if temp_raw.isdigit():
                                temperature = int(int(temp_raw) / 1000)  # Convert from millidegrees to integer
                                break
                    except:
                        continue
                
                # Если не удалось через файлы, попробуем через sensors
                if temperature is None:
                    try:
                        sensors_output = subprocess.check_output(['sensors'], stderr=subprocess.DEVNULL).decode(errors='ignore')
                        temp_match = re.search(r'Core 0:\s*\+(\d+(?:\.\d+)?)°C', sensors_output)
                        if temp_match:
                            temperature = int(float(temp_match.group(1)))
                    except:
                        pass
                        
        except Exception as e:
            print(f"[WARNING] Failed to get CPU temperature: {e}")
        
        return temperature
    
    def collect_system_data(self) -> Dict[str, Any]:
        """Собирает полные данные о системе"""
        print("[INFO] Collecting system information...")
        
        try:
            # Получаем системную информацию
            system_info = self.hardware_analyzer.get_system_info()
            
            # Получаем данные мониторинга
            cpu_usage = psutil.cpu_percent()
            memory_usage = psutil.virtual_memory().percent
            
            # Получаем информацию о диске
            disk_usage = {}
            try:
                disk_usage = {"/": psutil.disk_usage('/').percent}
            except:
                pass
            
            # Получаем GPU usage
            gpu_usage_data = self.get_gpu_usage()
            gpu_usage = gpu_usage_data.get("average", 0) if gpu_usage_data else 0
            
            # Получаем network usage
            network_usage = self.get_network_usage()
            
            # Получаем CPU temperature
            cpu_temperature = self.get_cpu_temperature()
            
            # Получаем IP адрес и определяем локацию
            ip_address = self.hardware_analyzer.get_ip_address()
            if ip_address:
                location = self.hardware_analyzer.get_location_from_ip(ip_address)
                print(f"[INFO] Detected location: {location} (IP: {ip_address})")
            else:
                location = "Unknown"
                print("[WARNING] Could not detect IP address, using 'Unknown' location")
            
            # Формируем полные данные
            data = {
                **system_info,
                "location": location,
                "status": "online",
                "cpu_usage": cpu_usage,
                "memory_usage": memory_usage,
                "gpu_usage": gpu_usage,
                "disk_usage": disk_usage,
                "network_usage": network_usage,
                "cpu_temperature": cpu_temperature,
            }
            
            print("[INFO] System information collected successfully")
            return data
            
        except Exception as e:
            print(f"[ERROR] Failed to collect system info: {e}")
            # Возвращаем базовые данные в случае ошибки
            return {
                "hostname": "unknown",
                "ip_address": "unknown",
                "total_ram_gb": 0,
                "ram_type": "unknown",
                "hardware_info": {},
                "location": "Unknown",
                "status": "online",
                "cpu_usage": 0,
                "memory_usage": 0,
                "gpu_usage": 0,
                "disk_usage": {},
                "network_usage": {},
                "cpu_temperature": None,
            }
    
    def collect_monitoring_data(self) -> Dict[str, Any]:
        """Собирает данные мониторинга для heartbeat"""
        try:
            cpu_usage = psutil.cpu_percent()
            memory_usage = psutil.virtual_memory().percent
            
            # Получаем информацию о диске
            disk_usage = {}
            try:
                disk_usage = {"/": psutil.disk_usage('/').percent}
            except:
                pass
            
            # Получаем GPU usage
            gpu_usage_data = self.get_gpu_usage()
            gpu_usage = {}
            if gpu_usage_data:
                for gpu_id, usage in gpu_usage_data.items():
                    if gpu_id != "average":
                        gpu_usage[f"gpu{gpu_id}"] = usage
            
            # Получаем network usage
            network_usage = self.get_network_usage()
            net_up_mbps = sum(network_usage.values()) if network_usage else 0
            net_down_mbps = net_up_mbps  # Упрощенная версия
            
            return {
                "gpu_usage": gpu_usage,
                "cpu_usage": cpu_usage,
                "memory_usage": memory_usage,
                "disk_usage": disk_usage,
                "network_usage": {
                    "up_mbps": net_up_mbps,
                    "down_mbps": net_down_mbps
                }
            }
            
        except Exception as e:
            print(f"[ERROR] Failed to collect monitoring data: {e}")
            return {
                "gpu_usage": {},
                "cpu_usage": 0,
                "memory_usage": 0,
                "disk_usage": {},
                "network_usage": {"up_mbps": 0, "down_mbps": 0}
            }
    
    def process_task(self, task: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Обрабатывает полученную задачу"""
        try:
            print(f"[INFO] Processing task: {task.get('id')}")
            
            task_data = task.get('task_data', {})
            container_info = task.get('container_info', {})

            # Обработка управляющих операций: stop / stop_remove
            operation = (task_data.get('operation') or '').strip().lower()
            if operation in {'stop', 'stop_remove'}:
                container_id = task_data.get('container_id') or container_info.get('container_id')
                container_name = task_data.get('container_name') or container_info.get('container_name')
                if not container_id:
                    print("[ERROR] CONTROL task missing container_id")
                    try:
                        self.api_client.send_log("control task error: missing container_id")
                    except Exception:
                        pass
                    return {
                        'status': 'failed',
                        'container_id': '',
                        'container_name': container_name,
                        'error_message': 'Missing container_id in control task'
                    }

                print(f"[INFO] Control operation: {operation} for container_id={container_id}")
                try:
                    self.api_client.send_log(f"control task received: op={operation} container_id={container_id}")
                except Exception:
                    pass
                stop_ok = self.container_manager.stop_by_id(container_id)
                remove_ok = True
                if operation == 'stop_remove':
                    remove_ok = self.container_manager.remove_by_id(container_id)

                if stop_ok and remove_ok:
                    try:
                        self.api_client.send_log(f"control task completed: op={operation} container_id={container_id}")
                    except Exception:
                        pass
                    return {
                        'status': 'completed',
                        'container_id': container_id,
                        'container_name': container_name
                    }
                else:
                    err = []
                    if not stop_ok:
                        err.append('stop failed')
                    if operation == 'stop_remove' and not remove_ok:
                        err.append('remove failed')
                    try:
                        self.api_client.send_log(f"control task failed: op={operation} container_id={container_id} error={', '.join(err) or 'unknown'}")
                    except Exception:
                        pass
                    return {
                        'status': 'failed',
                        'container_id': container_id,
                        'container_name': container_name,
                        'error_message': ", ".join(err) or 'unknown error'
                    }
            
            # Получаем docker_image и ресурсы из task_data (для START)
            docker_image = task_data.get('docker_image')
            if not docker_image:
                print("[ERROR] No docker_image specified in task")
                try:
                    self.api_client.send_log("task error: docker_image not specified")
                except Exception:
                    pass
                return None

            # GPU allocation
            gpu_required = task_data.get('gpu_required', 0) or 0
            gpu_indices = task_data.get('gpu_enabled_indices') or []
            gpus_param = None
            if gpu_required and isinstance(gpu_indices, list) and len(gpu_indices) > 0:
                try:
                    gpus_param = ",".join(str(int(i)) for i in gpu_indices)
                except Exception:
                    gpus_param = "all"
            elif gpu_required:
                gpus_param = "all"

            # CPU allocation: ranges to cpuset string
            cpu_allocated_ranges = task_data.get('cpu_allocated_ranges') or []
            cpuset_cpus = None
            if isinstance(cpu_allocated_ranges, list) and len(cpu_allocated_ranges) > 0:
                try:
                    ranges = []
                    for r in cpu_allocated_ranges:
                        if isinstance(r, (list, tuple)) and len(r) == 2:
                            start, end = int(r[0]), int(r[1])
                            ranges.append(f"{start}-{end}")
                    if ranges:
                        cpuset_cpus = ",".join(ranges)
                except Exception:
                    cpuset_cpus = None

            # RAM and storage
            ram_allocated_gb = task_data.get('ram_allocated_gb')
            storage_allocated_gb = task_data.get('storage_allocated_gb')
            try:
                memory_gb = int(ram_allocated_gb) if ram_allocated_gb is not None else None
            except Exception:
                memory_gb = None
            try:
                storage_gb = int(storage_allocated_gb) if storage_allocated_gb is not None else None
            except Exception:
                storage_gb = None

            # shm-size: int(RAM/2), если RAM задан
            shm_size_gb = None
            if memory_gb is not None and memory_gb > 0:
                try:
                    shm_size_gb = max(1, int(memory_gb / 2))
                except Exception:
                    shm_size_gb = None
            
            # Получаем SSH credentials из container_info
            # Username теперь опционален и всегда используем "root" как значение по умолчанию
            ssh_username = container_info.get('ssh_username') or "root"
            ssh_password = container_info.get('ssh_password')
            ssh_port = container_info.get('ssh_port')
            ssh_host = container_info.get('ssh_host')
            
            # Проверяем наличие port_mapping для новой логики
            port_mapping = container_info.get('port_mapping')
            
            if port_mapping and isinstance(port_mapping, dict):
                # Новая логика с port_mapping
                print(f"[INFO] Using port mapping: {port_mapping}")
                
                if not ssh_password:
                    print("[ERROR] Missing SSH password in container_info")
                    try:
                        self.api_client.send_log("task error: missing ssh password")
                    except Exception:
                        pass
                    return None
                
                # Формируем имя контейнера
                task_id = task.get('id', int(time.time()))
                container_name = f"task_{task_id}"
                
                # Используем новую функцию ContainerManager
                try:
                    self.api_client.send_log(f"task start requested: id={task_id} image={docker_image}")
                except Exception:
                    pass
                    
                container_id = self.container_manager.start_with_port_mapping(
                    container_name=container_name,
                    port_mapping=port_mapping,
                    ssh_password=ssh_password,
                    jupyter_token=ssh_password,  # Используем тот же пароль для Jupyter
                    ssh_username=ssh_username,
                    gpus=gpus_param,
                    image=docker_image,
                    cpuset_cpus=cpuset_cpus,
                    memory_gb=memory_gb,
                    memory_swap_gb=memory_gb,
                    shm_size_gb=shm_size_gb,
                    storage_gb=storage_gb
                )
                
                # Находим SSH порт в маппинге для результата
                ssh_port_result = None
                for host_port, container_port in port_mapping.items():
                    if container_port == 22:
                        ssh_port_result = host_port
                        break
                
                # Формируем результат для новой логики
                result = {
                    'container_id': container_id,
                    'container_name': container_name,
                    'ssh_port': ssh_port_result,
                    'ssh_host': ssh_host,
                    'ssh_command': container_info.get('ssh_command', f"ssh root@{ssh_host} -p {ssh_port_result}") if ssh_port_result else None,
                    'ssh_username': ssh_username,
                    'ssh_password': ssh_password,
                    'port_mapping': port_mapping,  # Добавляем port_mapping в результат
                    'status': 'running',
                    'allocated_resources': {
                        'cpu_cpuset': cpuset_cpus,
                        'ram_gb': memory_gb,
                        'gpu_count': gpu_required,
                        'gpu_devices': gpus_param,
                        'storage_gb': storage_gb,
                        'gpu_support': bool(gpus_param)
                    }
                }
                
            else:
                # Старая логика для обратной совместимости
                if not all([ssh_password, ssh_port]):
                    print("[ERROR] Missing SSH credentials in container_info")
                    try:
                        self.api_client.send_log("task error: missing ssh credentials")
                    except Exception:
                        pass
                    return None
                
                print(f"[INFO] Using SSH credentials from task:")
                print(f"  Username: {ssh_username}")
                print(f"  Port: {ssh_port}")
                print(f"  Host: {ssh_host}")
                
                # Получаем выделенные ресурсы из задачи
                gpus_allocated = task_data.get('gpus_allocated', {})
                gpu_limit = gpus_allocated.get('count') if gpus_allocated else 0
                
                # Формируем имя контейнера (без зависимости от username)
                task_id = task.get('id', int(time.time()))
                container_name = f"task_{task_id}"
                
                # Вычисляем Jupyter порт (на 1 больше SSH порта)
                jup_port = ssh_port + 1

                # Используем ContainerManager для создания контейнера
                try:
                    self.api_client.send_log(f"task start requested: id={task_id} image={docker_image}")
                except Exception:
                    pass
                container_id = self.container_manager.start(
                    container_name=container_name,
                    ssh_port=ssh_port,
                    jup_port=jup_port,
                    ssh_password=ssh_password,
                    jupyter_token=ssh_password,  # Используем тот же пароль для Jupyter
                    ssh_username=ssh_username,
                    gpus=gpus_param,
                    image=docker_image,
                    cpuset_cpus=cpuset_cpus,
                    memory_gb=memory_gb,
                    memory_swap_gb=memory_gb,
                    shm_size_gb=shm_size_gb,
                    storage_gb=storage_gb
                )
                
                # Формируем результат для старой логики
                result = {
                    'container_id': container_id,
                    'container_name': container_name,
                    'ssh_port': ssh_port,
                    'ssh_host': ssh_host,
                    'ssh_command': container_info.get('ssh_command', f"ssh root@{ssh_host} -p {ssh_port}"),
                    'ssh_username': ssh_username,
                    'ssh_password': ssh_password,
                    'status': 'running',
                    'allocated_resources': {
                        'cpu_cpuset': cpuset_cpus,
                        'ram_gb': memory_gb,
                        'gpu_count': gpu_required,
                        'gpu_devices': gpus_param,
                        'storage_gb': storage_gb,
                        'gpu_support': bool(gpus_param)
                    }
                }
            
            print(f"[INFO] Container created successfully:")
            print(f"  Container ID: {result['container_id']}")
            print(f"  Container Name: {result['container_name']}")
            print(f"  SSH Host: {result['ssh_host']}")
            print(f"  SSH Port: {result['ssh_port']}")
            print(f"  SSH Command: {result['ssh_command']}")
            print(f"  Allocated Resources: {result.get('allocated_resources', 'N/A')}")
            try:
                self.api_client.send_log(f"container started: id={result['container_id']} name={result['container_name']}")
            except Exception:
                pass
            
            return result
                
        except Exception as e:
            print(f"[ERROR] Task processing failed: {e}")
            try:
                self.api_client.send_log(f"task processing exception: {e}")
            except Exception:
                pass
            return None
    
    def initialize(self) -> bool:
        """Инициализирует агента"""
        print("[INFO] Initializing agent...")
        try:
            # Если известен agent_id, сообщаем о старте init
            if self.api_client.agent_id:
                self.api_client.send_log("agent init started")
        except Exception:
            pass
        
        # Проверяем и устанавливаем Docker (только один раз при инициализации)
        print("[INFO] Checking Docker installation...")
        if not self.container_manager.check_and_install_docker():
            print("[ERROR] Docker is required but not available. Please install Docker and restart the script.")
            try:
                if self.api_client.agent_id:
                    self.api_client.send_log("agent init error: docker not available")
            except Exception:
                pass
            return False
        
        # Проверяем и исправляем права Docker (только один раз при инициализации)
        print("[INFO] Checking Docker permissions...")
        if not self.container_manager.fix_docker_permissions():
            print("[WARNING] Docker permissions could not be fixed automatically.")
            print("[WARNING] You may need to run: sudo usermod -aG docker $USER")
            print("[WARNING] Then log out and log back in, or restart the system.")
            print("[WARNING] Continuing anyway, but Docker operations may fail...")
        else:
            print("[INFO] Docker permissions are OK")
        
        # Проверяем поддержку GPU в Docker (только один раз при инициализации)
        print("[INFO] Checking Docker GPU support...")
        gpu_support = self.container_manager.check_docker_gpu_support()
        if not gpu_support:
            print("[WARNING] GPU support not available in Docker, containers will run without GPU access")
        else:
            print("[INFO] Docker GPU support confirmed")
        
        # Собираем данные о системе
        system_data = self.collect_system_data()
        print(json.dumps(system_data, indent=2, ensure_ascii=False))
        
        if not self.agent_id:
            # Первый запуск — делаем confirm
            print("[INFO] First run - confirming agent with server...")
            try:
                agent_id = self.api_client.confirm_agent(system_data)
                if agent_id:
                    self.agent_id = agent_id
                    self.api_client.set_credentials(agent_id, self.secret_key)
                    self._save_agent_id(agent_id)
                    try:
                        self.api_client.send_log("agent confirmed")
                    except Exception:
                        pass
                else:
                    print("[ERROR] Could not obtain agent_id from server. Exiting.")
                    try:
                        self.api_client.send_log("agent confirm failed: no id")
                    except Exception:
                        pass
                    return False
            except Exception as e:
                print(f"[ERROR] Failed to confirm agent: {e}")
                try:
                    self.api_client.send_log(f"agent confirm exception: {e}")
                except Exception:
                    pass
                return False
        
        # Отправляем init данные
        print(f"[INFO] Sending init data to server for agent_id: {self.agent_id}")
        try:
            success = self.api_client.send_init_data(system_data)
            if success:
                try:
                    self.api_client.send_log("agent init sent")
                except Exception:
                    pass
            else:
                print("[WARNING] Failed to send init data, but continuing...")
                try:
                    self.api_client.send_log("agent init send failed")
                except Exception:
                    pass
        except Exception as e:
            print(f"[ERROR] Failed to send init data: {e}")
            # Продолжаем работу даже если init не удался
            try:
                self.api_client.send_log(f"agent init send exception: {e}")
            except Exception:
                pass
        
        try:
            self.api_client.send_log("agent init completed")
        except Exception:
            pass
        return True
    
    def run(self):
        """Запускает основной цикл агента"""
        print("[INFO] Starting agent...")
        
        # Инициализируем агента
        if not self.initialize():
            print("[ERROR] Agent initialization failed")
            try:
                if self.api_client.agent_id:
                    self.api_client.send_log("agent start failed: init failed")
            except Exception:
                pass
            return
        
        # Запускаем polling в отдельном потоке
        print("[INFO] Starting polling thread...")
        try:
            polling_thread = self.api_client.start_polling_thread(self.process_task)
            print("[INFO] Polling thread started successfully")
            try:
                self.api_client.send_log("polling started")
            except Exception:
                pass
        except Exception as e:
            print(f"[ERROR] Failed to start polling thread: {e}")
            try:
                self.api_client.send_log(f"polling start exception: {e}")
            except Exception:
                pass
            return
        
        print("[INFO] Agent initialization completed. Starting main loop...")
        
        # Основной цикл с периодической отправкой heartbeat
        heartbeat_counter = 0
        print("[INFO] Main loop started. Agent is running...")
        
        try:
            while True:
                time.sleep(60)
                heartbeat_counter += 1
                
                # Каждые 5 минут отправляем heartbeat
                if heartbeat_counter >= 5:
                    try:
                        monitoring_data = self.collect_monitoring_data()
                        self.api_client.send_heartbeat(monitoring_data)
                    except Exception as e:
                        print(f"[WARNING] Heartbeat failed: {e}")
                        try:
                            self.api_client.send_log(f"heartbeat exception: {e}")
                        except Exception:
                            pass
                    heartbeat_counter = 0
                    
        except KeyboardInterrupt:
            print("[INFO] Received interrupt signal. Shutting down...")
            try:
                self.api_client.send_log("agent stopping: interrupt")
            except Exception:
                pass
        except Exception as e:
            print(f"[ERROR] Main loop error: {e}")
            try:
                self.api_client.send_log(f"agent main loop exception: {e}")
            except Exception:
                pass
        finally:
            # Закрываем соединения
            self.api_client.close()
            print("[INFO] Agent shutdown completed")
            try:
                if self.api_client.agent_id:
                    self.api_client.send_log("agent stopped")
            except Exception:
                pass


def main():
    """Точка входа"""
    if len(sys.argv) < 2:
        print("Usage: python agent.py <secret_key>")
        sys.exit(1)
    
    secret_key = sys.argv[1]
    base_url = os.getenv("API_BASE_URL", "https://api.gpugo.ru")

    
    agent = Agent(secret_key, base_url=base_url)
    agent.run()


if __name__ == "__main__":
    main()
