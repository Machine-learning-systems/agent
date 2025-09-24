#!/bin/bash

SERVICE_NAME="gpugo-agent"
SERVICE_FILE="/etc/systemd/system/gpugo-agent.service"
KEY_FILE=".agent_key"

case "$1" in
    install)
        [ -z "$2" ] && echo "Usage: $0 install SECRET_KEY" && exit 1
        echo "$2" > "$KEY_FILE"
        UV_PATH="/root/.local/bin/uv"
        sudo test -f "$UV_PATH" || { echo "uv not found at $UV_PATH"; exit 1; }
        cat > temp_service << EOF
[Unit]
Description=GpuGo Agent
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=root
WorkingDirectory=$(pwd)
Environment="PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$HOME/.cargo/bin"
ExecStart=$UV_PATH run agent.py $2
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
        sudo mv temp_service "$SERVICE_FILE"
        sudo systemctl daemon-reload
        sudo systemctl enable "$SERVICE_NAME"
        sudo systemctl start "$SERVICE_NAME"
        ;;
    
    start|restart)
        [ ! -f "$KEY_FILE" ] && echo "Run install first" && exit 1
        [ "$1" = "start" ] && sudo systemctl start "$SERVICE_NAME"
        [ "$1" = "restart" ] && sudo systemctl restart "$SERVICE_NAME"
        ;;
    
    stop)
        [ ! -f "$KEY_FILE" ] && echo "Run install first" && exit 1
        sudo systemctl stop "$SERVICE_NAME"
        ;;
    
    status)
        [ ! -f "$KEY_FILE" ] && echo "Run install first" && exit 1
        sudo systemctl status "$SERVICE_NAME"
        ;;
    
    logs)
        [ ! -f "$KEY_FILE" ] && echo "Run install first" && exit 1
        sudo journalctl -u "$SERVICE_NAME" -f
        ;;
    
    uninstall)
        [ ! -f "$KEY_FILE" ] && echo "Nothing to uninstall" && exit 1
        sudo systemctl stop "$SERVICE_NAME" 2>/dev/null
        sudo systemctl disable "$SERVICE_NAME" 2>/dev/null
        sudo rm -f "$SERVICE_FILE"
        sudo systemctl daemon-reload
        rm -f "$KEY_FILE"
        ;;
    
    *)
        echo "Usage: $0 {install SECRET_KEY|start|stop|restart|status|logs|uninstall}"
        exit 1
        ;;
esac