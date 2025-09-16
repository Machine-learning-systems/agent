#!/usr/bin/env python
# -*- coding: utf-8 -*-

import platform
import subprocess
import re
import os
import socket
import time
import psutil
import requests
from typing import List, Dict, Optional, Tuple, Any


class HardwareAnalyzer:
    """Класс для анализа характеристик компьютера"""
    
    def __init__(self):
        self.system = platform.system()
        self._cpu_info_cache = None
        self._gpu_info_cache = None
        self._disk_info_cache = None
        self._network_info_cache = None
        self._ram_info_cache = None
    
    def get_cpu_info(self) -> List[Dict[str, Any]]:
        """Получает детальную информацию о CPU"""
        if self._cpu_info_cache is not None:
            return self._cpu_info_cache
            
        cpu_info = []
        
        try:
            if self.system == "Darwin":
                # macOS
                try:
                    model = subprocess.check_output(['sysctl', '-n', 'machdep.cpu.brand_string']).decode().strip()
                    cores = psutil.cpu_count(logical=False)
                    threads = psutil.cpu_count(logical=True)
                    
                    # Получаем частоту через sysctl
                    freq = None
                    try:
                        freq_mhz = subprocess.check_output(['sysctl', '-n', 'hw.cpufrequency_max']).decode().strip()
                        if freq_mhz.isdigit():
                            freq = float(freq_mhz) / 1000000000  # Конвертируем в GHz
                    except:
                        pass
                    
                    cpu_info.append({
                        "model": model,
                        "cores": cores,
                        "threads": threads,
                        "freq_ghz": round(freq, 2) if freq else None,
                        "count": 1
                    })
                except Exception as e:
                    print(f"[WARNING] macOS CPU detection failed: {e}")
                    cpu_info.append({
                        "model": platform.processor(),
                        "cores": psutil.cpu_count(logical=False),
                        "threads": psutil.cpu_count(logical=True),
                        "freq_ghz": None,
                        "count": 1
                    })
                    
            elif self.system == "Windows":
                # Windows
                try:
                    wmic_output = subprocess.check_output(['wmic', 'cpu', 'get', 'Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed'], shell=True).decode(errors='ignore')
                    lines = wmic_output.strip().split('\n')[1:]  # Пропускаем заголовок
                    
                    cpu_groups = {}
                    for line in lines:
                        if line.strip():
                            parts = line.split()
                            if len(parts) >= 4:
                                model_parts = parts[:-3]
                                model = ' '.join(model_parts)
                                cores = int(parts[-3]) if parts[-3].isdigit() else 1
                                threads = int(parts[-2]) if parts[-2].isdigit() else 1
                                freq_mhz = int(parts[-1]) if parts[-1].isdigit() else None
                                freq_ghz = freq_mhz / 1000 if freq_mhz else None
                                
                                if model in cpu_groups:
                                    cpu_groups[model]['count'] += 1
                                    cpu_groups[model]['cores'] += cores
                                    cpu_groups[model]['threads'] += threads
                                    if freq_ghz and (cpu_groups[model]['freq_ghz'] is None or freq_ghz > cpu_groups[model]['freq_ghz']):
                                        cpu_groups[model]['freq_ghz'] = freq_ghz
                                else:
                                    cpu_groups[model] = {
                                        'model': model,
                                        'cores': cores,
                                        'threads': threads,
                                        'freq_ghz': freq_ghz,
                                        'count': 1
                                    }
                    
                    for cpu_data in cpu_groups.values():
                        cpu_info.append(cpu_data)
                        
                except Exception as e:
                    print(f"[WARNING] Windows CPU detection failed: {e}")
                    model = subprocess.check_output(['wmic', 'cpu', 'get', 'Name'], shell=True).decode(errors='ignore').split('\n')[1].strip()
                    cores = psutil.cpu_count(logical=False)
                    threads = psutil.cpu_count(logical=True)
                    freq = psutil.cpu_freq().max / 1000 if psutil.cpu_freq() else None
                    cpu_info.append({
                        "model": model,
                        "cores": cores,
                        "threads": threads,
                        "freq_ghz": round(freq, 2) if freq else None,
                        "count": 1
                    })
                    
            elif self.system == "Linux":
                # Linux
                try:
                    lscpu_output = subprocess.check_output(['lscpu']).decode()
                    
                    sockets_match = re.search(r'Socket\(s\):\s+(\d+)', lscpu_output)
                    sockets = int(sockets_match.group(1)) if sockets_match else 1
                    
                    # Альтернативные способы определения сокетов
                    if sockets == 1:
                        try:
                            with open('/proc/cpuinfo') as f:
                                cpuinfo_lines = f.read()
                                physical_ids = set()
                                for line in cpuinfo_lines.split('\n'):
                                    if line.startswith('physical id'):
                                        physical_id = line.split(':')[1].strip()
                                        physical_ids.add(physical_id)
                                if len(physical_ids) > 1:
                                    sockets = len(physical_ids)
                        except Exception as e:
                            print(f"[DEBUG] Failed to detect sockets from /proc/cpuinfo: {e}")
                    
                    # Получаем модель процессора
                    model_match = re.search(r'Model name:\s+(.+)', lscpu_output)
                    if model_match:
                        model = model_match.group(1).strip()
                    else:
                        with open('/proc/cpuinfo') as f:
                            cpuinfo_lines = f.read()
                            model_match = re.search(r'model name\s+:\s+(.+)', cpuinfo_lines)
                            model = model_match.group(1).strip() if model_match else platform.processor()
                    
                    # Получаем общее количество ядер и потоков
                    total_cores = psutil.cpu_count(logical=False)
                    total_threads = psutil.cpu_count(logical=True)
                    
                    # Вычисляем количество ядер и потоков на один сокет
                    cores_per_socket = total_cores // sockets
                    threads_per_socket = total_threads // sockets
                    
                    # Проверяем корректность вычислений
                    if cores_per_socket * sockets != total_cores:
                        cores_per_socket = total_cores
                        threads_per_socket = total_threads
                        sockets = 1
                    
                    # Получаем частоту через lscpu
                    freq = None
                    freq_match = re.search(r'CPU max MHz:\s+(\d+)', lscpu_output)
                    if freq_match:
                        freq = float(freq_match.group(1)) / 1000
                    else:
                        cpu_freq = psutil.cpu_freq()
                        freq = cpu_freq.max / 1000 if cpu_freq else None
                    
                    cpu_info.append({
                        "model": model,
                        "cores": cores_per_socket,
                        "threads": threads_per_socket,
                        "freq_ghz": round(freq, 2) if freq else None,
                        "count": sockets
                    })
                    
                except Exception as e:
                    print(f"[WARNING] lscpu failed, using fallback: {e}")
                    with open('/proc/cpuinfo') as f:
                        lines = f.read()
                        model_match = re.search(r'model name\s+:\s+(.+)', lines)
                        if model_match:
                            model = model_match.group(1).strip()
                        else:
                            model = platform.processor()
                        
                        cores = psutil.cpu_count(logical=False)
                        threads = psutil.cpu_count(logical=True)
                        
                        freq = None
                        try:
                            cpu_freq = psutil.cpu_freq()
                            freq = cpu_freq.max / 1000 if cpu_freq else None
                        except:
                            pass
                        
                        cpu_info.append({
                            "model": model,
                            "cores": cores,
                            "threads": threads,
                            "freq_ghz": round(freq, 2) if freq else None,
                            "count": 1
                        })
            else:
                # Для других систем
                model = platform.processor()
                cores = psutil.cpu_count(logical=False)
                threads = psutil.cpu_count(logical=True)
                freq = psutil.cpu_freq().max / 1000 if psutil.cpu_freq() else None
                
                cpu_info.append({
                    "model": model,
                    "cores": cores,
                    "threads": threads,
                    "freq_ghz": round(freq, 2) if freq else None,
                    "count": 1
                })
        except Exception as e:
            print(f"[ERROR] CPU info failed: {e}")
            if not cpu_info:
                cpu_info.append({
                    "model": "Unknown CPU",
                    "cores": psutil.cpu_count(logical=False) or 1,
                    "threads": psutil.cpu_count(logical=True) or 1,
                    "freq_ghz": None,
                    "count": 1
                })
        
        self._cpu_info_cache = cpu_info
        return cpu_info
    
    def get_gpu_info(self) -> List[Dict[str, Any]]:
        """Получает детальную информацию о GPU"""
        if self._gpu_info_cache is not None:
            return self._gpu_info_cache
            
        gpus = []
        
        try:
            if self.system == "Darwin":
                # macOS
                sp = subprocess.check_output(['system_profiler', 'SPDisplaysDataType']).decode()
                for block in sp.split('\n\n'):
                    model = re.search(r'Chipset Model: (.+)', block)
                    vram = re.search(r'VRAM.*: (\d+)\s*MB', block)
                    vendor = re.search(r'Vendor: (.+)', block)
                    metal = re.search(r'Metal Family: (.+)', block)
                    if model:
                        gpus.append({
                            "model": model.group(1),
                            "vram_gb": int(vram.group(1)) // 1024 if vram else 0,
                            "max_cuda_version": None,
                            "tflops": None,
                            "bandwidth_gbps": None,
                            "vendor": vendor.group(1) if vendor else None,
                            "metal_family": metal.group(1) if metal else None,
                            "count": 1
                        })
                        
            elif self.system == "Windows":
                # Windows
                out = subprocess.check_output(['wmic', 'path', 'win32_VideoController', 'get', 'Name,AdapterRAM,PNPDeviceID,DriverVersion'], shell=True).decode(errors='ignore')
                for line in out.split('\n')[1:]:
                    if line.strip():
                        parts = line.split()
                        model = ' '.join(parts[:-3]) if len(parts) > 3 else parts[0]
                        vram = int(parts[-3]) if parts[-3].isdigit() else None
                        driver = parts[-1] if len(parts) > 1 else None
                        gpus.append({
                            "model": model,
                            "vram_gb": vram // (1024 ** 3) if vram else 0,
                            "max_cuda_version": None,
                            "tflops": None,
                            "bandwidth_gbps": None,
                            "driver_version": driver,
                            "count": 1
                        })
                        
            elif self.system == "Linux":
                # Linux - NVIDIA GPU
                try:
                    nvidia_output = subprocess.check_output(['nvidia-smi', '-L'], stderr=subprocess.DEVNULL, timeout=10).decode(errors='ignore')
                    for line in nvidia_output.strip().split('\n'):
                        if line:
                            match = re.search(r'GPU (\d+): (.+?) \(UUID:', line)
                            if match:
                                gpu_index = int(match.group(1))
                                model = match.group(2).strip()
                                
                                # Получаем дополнительную информацию
                                vram_gb = None
                                cuda_version = None
                                try:
                                    nvidia_detailed = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.total,driver_version', '--format=csv,noheader', '-i', str(gpu_index)], stderr=subprocess.DEVNULL, timeout=5).decode(errors='ignore')
                                    if nvidia_detailed.strip():
                                        parts = nvidia_detailed.strip().split(',')
                                        if len(parts) >= 2:
                                            vram_str = parts[0].strip()
                                            driver_version = parts[1].strip()
                                            vram_match = re.search(r'(\d+)\s*(MiB|GiB)', vram_str)
                                            if vram_match:
                                                vram_size = int(vram_match.group(1))
                                                vram_unit = vram_match.group(2)
                                                if vram_unit == 'MiB':
                                                    vram_gb = vram_size // 1024
                                                elif vram_unit == 'GiB':
                                                    vram_gb = vram_size
                                                else:
                                                    vram_gb = vram_size // 1024
                                            
                                            cuda_match = re.search(r'CUDA Version: (\d+\.\d+)', driver_version)
                                            if cuda_match:
                                                cuda_version = cuda_match.group(1)
                                except:
                                    pass
                                
                                gpus.append({
                                    "model": model,
                                    "vram_gb": vram_gb if vram_gb is not None else 0,
                                    "max_cuda_version": cuda_version,
                                    "tflops": None,
                                    "bandwidth_gbps": None,
                                    "vendor": "NVIDIA",
                                    "count": 1
                                })
                except:
                    pass
                
                # Linux - другие GPU через lspci
                try:
                    lspci_output = subprocess.check_output(['lspci', '-nn'], timeout=5).decode(errors='ignore')
                    for line in lspci_output.split('\n'):
                        if 'VGA compatible controller' in line or '3D controller' in line or 'Display controller' in line:
                            parts = line.split(':')
                            if len(parts) >= 2:
                                device_info = ':'.join(parts[1:]).strip()
                                model = "Unknown"
                                vendor = "Unknown"
                                
                                if 'AMD' in device_info or 'ATI' in device_info:
                                    vendor = "AMD"
                                    amd_match = re.search(r'\[([^\]]+)\]', device_info)
                                    if amd_match:
                                        model = amd_match.group(1)
                                        if model.isdigit() or len(model) < 4:
                                            radeon_match = re.search(r'Radeon\s+([^\s\]]+)', device_info)
                                            if radeon_match:
                                                model = f"AMD Radeon {radeon_match.group(1)}"
                                elif 'NVIDIA' in device_info:
                                    vendor = "NVIDIA"
                                    nvidia_match = re.search(r'\[([^\]]+)\]', device_info)
                                    if nvidia_match:
                                        model = nvidia_match.group(1)
                                elif 'Intel' in device_info:
                                    vendor = "Intel"
                                    intel_match = re.search(r'\[([^\]]+)\]', device_info)
                                    if intel_match:
                                        model = intel_match.group(1)
                                
                                if model != "Unknown" and len(model) > 3:
                                    gpus.append({
                                        "model": model,
                                        "vram_gb": 0,
                                        "max_cuda_version": None,
                                        "tflops": None,
                                        "bandwidth_gbps": None,
                                        "vendor": vendor,
                                        "count": 1
                                    })
                except:
                    pass
        except Exception as e:
            print(f"[ERROR] GPU info failed: {e}")
        
        # Группируем одинаковые GPU
        filtered_gpus = []
        gpu_groups = {}
        
        for gpu in gpus:
            model = gpu.get("model", "")
            vendor = gpu.get("vendor", "")
            
            if (model in ["Unknown", "0300", "1a03:2000"] or 
                len(model) < 4 or 
                model.isdigit() or 
                model.startswith('0') or 
                ':' in model):
                continue
            
            key = f"{vendor}_{model}"
            
            if key in gpu_groups:
                gpu_groups[key]["count"] += 1
            else:
                gpu_groups[key] = gpu.copy()
                gpu_groups[key]["count"] = 1
        
        filtered_gpus = list(gpu_groups.values())
        self._gpu_info_cache = filtered_gpus
        return filtered_gpus
    
    def get_disk_info(self) -> List[Dict[str, Any]]:
        """Получает информацию о дисках"""
        if self._disk_info_cache is not None:
            return self._disk_info_cache
            
        disks = []
        
        try:
            if self.system == "Darwin":
                # macOS
                disk_list = subprocess.check_output(['diskutil', 'list']).decode()
                for match in re.finditer(r'/dev/(disk\d+)', disk_list):
                    disk = match.group(1)
                    try:
                        info = subprocess.check_output(['diskutil', 'info', disk]).decode()
                        model = re.search(r'Device / Media Name: (.+)', info)
                        size = re.search(r'Total Size:.*\((\d+(?:\.\d+)?)\s+GB\)', info)
                        dtype = re.search(r'Protocol: (.+)', info)
                        disks.append({
                            "model": model.group(1) if model else disk,
                            "type": dtype.group(1) if dtype else None,
                            "size_gb": float(size.group(1)) if size else None,
                            "read_speed_mb_s": None,
                            "write_speed_mb_s": None
                        })
                    except Exception:
                        continue
                        
            elif self.system == "Windows":
                # Windows
                out = subprocess.check_output(['wmic', 'diskdrive', 'get', 'Model,Size,MediaType,InterfaceType'], shell=True).decode(errors='ignore')
                for line in out.split('\n')[1:]:
                    if line.strip():
                        parts = line.split()
                        if len(parts) >= 4:
                            model = ' '.join(parts[:-3])
                            dtype = parts[-2]
                            size = int(parts[-3]) if parts[-3].isdigit() else None
                            size_gb = size // (1024 ** 3) if size else None
                            disks.append({
                                "model": model,
                                "type": dtype,
                                "size_gb": size_gb,
                                "read_speed_mb_s": None,
                                "write_speed_mb_s": None
                            })
                            
            elif self.system == "Linux":
                # Linux
                try:
                    lsblk_output = subprocess.check_output(['lsblk', '-d', '-o', 'NAME,MODEL,SIZE,TYPE'], stderr=subprocess.DEVNULL).decode(errors='ignore')
                    lines = lsblk_output.split('\n')
                    
                    header_index = -1
                    for i, line in enumerate(lines):
                        if 'NAME' in line and 'MODEL' in line and 'SIZE' in line and 'TYPE' in line:
                            header_index = i
                            break
                    
                    for line in lines[header_index + 1:]:
                        if line.strip() and 'disk' in line:
                            parts = line.split()
                            if len(parts) >= 4:
                                name = parts[0]
                                dtype = parts[-1]
                                
                                size_str = None
                                model_parts = []
                                
                                for i, part in enumerate(parts[1:-1]):
                                    if any(unit in part.upper() for unit in ['G', 'T', 'M', 'K']) and any(char.isdigit() for char in part):
                                        size_str = part
                                        model_parts = parts[1:i+1]
                                        break
                                
                                if size_str is None and len(parts) >= 5:
                                    size_str = parts[-2]
                                    model_parts = parts[1:-2]
                                
                                if size_str in ['-', 'Unknown', 'LEGEND'] or not size_str:
                                    continue
                                
                                model = ' '.join(model_parts) if model_parts else "Unknown"
                                
                                if any(char.isalpha() and char.upper() not in ['G', 'T', 'M', 'K', 'I', 'B'] for char in size_str):
                                    continue
                                
                                size_gb = None
                                if size_str != '-':
                                    try:
                                        size_str = size_str.strip()
                                        
                                        if not re.match(r'^[\d\.]+[GMTK]?[i]?[B]?$', size_str, re.IGNORECASE):
                                            continue
                                        
                                        if 'G' in size_str.upper():
                                            size_gb = float(size_str.replace('G', '').replace('g', ''))
                                        elif 'T' in size_str.upper():
                                            size_gb = float(size_str.replace('T', '').replace('t', '')) * 1024
                                        elif 'M' in size_str.upper():
                                            size_gb = float(size_str.replace('M', '').replace('m', '')) / 1024
                                        elif 'K' in size_str.upper():
                                            size_gb = float(size_str.replace('K', '').replace('k', '')) / (1024 * 1024)
                                        elif size_str.isdigit():
                                            size_bytes = int(size_str)
                                            size_gb = size_bytes // (1024**3)
                                        else:
                                            number_match = re.search(r'(\d+(?:\.\d+)?)', size_str)
                                            if number_match:
                                                number = float(number_match.group(1))
                                                if 'T' in size_str.upper():
                                                    size_gb = number * 1024
                                                elif 'M' in size_str.upper():
                                                    size_gb = number / 1024
                                                elif 'K' in size_str.upper():
                                                    size_gb = number / (1024 * 1024)
                                                else:
                                                    size_gb = number
                                    except Exception as e:
                                        print(f"[WARNING] Failed to parse disk size '{size_str}': {e}")
                                        pass
                                
                                # Определяем тип диска
                                disk_type = "Unknown"
                                try:
                                    if os.path.exists(f'/sys/block/{name.replace("/dev/", "")}/queue/rotational'):
                                        with open(f'/sys/block/{name.replace("/dev/", "")}/queue/rotational', 'r') as f:
                                            rotational = f.read().strip()
                                            disk_type = "SSD" if rotational == "0" else "HDD"
                                except:
                                    pass
                                
                                disks.append({
                                    "model": model,
                                    "type": disk_type,
                                    "size_gb": size_gb,
                                    "read_speed_mb_s": None,
                                    "write_speed_mb_s": None
                                })
                except Exception as e:
                    print(f"[WARNING] lsblk failed: {e}")
                    # Fallback
                    try:
                        with open('/proc/partitions', 'r') as f:
                            for line in f.readlines()[2:]:
                                parts = line.split()
                                if len(parts) >= 4 and (parts[3].endswith('sd') or parts[3].endswith('nvme') or parts[3].endswith('hd')):
                                    name = f"/dev/{parts[3]}"
                                    size_gb = int(parts[2]) // (1024 * 1024)
                                    disks.append({
                                        "model": "Unknown",
                                        "type": "Unknown",
                                        "size_gb": size_gb,
                                        "read_speed_mb_s": None,
                                        "write_speed_mb_s": None
                                    })
                    except Exception as e2:
                        print(f"[WARNING] /proc/partitions also failed: {e2}")
                        pass
        except Exception as e:
            print(f"[ERROR] Disk info failed: {e}")
            disks.append({
                "model": "Unknown Disk",
                "type": "Unknown",
                "size_gb": 100,
                "read_speed_mb_s": None,
                "write_speed_mb_s": None
            })
        
        self._disk_info_cache = disks
        return disks
    
    def get_network_info(self) -> List[Dict[str, Any]]:
        """Получает информацию о сетевых интерфейсах"""
        if self._network_info_cache is not None:
            return self._network_info_cache
            
        networks = []
        
        try:
            if self.system == "Darwin":
                # macOS
                sp = subprocess.check_output(['networksetup', '-listallhardwareports']).decode()
                for match in re.finditer(r'Hardware Port: (.+?)\nDevice: (.+?)\n', sp):
                    port, device = match.groups()
                    up_mbps = None
                    try:
                        info = subprocess.check_output(['ifconfig', device]).decode()
                        up = re.search(r'media:.*\((\d+)baseT', info)
                        up_mbps = int(up.group(1)) if up else None
                    except Exception:
                        pass
                    networks.append({
                        "up_mbps": up_mbps,
                        "down_mbps": up_mbps,
                        "ports": device
                    })
                    
            elif self.system == "Windows":
                # Windows
                try:
                    out = subprocess.check_output(['wmic', 'nic', 'get', 'Name,Speed'], shell=True).decode(errors='ignore')
                    for line in out.split('\n')[1:]:
                        if line.strip():
                            parts = line.split()
                            name = ' '.join(parts[:-1]) if len(parts) > 1 else parts[0]
                            speed = int(parts[-1]) if parts[-1].isdigit() else None
                            networks.append({
                                "up_mbps": speed // 1_000_000 if speed else None,
                                "down_mbps": speed // 1_000_000 if speed else None,
                                "ports": name
                            })
                except Exception:
                    pass
                    
            elif self.system == "Linux":
                # Linux
                try:
                    ip_link_output = subprocess.check_output(['ip', '-o', 'link', 'show'], stderr=subprocess.DEVNULL).decode(errors='ignore')
                    
                    for line in ip_link_output.split('\n'):
                        if line.strip():
                            try:
                                parts = line.split(':')
                                if len(parts) >= 2:
                                    iface_name = parts[1].strip()
                                    
                                    if iface_name == 'lo' or iface_name.startswith('virbr') or iface_name.startswith('docker') or iface_name.startswith('veth'):
                                        continue
                                    
                                    up_mbps = None
                                    down_mbps = None
                                    
                                    # Получаем скорость через sysfs
                                    try:
                                        if os.path.exists(f'/sys/class/net/{iface_name}/speed'):
                                            with open(f'/sys/class/net/{iface_name}/speed', 'r') as f:
                                                speed = f.read().strip()
                                                if speed != '-1' and speed.isdigit():
                                                    up_mbps = int(speed)
                                                    down_mbps = int(speed)
                                    except:
                                        pass
                                    
                                    # Определяем тип интерфейса
                                    interface_type = "Unknown"
                                    if 'wlan' in iface_name or 'wifi' in iface_name or 'wl' in iface_name or iface_name.startswith('wl'):
                                        interface_type = "WiFi"
                                    elif 'eth' in iface_name or 'en' in iface_name:
                                        interface_type = "Ethernet"
                                    
                                    # Fallback для скорости
                                    if up_mbps is None:
                                        if interface_type == "Ethernet":
                                            up_mbps = 1000
                                            down_mbps = 1000
                                        elif interface_type == "WiFi":
                                            up_mbps = 300
                                            down_mbps = 300
                                        else:
                                            up_mbps = 1000
                                            down_mbps = 1000
                                    
                                    networks.append({
                                        "up_mbps": up_mbps,
                                        "down_mbps": down_mbps,
                                        "ports": iface_name,
                                        "type": interface_type
                                    })
                                    
                            except Exception as e:
                                print(f"[WARNING] Network interface parsing error: {e}")
                                continue
                except Exception as e:
                    print(f"[WARNING] Network detection error: {e}")
        except Exception as e:
            print(f"[ERROR] Network info failed: {e}")
        
        self._network_info_cache = networks
        return networks
    
    def get_ram_info(self) -> Tuple[int, str]:
        """Получает информацию о RAM"""
        if self._ram_info_cache is not None:
            return self._ram_info_cache
            
        total_ram_gb = round(psutil.virtual_memory().total / (1024 ** 3))
        ram_type = "Unknown"
        
        try:
            if self.system == "Darwin":
                ram_type_out = subprocess.check_output(["system_profiler", "SPMemoryDataType"]).decode()
                match = re.search(r'Type: (\w+)', ram_type_out)
                if match:
                    ram_type = match.group(1)
            elif self.system == "Windows":
                ram_type_out = subprocess.check_output(['wmic', 'memorychip', 'get', 'MemoryType'], shell=True).decode(errors='ignore')
                if '24' in ram_type_out:
                    ram_type = 'DDR3'
                elif '26' in ram_type_out:
                    ram_type = 'DDR4'
            elif self.system == "Linux":
                try:
                    try:
                        ram_type_out = subprocess.check_output(['sudo', 'dmidecode', '-t', 'memory'], stderr=subprocess.DEVNULL).decode(errors='ignore')
                        match = re.search(r'Type:\s+(DDR\w*)', ram_type_out)
                        if match:
                            ram_type = match.group(1)
                    except:
                        try:
                            lshw_output = subprocess.check_output(['lshw', '-class', 'memory'], stderr=subprocess.DEVNULL).decode(errors='ignore')
                            match = re.search(r'DDR(\w*)', lshw_output)
                            if match:
                                ram_type = f"DDR{match.group(1)}"
                        except:
                            pass
                except Exception as e:
                    print(f"[WARNING] RAM type detection error: {e}")
        except Exception as e:
            print(f"[ERROR] RAM info failed: {e}")
        
        self._ram_info_cache = (total_ram_gb, ram_type)
        return total_ram_gb, ram_type
    
    def get_ip_address(self) -> Optional[str]:
        """Получает реальный IP адрес для SSH подключения"""
        try:
            # Метод 1: Для Linux - используем ip route get
            if self.system == "Linux":
                try:
                    route_output = subprocess.check_output(['ip', 'route', 'get', '1.1.1.1'], stderr=subprocess.DEVNULL).decode(errors='ignore')
                    if 'src ' in route_output:
                        src_match = re.search(r'src (\d+\.\d+\.\d+\.\d+)', route_output)
                        if src_match:
                            ip = src_match.group(1)
                            return ip
                except Exception as e:
                    print(f"[DEBUG] Failed to get IP from route: {e}")
                    pass
            
            # Метод 2: Внешний сервис
            try:
                response = requests.get('https://api.ipify.org', timeout=5)
                if response.status_code == 200:
                    external_ip = response.text.strip()
                    if external_ip and external_ip != '127.0.0.1':
                        return external_ip
            except Exception as e:
                print(f"[DEBUG] Failed to get IP from api.ipify.org: {e}")
                pass
            
            # Метод 3: Альтернативный сервис
            try:
                response = requests.get('https://ifconfig.me', timeout=5)
                if response.status_code == 200:
                    external_ip = response.text.strip()
                    if external_ip and external_ip != '127.0.0.1':
                        return external_ip
            except Exception as e:
                print(f"[DEBUG] Failed to get IP from ifconfig.me: {e}")
                pass
            
            # Метод 4: Для macOS
            if self.system == "Darwin":
                try:
                    ifconfig_output = subprocess.check_output(['ifconfig']).decode(errors='ignore')
                    for line in ifconfig_output.split('\n'):
                        if 'inet ' in line and '127.0.0.1' not in line:
                            parts = line.strip().split()
                            for i, part in enumerate(parts):
                                if part == 'inet':
                                    if i + 1 < len(parts):
                                        ip = parts[i + 1]
                                        if ip != '127.0.0.1':
                                            return ip
                except:
                    pass
            
            # Метод 5: Для Windows
            elif self.system == "Windows":
                try:
                    ipconfig_output = subprocess.check_output(['ipconfig'], shell=True).decode(errors='ignore')
                    for line in ipconfig_output.split('\n'):
                        if 'IPv4 Address' in line:
                            ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
                            if ip_match:
                                ip = ip_match.group(1)
                                if ip != '127.0.0.1':
                                    return ip
                except:
                    pass
            
            # Метод 6: Fallback
            try:
                hostname = socket.gethostname()
                ip = socket.gethostbyname(hostname)
                if ip != '127.0.0.1':
                    return ip
            except:
                pass
            
            return None
            
        except Exception as e:
            print(f"[WARNING] IP address detection error: {e}")
            return None
    
    def get_hostname(self) -> str:
        """Получает hostname"""
        return platform.node()
    
    def get_location_from_ip(self, ip_address: str) -> str:
        """Определяет локацию по IP адресу"""
        try:
            response = requests.get(f"http://ip-api.com/json/{ip_address}", timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success':
                    country = data.get('country', 'Unknown')
                    city = data.get('city', 'Unknown')
                    return f"{city}, {country}"
                else:
                    return "Unknown"
            else:
                return "Unknown"
        except Exception as e:
            print(f"[WARNING] Failed to get location from IP: {e}")
            return "Unknown"

    def get_available_resources(self) -> Optional[Dict[str, Any]]:
        """Получает информацию о доступных ресурсах системы с учетом уже запущенных контейнеров"""
        try:
            # CPU
            cpu_count = psutil.cpu_count(logical=True)
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # RAM
            memory = psutil.virtual_memory()
            total_ram_gb = memory.total / (1024**3)
            available_ram_gb = memory.available / (1024**3)
            
            # GPU (если есть)
            gpu_count = 0
            try:
                gpu_info = self.get_gpu_info()
                gpu_count = len(gpu_info) if gpu_info else 0
            except:
                pass
            
            # Disk
            disk_usage = psutil.disk_usage('/')
            total_disk_gb = disk_usage.total / (1024**3)
            available_disk_gb = disk_usage.free / (1024**3)
            
            # Проверяем уже запущенные контейнеры и вычитаем их ресурсы
            running_containers_resources = self._get_running_containers_resources()
            
            # Вычитаем ресурсы уже запущенных контейнеров
            if running_containers_resources:
                available_ram_gb = max(1, available_ram_gb - running_containers_resources.get('ram_gb', 0))
                available_disk_gb = max(10, available_disk_gb - running_containers_resources.get('disk_gb', 0))
                # GPU считаем как общее количество, так как Docker может использовать все GPU
                # CPU также считаем как общее количество, так как Docker может ограничивать по ядрам
            
            print(f"[INFO] System resources:")
            print(f"  Total CPU cores: {cpu_count}")
            print(f"  Available RAM: {available_ram_gb:.1f}GB")
            print(f"  Available disk: {available_disk_gb:.1f}GB")
            print(f"  GPU count: {gpu_count}")
            if running_containers_resources:
                print(f"  Running containers using: {running_containers_resources.get('ram_gb', 0):.1f}GB RAM, {running_containers_resources.get('disk_gb', 0):.1f}GB disk")
            
            return {
                'cpu_count': cpu_count,
                'cpu_usage_percent': cpu_percent,
                'total_ram_gb': total_ram_gb,
                'available_ram_gb': available_ram_gb,
                'gpu_count': gpu_count,
                'total_disk_gb': total_disk_gb,
                'available_disk_gb': available_disk_gb
            }
        except Exception as e:
            print(f"[ERROR] Failed to get available resources: {e}")
            return None

    def _get_running_containers_resources(self) -> Optional[Dict[str, Any]]:
        """Получает информацию о ресурсах уже запущенных Docker контейнеров"""
        try:
            import subprocess
            
            # Получаем список запущенных контейнеров
            result = subprocess.run(['docker', 'ps', '--format', '{{.Names}}'], 
                                  capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                return None
            
            container_names = result.stdout.strip().split('\n') if result.stdout.strip() else []
            
            total_ram_gb = 0
            total_disk_gb = 0
            
            for container_name in container_names:
                if not container_name:
                    continue
                
                # Получаем информацию о контейнере
                try:
                    # Получаем использование памяти
                    mem_result = subprocess.run(['docker', 'stats', '--no-stream', '--format', '{{.MemUsage}}', container_name], 
                                              capture_output=True, text=True, timeout=5)
                    if mem_result.returncode == 0 and mem_result.stdout.strip():
                        mem_str = mem_result.stdout.strip()
                        # Парсим строку вида "1.234MiB / 2GiB"
                        mem_match = re.search(r'(\d+(?:\.\d+)?)([KMGT]iB)', mem_str)
                        if mem_match:
                            mem_value = float(mem_match.group(1))
                            mem_unit = mem_match.group(2)
                            # Конвертируем в GB
                            if mem_unit == 'KiB':
                                mem_gb = mem_value / (1024**2)
                            elif mem_unit == 'MiB':
                                mem_gb = mem_value / 1024
                            elif mem_unit == 'GiB':
                                mem_gb = mem_value
                            else:
                                mem_gb = mem_value / (1024**3)
                            total_ram_gb += mem_gb
                    
                    # Получаем использование диска (упрощенно)
                    # Docker не предоставляет простой способ получить использование диска
                    # Поэтому используем приблизительную оценку
                    total_disk_gb += 1  # Примерно 1GB на контейнер
                    
                except Exception as e:
                    print(f"[WARNING] Failed to get resources for container {container_name}: {e}")
                    continue
            
            return {
                'ram_gb': total_ram_gb,
                'disk_gb': total_disk_gb
            }
            
        except Exception as e:
            print(f"[WARNING] Failed to get running containers resources: {e}")
            return None
    
    def get_system_info(self) -> Dict[str, Any]:
        """Получает полную системную информацию"""
        print("[DEBUG] Getting hostname...")
        try:
            hostname = self.get_hostname()
            print(f"[DEBUG] Hostname: {hostname}")
        except Exception as e:
            print(f"[WARNING] Failed to get hostname: {e}")
            hostname = "unknown"
        
        print("[DEBUG] Getting IP address...")
        try:
            ip_address = self.get_ip_address()
            print(f"[DEBUG] IP address: {ip_address}")
        except Exception as e:
            print(f"[WARNING] Failed to get IP address: {e}")
            ip_address = "unknown"
        
        print("[DEBUG] Getting RAM info...")
        try:
            total_ram_gb, ram_type = self.get_ram_info()
            print(f"[DEBUG] RAM: {total_ram_gb}GB, type: {ram_type}")
        except Exception as e:
            print(f"[WARNING] Failed to get RAM info: {e}")
            total_ram_gb, ram_type = 0, "unknown"
        
        print("[DEBUG] Getting hardware info...")
        hardware_info = self.get_hardware_info()
        print("[DEBUG] Hardware info collected")
        
        return {
            "hostname": hostname,
            "ip_address": ip_address,
            "total_ram_gb": total_ram_gb,
            "ram_type": ram_type,
            "hardware_info": hardware_info
        }
    
    def get_hardware_info(self) -> Dict[str, Any]:
        """Получает информацию о железе"""
        print("[DEBUG] Getting CPU info...")
        try:
            cpus = self.get_cpu_info()
            print(f"[DEBUG] CPU info collected: {len(cpus)} CPUs")
        except Exception as e:
            print(f"[WARNING] Failed to get CPU info: {e}")
            cpus = []
        
        print("[DEBUG] Getting GPU info...")
        try:
            gpus = self.get_gpu_info()
            print(f"[DEBUG] GPU info collected: {len(gpus)} GPUs")
        except Exception as e:
            print(f"[WARNING] Failed to get GPU info: {e}")
            gpus = []
        
        print("[DEBUG] Getting disk info...")
        try:
            disks = self.get_disk_info()
            print(f"[DEBUG] Disk info collected: {len(disks)} disks")
        except Exception as e:
            print(f"[WARNING] Failed to get disk info: {e}")
            disks = []
        
        print("[DEBUG] Getting network info...")
        try:
            networks = self.get_network_info()
            print(f"[DEBUG] Network info collected: {len(networks)} networks")
        except Exception as e:
            print(f"[WARNING] Failed to get network info: {e}")
            networks = []
        
        return {
            "cpus": cpus,
            "gpus": gpus,
            "disks": disks,
            "networks": networks
        }
    
    def clear_cache(self):
        """Очищает кэш данных"""
        self._cpu_info_cache = None
        self._gpu_info_cache = None
        self._disk_info_cache = None
        self._network_info_cache = None
        self._ram_info_cache = None
