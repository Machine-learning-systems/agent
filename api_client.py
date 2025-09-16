#!/usr/bin/env python
# -*- coding: utf-8 -*-


import requests
import json
import time
import threading
from typing import Dict, Any, Optional, List


class APIClient:
    """Класс для взаимодействия с API gpunix.ru"""
    
    def __init__(self, base_url: str = "https://api.gpunix.ru", agent_id: Optional[str] = None, secret_key: Optional[str] = None):
        self.base_url = base_url
        self.agent_id = agent_id
        self.secret_key = secret_key
        self.session = requests.Session()
        self.session.timeout = 15
        
    def set_credentials(self, agent_id: str, secret_key: str):
        """Устанавливает учетные данные агента"""
        self.agent_id = agent_id
        self.secret_key = secret_key
    
    def _get_headers(self) -> Dict[str, str]:
        """Возвращает заголовки для запросов"""
        headers = {
            "Content-Type": "application/json"
        }
        if self.secret_key:
            headers["X-Agent-Secret-Key"] = self.secret_key
        return headers
    
    def send_log(self, message: str) -> bool:
        """Отправляет короткое лог-сообщение на бэкенд
        POST /v1/agents/{agent_id}/logs, body {"message": "..."}
        """
        if not self.agent_id:
            return False
        url = f"{self.base_url}/v1/agents/{self.agent_id}/logs"
        # Логи не требуют аутентификацию; отправляем только content-type
        headers = {"Content-Type": "application/json"}
        try:
            resp = self.session.post(url, headers=headers, json={"message": str(message)}, timeout=5)
            return resp.status_code == 200
        except Exception:
            # Ничего не печатаем и не ретраим, чтобы не зациклиться
            return False
    
    def confirm_agent(self, data: Dict[str, Any]) -> Optional[str]:
        """Подтверждает агента на сервере и получает agent_id"""
        url = f"{self.base_url}/v1/agents/confirm"
        headers = self._get_headers()
        
        try:
            response = self.session.post(url, headers=headers, json=data, timeout=10)
            
            resp_json = response.json()
            agent_id = None
            
            if resp_json and isinstance(resp_json, dict):
                data_field = resp_json.get("data")
                if data_field and isinstance(data_field, dict):
                    agent_id = data_field.get("agent_id") or data_field.get("id")
            
            return agent_id
            
        except Exception as e:
            print(f"[ERROR] Failed to confirm agent: {e}")
            # Отправляем ошибку в логи, если уже есть agent_id
            try:
                self.send_log(f"confirm_agent error: {e}")
            except Exception:
                pass
            return None
    
    def send_init_data(self, data: Dict[str, Any]) -> bool:
        """Отправляет данные инициализации агента"""
        if not self.agent_id:
            print("[ERROR] Agent ID not set")
            return False
            
        url = f"{self.base_url}/v1/agents/{self.agent_id}/init"
        headers = self._get_headers()
        
        try:
            response = self.session.post(url, headers=headers, json=data, timeout=10)
            
            if response.status_code == 200:
                resp_json = response.json()
                if resp_json.get('exception') == 0:
                    return True
                else:
                    print(f"[WARNING] Server returned exception: {resp_json.get('message', 'Unknown error')}")
                    try:
                        self.send_log(f"init exception: {resp_json.get('message', 'Unknown error')}")
                    except Exception:
                        pass
                    return False
            else:
                print(f"[ERROR] Init failed with status {response.status_code}")
                try:
                    self.send_log(f"init failed with status {response.status_code}")
                except Exception:
                    pass
                return False
                
        except Exception as e:
            print(f"[ERROR] Failed to send init data: {e}")
            try:
                self.send_log(f"init error: {e}")
            except Exception:
                pass
            return False
    
    def poll_for_tasks(self, callback: callable) -> None:
        """Опрашивает сервер на наличие задач"""
        if not self.agent_id:
            print("[ERROR] Agent ID not set")
            return
            
        url = f"{self.base_url}/v1/agents/{self.agent_id}/tasks/pull"
        headers = self._get_headers()
        
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        while True:
            try:
                # print(f"[DEBUG] Polling for tasks from {url}")
                response = self.session.post(url, headers=headers, timeout=15)
                
                if response.status_code == 200:
                    resp_json = response.json()
                    
                    # Проверяем exception поле
                    if resp_json.get('exception') != 0:
                        print(f"[WARNING] Server returned exception: {resp_json.get('message', 'Unknown error')}")
                        try:
                            self.send_log(f"poll exception: {resp_json.get('message', 'Unknown error')}")
                        except Exception:
                            pass
                        consecutive_errors += 1
                        time.sleep(10)
                        continue
                    
                    data = resp_json.get('data', {})
                    task_id = data.get('task_id')
                    task_data = data.get('task_data')
                    container_info = data.get('container_info')
                    message = data.get('message', '')
                    
                    # print(f"[INFO] Server response: {message}")
                    
                    if task_id is not None and task_data is not None and container_info is not None:
                        print(f"[INFO] New task received:")
                        
                        print(f"  Data: {data}")

                        print(f"  Task ID: {task_id}")
                        print(f"  Docker Image: {task_data.get('docker_image')}")
                        print(f"  SSH Username: {container_info.get('ssh_username')}")
                        print(f"  SSH Port: {container_info.get('ssh_port')}")
                        print(f"  SSH Command: {container_info.get('ssh_command')}")
                        try:
                            op = (task_data.get('operation') or 'start').strip().lower()
                            self.send_log(f"task received: id={task_id} op={op}")
                        except Exception:
                            pass
                        
                        # Создаем полную задачу
                        full_task = {
                            'id': task_id,
                            'task_data': task_data,
                            'container_info': container_info
                        }
                        
                        # Вызываем callback с задачей
                        try:
                            result = callback(full_task)
                            if result:
                                # Отправляем статус задачи
                                self.send_task_status(task_id, result)
                                consecutive_errors = 0
                            else:
                                print(f"[ERROR] Failed to process task {task_id}")
                                try:
                                    self.send_log(f"task process failed: id={task_id}")
                                except Exception:
                                    pass
                                consecutive_errors += 1
                        except Exception as e:
                            print(f"[ERROR] Task processing failed: {e}")
                            try:
                                self.send_log(f"task processing exception: id={task_id} error={e}")
                            except Exception:
                                pass
                            consecutive_errors += 1
                            
                    elif task_id is None:
                        # print(f"[INFO] No tasks available: {message}")
                        consecutive_errors = 0
                    else:
                        print(f"[WARNING] Invalid task data received: {data}")
                        try:
                            self.send_log("invalid task data received")
                        except Exception:
                            pass
                        consecutive_errors += 1
                else:
                    print(f"[WARNING] Server returned status {response.status_code}")
                    # print(f"[DEBUG] Server response: {response.text}")
                    try:
                        self.send_log(f"poll failed with status {response.status_code}")
                    except Exception:
                        pass
                    consecutive_errors += 1
                    
            except requests.exceptions.Timeout:
                print("[WARNING] Request timeout, retrying...")
                try:
                    self.send_log("poll timeout")
                except Exception:
                    pass
                consecutive_errors += 1
            except requests.exceptions.ConnectionError:
                print("[WARNING] Connection error, retrying...")
                try:
                    self.send_log("poll connection error")
                except Exception:
                    pass
                consecutive_errors += 1
            except Exception as e:
                print(f"[ERROR] Polling failed: {e}")
                try:
                    self.send_log(f"poll exception: {e}")
                except Exception:
                    pass
                consecutive_errors += 1
            
            # Если слишком много ошибок подряд, увеличиваем интервал
            if consecutive_errors >= max_consecutive_errors:
                print(f"[WARNING] Too many consecutive errors ({consecutive_errors}), increasing poll interval")
                time.sleep(60)
            else:
                time.sleep(10)
    
    def send_task_status(self, task_id: str, container_info: Dict[str, Any]) -> bool:
        """Отправляет статус задачи
        Ожидает поля в container_info:
          - status: "running" | "completed" | "failed"
          - container_id: str
          - container_name: optional
          - error_message: optional (для failed)
          - ssh_host/ssh_port/ssh_command: используются только для running-логики START
        Если статус не указан, по умолчанию отправляется running (совместимость).
        """
        if not self.agent_id:
            print("[ERROR] Agent ID not set")
            return False
            
        url = f"{self.base_url}/v1/agents/{self.agent_id}/tasks/{task_id}/status"
        headers = self._get_headers()
        
        status = container_info.get("status") or "running"
        data = {
            "status": status,
            "container_id": container_info.get('container_id'),
        }
        if container_info.get('container_name') is not None:
            data["container_name"] = container_info.get('container_name')
        if status == "running":
            # Совместимость: добавляем прогресс и output если известны ssh_host/port
            ssh_host = container_info.get('ssh_host')
            ssh_port = container_info.get('ssh_port')
            cname = container_info.get('container_name')
            data["progress"] = 0.0
            if ssh_host and ssh_port and cname:
                data["output"] = f"Container {cname} started successfully. SSH ready on {ssh_host}:{ssh_port}"
        elif status == "failed":
            if container_info.get('error_message'):
                data["error_message"] = container_info.get('error_message')
        
        try:
            response = self.session.post(url, headers=headers, json=data, timeout=10)
            
            if response.status_code == 200:
                resp_json = response.json()
                if resp_json.get('exception') == 0:
                    return True
                else:
                    print(f"[WARNING] Server returned exception: {resp_json.get('message', 'Unknown error')}")
                    try:
                        self.send_log(f"task status exception: id={task_id} msg={resp_json.get('message', 'Unknown error')}")
                    except Exception:
                        pass
                    return False
            else:
                print(f"[WARNING] Server returned status {response.status_code}: {response.text}")
                try:
                    self.send_log(f"task status failed: id={task_id} status={response.status_code}")
                except Exception:
                    pass
                return False
                
        except Exception as e:
            print(f"[ERROR] Failed to update task status: {e}")
            try:
                self.send_log(f"task status exception: id={task_id} error={e}")
            except Exception:
                pass
            return False
    
    def send_heartbeat(self, monitoring_data: Dict[str, Any]) -> bool:
        """Отправляет heartbeat с информацией о состоянии агента"""
        if not self.agent_id:
            print("[ERROR] Agent ID not set")
            return False
            
        url = f"{self.base_url}/v1/agents/{self.agent_id}/heartbeat"
        headers = self._get_headers()
        
        data = {
            "status": "online",
            **monitoring_data
        }
        
        try:
            response = self.session.post(url, headers=headers, json=data, timeout=10)
            
            if response.status_code == 200:
                resp_json = response.json()
                if resp_json.get('exception') == 0:
                    return True
                else:
                    print(f"[WARNING] Heartbeat failed: {resp_json.get('message', 'Unknown error')}")
                    try:
                        self.send_log(f"heartbeat exception: {resp_json.get('message', 'Unknown error')}")
                    except Exception:
                        pass
                    return False
            else:
                print(f"[WARNING] Heartbeat failed with status {response.status_code}")
                try:
                    self.send_log(f"heartbeat failed with status {response.status_code}")
                except Exception:
                    pass
                return False
                
        except Exception as e:
            print(f"[ERROR] Failed to send heartbeat: {e}")
            try:
                self.send_log(f"heartbeat exception: {e}")
            except Exception:
                pass
            return False
    
    def start_polling_thread(self, callback: callable) -> threading.Thread:
        """Запускает поток для опроса задач"""
        polling_thread = threading.Thread(target=self.poll_for_tasks, args=(callback,), daemon=True)
        polling_thread.start()
        print("[INFO] Polling thread started successfully")
        return polling_thread
    
    def close(self):
        """Закрывает сессию"""
        if self.session:
            self.session.close()
