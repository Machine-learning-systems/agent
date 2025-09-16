#!/usr/bin/env python
# -*- coding: utf-8 -*-

import socket
import subprocess
import time
import os
from typing import Optional, Dict, Any
from clean_manager import ContainerManager


class APIContainerManager(ContainerManager):
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

    def wait_for_ssh_ready(self, host: str, port: int, timeout: int = 60) -> bool:
        """Ждет, пока SSH сервис будет готов к подключению"""
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
