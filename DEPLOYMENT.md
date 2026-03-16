# 中纪委爬虫API 生产环境部署指南

本文档详细介绍如何将中纪委腐败舆情爬虫API部署到生产环境。

---

## 目录

1. [部署概述](#1-部署概述)
2. [环境要求](#2-环境要求)
3. [部署方案](#3-部署方案)
   - 方案一：直接部署（Linux服务器）
   - 方案二：Docker部署（推荐）
   - 方案三：云服务器部署（阿里云/腾讯云）
4. [配置说明](#4-配置说明)
5. [Nginx反向代理](#5-nginx反向代理)
6. [HTTPS配置](#6-https配置)
7. [监控与维护](#7-监控与维护)
8. [故障排查](#8-故障排查)

---

## 1. 部署概述

### 1.1 架构说明

```
用户请求 → Nginx → Gunicorn → FastAPI应用 → 爬虫引擎
                          ↓
                    内存状态存储(task_status)
                          ↓
                    结果文件(api_results/)
```

### 1.2 部署流程图

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  准备环境    │ → │  部署应用    │ → │ 配置Nginx   │ → │  配置HTTPS  │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
       │                  │                  │                  │
       ▼                  ▼                  ▼                  ▼
  - 安装Python       - 安装依赖        - 反向代理        - SSL证书
  - 安装Chrome       - 配置环境变量    - 负载均衡        - 自动续期
  - 创建目录         - 启动服务        - 静态文件        - 安全头配置
```

---

## 2. 环境要求

### 2.1 系统要求

| 项目 | 最低配置 | 推荐配置 |
|------|---------|---------|
| CPU | 2核 | 4核+ |
| 内存 | 4GB | 8GB+ |
| 磁盘 | 20GB | 50GB+ SSD |
| 带宽 | 5Mbps | 10Mbps+ |
| 操作系统 | Ubuntu 20.04/22.04 | Ubuntu 22.04 LTS |

### 2.2 软件依赖

- Python 3.8+
- Chrome浏览器（用于爬虫）
- Nginx（反向代理）
- Git

### 2.3 网络要求

- 可访问互联网（访问中纪委网站）
- 可访问KIMI API（如使用AI分析）
- 开放端口：22(SSH), 80(HTTP), 443(HTTPS), 8000(API服务)

---

## 3. 部署方案

### 方案一：直接部署（Linux服务器）

#### 步骤1：系统初始化

```bash
# 更新系统
sudo apt-get update
sudo apt-get upgrade -y

# 安装基础工具
sudo apt-get install -y git curl wget vim unzip build-essential

# 安装Python
sudo apt-get install -y python3 python3-pip python3-venv

# 验证安装
python3 --version  # 应显示 3.8+
pip3 --version
```

#### 步骤2：安装Chrome浏览器

```bash
# 下载并安装Chrome
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt-get install -y ./google-chrome-stable_current_amd64.deb

# 解决依赖问题（如有）
sudo apt-get --fix-broken install -y

# 验证安装
google-chrome --version
```

#### 步骤3：创建应用目录

```bash
# 创建应用目录
sudo mkdir -p /opt/ccdi_crawler
sudo chown $USER:$USER /opt/ccdi_crawler
cd /opt/ccdi_crawler

# 克隆代码（或上传代码）
git clone <your-repo-url> .
# 或者使用 scp/rsync 上传代码
```

#### 步骤4：配置Python虚拟环境

```bash
# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 升级pip
pip install --upgrade pip

# 安装依赖
pip install -r requirements.txt

# 安装生产环境服务器
pip install gunicorn
```

#### 步骤5：配置环境变量

```bash
# 创建环境变量文件
sudo vim /etc/ccdi_crawler.env
```

添加以下内容：

```bash
# API配置
MOONSHOT_API_KEY=sk-your-api-key-here
MAX_PAGES=5
HEADLESS=true
LOG_LEVEL=info

# 路径配置
RESULTS_DIR=/opt/ccdi_crawler/api_results
LOG_DIR=/var/log/ccdi_crawler

# 安全配置
ALLOWED_HOSTS=*
CORS_ORIGINS=*
```

加载环境变量：

```bash
# 设置文件权限
sudo chmod 600 /etc/ccdi_crawler.env

# 加载环境变量
export $(grep -v '^#' /etc/ccdi_crawler.env | xargs)
```

#### 步骤6：创建日志目录

```bash
# 创建日志目录
sudo mkdir -p /var/log/ccdi_crawler
sudo chown $USER:$USER /var/log/ccdi_crawler

# 创建结果目录
mkdir -p /opt/ccdi_crawler/api_results
```

#### 步骤7：测试启动

```bash
# 进入应用目录
cd /opt/ccdi_crawler
source venv/bin/activate

# 测试启动
python api.py

# 访问测试（另开终端）
curl http://localhost:8000/health
```

看到以下输出表示成功：

```json
{"status":"healthy","timestamp":"2026-03-16T...","active_tasks":0,"total_tasks":0}
```

按 `Ctrl+C` 停止测试。

#### 步骤8：配置systemd服务

```bash
# 创建服务文件
sudo vim /etc/systemd/system/ccdi-api.service
```

添加以下内容：

```ini
[Unit]
Description=中纪委腐败舆情爬虫API
Documentation=https://your-docs-url.com
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/ccdi_crawler
Environment="PATH=/opt/ccdi_crawler/venv/bin"
Environment="PYTHONPATH=/opt/ccdi_crawler"
EnvironmentFile=/etc/ccdi_crawler.env

# 启动命令
ExecStart=/opt/ccdi_crawler/venv/bin/gunicorn \
    api:app \
    -w 4 \
    -k uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000 \
    --access-logfile /var/log/ccdi_crawler/access.log \
    --error-logfile /var/log/ccdi_crawler/error.log \
    --capture-output \
    --enable-stdio-inheritance

# 重启配置
Restart=always
RestartSec=5

# 资源限制
LimitAS=2G
LimitRSS=2G
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
```

#### 步骤9：启动服务

```bash
# 重载systemd配置
sudo systemctl daemon-reload

# 启动服务
sudo systemctl start ccdi-api

# 设置开机自启
sudo systemctl enable ccdi-api

# 查看状态
sudo systemctl status ccdi-api

# 查看日志
sudo journalctl -u ccdi-api -f
```

---

### 方案二：Docker部署（推荐）

#### 步骤1：安装Docker

```bash
# 安装Docker
curl -fsSL https://get.docker.com | sh

# 添加用户到docker组
sudo usermod -aG docker $USER
newgrp docker

# 验证安装
docker --version
docker-compose --version
```

#### 步骤2：创建Dockerfile

在应用根目录创建 `Dockerfile`：

```dockerfile
FROM python:3.11-slim

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    chromium \
    chromium-driver \
    fonts-wqy-zenhei \
    fonts-wqy-microhei \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# 设置Chrome环境变量
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

# 创建工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn

# 复制应用代码
COPY . .

# 创建结果目录
RUN mkdir -p /app/api_results

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 启动命令
CMD ["gunicorn", "api:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--access-logfile", "-", "--error-logfile", "-"]
```

#### 步骤3：创建docker-compose.yml

```yaml
version: '3.8'

services:
  ccdi-api:
    build: .
    container_name: ccdi-crawler-api
    restart: always
    ports:
      - "8000:8000"
    environment:
      - MOONSHOT_API_KEY=${MOONSHOT_API_KEY}
      - MAX_PAGES=${MAX_PAGES:-5}
      - HEADLESS=${HEADLESS:-true}
      - LOG_LEVEL=${LOG_LEVEL:-info}
    volumes:
      - ./api_results:/app/api_results
      - ./logs:/app/logs
    networks:
      - ccdi-network
    # 资源限制
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G

  # 可选：添加Nginx反向代理
  nginx:
    image: nginx:alpine
    container_name: ccdi-nginx
    restart: always
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - ccdi-api
    networks:
      - ccdi-network

networks:
  ccdi-network:
    driver: bridge
```

#### 步骤4：创建环境文件

```bash
# 创建环境变量文件
cat > .env << EOF
MOONSHOT_API_KEY=sk-your-api-key-here
MAX_PAGES=5
HEADLESS=true
LOG_LEVEL=info
EOF
```

#### 步骤5：构建并启动

```bash
# 构建镜像
docker-compose build

# 启动服务（后台运行）
docker-compose up -d

# 查看日志
docker-compose logs -f ccdi-api

# 查看状态
docker-compose ps

# 健康检查
curl http://localhost:8000/health
```

#### 步骤6：常用Docker命令

```bash
# 停止服务
docker-compose down

# 重启服务
docker-compose restart

# 更新部署
docker-compose pull
docker-compose up -d

# 进入容器
docker exec -it ccdi-crawler-api /bin/bash

# 查看资源使用
docker stats ccdi-crawler-api
```

---

### 方案三：云服务器部署（阿里云/腾讯云）

#### 步骤1：购买服务器

推荐配置：
- **ECS实例**：2核4G起，推荐4核8G
- **系统盘**：50GB SSD
- **带宽**：5Mbps起
- **系统**：Ubuntu 22.04 LTS

#### 步骤2：配置安全组

在阿里云/腾讯云控制台配置安全组规则：

| 类型 | 端口 | 来源 | 说明 |
|------|------|------|------|
| SSH | 22 | 你的IP | 远程登录 |
| HTTP | 80 | 0.0.0.0/0 | Web访问 |
| HTTPS | 443 | 0.0.0.0/0 | 安全Web访问 |
| Custom | 8000 | 0.0.0.0/0 | API服务（开发测试）|

#### 步骤3：域名解析

1. 购买域名（如阿里云万网）
2. 添加A记录：
   - 主机记录：`api`
   - 记录值：服务器公网IP
3. 等待DNS生效（通常10分钟-24小时）

#### 步骤4：部署应用

按照**方案一**或**方案二**的步骤部署应用。

#### 步骤5：配置SSL证书

见下文 [HTTPS配置](#6-https配置) 部分。

---

## 4. 配置说明

### 4.1 环境变量配置

| 变量名 | 必填 | 默认值 | 说明 |
|--------|------|--------|------|
| MOONSHOT_API_KEY | 是 | - | KIMI API密钥 |
| MAX_PAGES | 否 | 5 | 最大翻页数（1-10） |
| HEADLESS | 否 | true | 是否使用无头浏览器 |
| LOG_LEVEL | 否 | info | 日志级别(debug/info/warning/error) |
| RESULTS_DIR | 否 | ./api_results | 结果文件保存目录 |
| WORKERS | 否 | 4 | Gunicorn工作进程数 |
| TIMEOUT | 否 | 300 | 请求超时时间（秒） |

### 4.2 Gunicorn配置优化

创建 `gunicorn.conf.py`：

```python
import multiprocessing

# 工作进程数
workers = multiprocessing.cpu_count() * 2 + 1

# 工作模式
worker_class = "uvicorn.workers.UvicornWorker"

# 绑定地址
bind = "0.0.0.0:8000"

# 超时设置（爬虫可能需要较长时间）
timeout = 600
keepalive = 5

# 日志配置
accesslog = "/var/log/ccdi_crawler/access.log"
errorlog = "/var/log/ccdi_crawler/error.log"
loglevel = "info"

# 进程名称
proc_name = "ccdi-api"

# 工作进程临时目录
worker_tmp_dir = "/dev/shm"

# 最大并发连接数
worker_connections = 1000

# 预加载应用（节省内存）
preload_app = True
```

启动命令改为：

```bash
gunicorn -c gunicorn.conf.py api:app
```

---

## 5. Nginx反向代理

### 5.1 安装Nginx

```bash
sudo apt-get update
sudo apt-get install -y nginx

# 验证安装
nginx -v
sudo systemctl status nginx
```

### 5.2 配置Nginx

创建配置文件：

```bash
sudo vim /etc/nginx/sites-available/ccdi-api
```

添加以下内容：

```nginx
upstream ccdi_api {
    server 127.0.0.1:8000;
    # 如果使用多个worker，可以添加更多
    # server 127.0.0.1:8001;
}

server {
    listen 80;
    server_name your-domain.com;  # 替换为你的域名

    # 日志配置
    access_log /var/log/nginx/ccdi-api-access.log;
    error_log /var/log/nginx/ccdi-api-error.log;

    # 客户端上传限制
    client_max_body_size 50M;

    # 代理设置
    location / {
        proxy_pass http://ccdi_api;
        proxy_http_version 1.1;

        # WebSocket支持（如需要）
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';

        # 转发真实IP
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 超时设置
        proxy_connect_timeout 600s;
        proxy_send_timeout 600s;
        proxy_read_timeout 600s;
    }

    # 静态文件（如果有）
    location /static {
        alias /opt/ccdi_crawler/static;
        expires 1d;
    }

    # 健康检查
    location /nginx-health {
        access_log off;
        return 200 "healthy\n";
        add_header Content-Type text/plain;
    }
}
```

启用配置：

```bash
# 创建软链接
sudo ln -s /etc/nginx/sites-available/ccdi-api /etc/nginx/sites-enabled/

# 删除默认配置（可选）
sudo rm /etc/nginx/sites-enabled/default

# 测试配置语法
sudo nginx -t

# 重载配置
sudo systemctl reload nginx
```

### 5.3 Nginx性能优化

编辑 `/etc/nginx/nginx.conf`：

```nginx
user www-data;
worker_processes auto;
pid /run/nginx.pid;
include /etc/nginx/modules-enabled/*.conf;

events {
    worker_connections 4096;
    use epoll;
    multi_accept on;
}

http {
    # 基础配置
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;

    # Gzip压缩
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css text/xml application/json application/javascript application/rss+xml application/atom+xml image/svg+xml;

    # 请求限制（防爬虫）
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;

    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    include /etc/nginx/conf.d/*.conf;
    include /etc/nginx/sites-enabled/*;
}
```

---

## 6. HTTPS配置

### 6.1 使用Certbot自动配置（推荐）

```bash
# 安装Certbot
sudo apt-get install -y certbot python3-certbot-nginx

# 获取证书并自动配置Nginx
sudo certbot --nginx -d your-domain.com

# 按照提示操作，选择重定向HTTP到HTTPS

# 测试自动续期
sudo certbot renew --dry-run
```

### 6.2 手动配置SSL

如果你有证书文件：

```bash
# 创建SSL目录
sudo mkdir -p /etc/nginx/ssl

# 上传证书文件（私钥和证书）
sudo cp your-domain.key /etc/nginx/ssl/
sudo cp your-domain.crt /etc/nginx/ssl/

# 设置权限
sudo chmod 600 /etc/nginx/ssl/*
```

修改Nginx配置：

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # SSL证书
    ssl_certificate /etc/nginx/ssl/your-domain.crt;
    ssl_certificate_key /etc/nginx/ssl/your-domain.key;

    # SSL优化
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;

    # 安全头
    add_header Strict-Transport-Security "max-age=63072000" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;

    # ... 其他配置与HTTP相同
}

# HTTP重定向到HTTPS
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}
```

---

## 7. 监控与维护

### 7.1 日志轮转配置

创建 `/etc/logrotate.d/ccdi-api`：

```
/var/log/ccdi_crawler/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0644 www-data www-data
    sharedscripts
    postrotate
        /bin/kill -HUP $(cat /var/run/syslogd.pid 2> /dev/null) 2> /dev/null || true
        systemctl reload ccdi-api
    endscript
}
```

### 7.2 监控脚本

创建 `monitor.sh`：

```bash
#!/bin/bash

# API健康检查
HEALTH=$(curl -s http://localhost:8000/health | grep -o '"status":"healthy"')

if [ -z "$HEALTH" ]; then
    echo "[$(date)] API服务异常，尝试重启..." >> /var/log/ccdi_crawler/monitor.log
    sudo systemctl restart ccdi-api

    # 发送告警（如需要）
    # curl -X POST "https://your-alert-webhook" -d "msg=API服务重启"
fi

# 磁盘空间检查
DISK_USAGE=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -gt 80 ]; then
    echo "[$(date)] 磁盘使用率超过80%: ${DISK_USAGE}%" >> /var/log/ccdi_crawler/monitor.log
fi

# 内存使用检查
MEM_USAGE=$(free | grep Mem | awk '{printf("%.0f", $3/$2 * 100.0)}')
if [ "$MEM_USAGE" -gt 90 ]; then
    echo "[$(date)] 内存使用率超过90%: ${MEM_USAGE}%" >> /var/log/ccdi_crawler/monitor.log
fi
```

添加定时任务：

```bash
# 编辑crontab
crontab -e

# 每5分钟检查一次
*/5 * * * * /opt/ccdi_crawler/monitor.sh

# 每天清理旧结果文件（保留30天）
0 2 * * * find /opt/ccdi_crawler/api_results -name "*.json" -mtime +30 -delete
```

### 7.3 备份策略

```bash
#!/bin/bash
# backup.sh

BACKUP_DIR="/backup/ccdi_crawler"
DATE=$(date +%Y%m%d)

# 创建备份目录
mkdir -p $BACKUP_DIR

# 备份结果文件
tar -czf $BACKUP_DIR/api_results_$DATE.tar.gz /opt/ccdi_crawler/api_results/

# 保留最近30天备份
find $BACKUP_DIR -name "*.tar.gz" -mtime +30 -delete

# 可选：上传到云存储
# aws s3 cp $BACKUP_DIR/api_results_$DATE.tar.gz s3://your-bucket/backups/
```

---

## 8. 故障排查

### 8.1 常见问题

#### 问题1：服务无法启动

```bash
# 查看详细错误
sudo journalctl -u ccdi-api -n 50

# 检查端口占用
sudo lsof -i :8000

# 检查环境变量
cat /etc/ccdi_crawler.env

# 检查文件权限
ls -la /opt/ccdi_crawler/
ls -la /var/log/ccdi_crawler/
```

#### 问题2：爬虫无响应

```bash
# 查看爬虫日志
tail -f /var/log/ccdi_crawler/error.log

# 检查Chrome进程
ps aux | grep chrome

# 检查内存使用
free -h

# 重启服务
sudo systemctl restart ccdi-api
```

#### 问题3：Nginx 502错误

```bash
# 检查API服务状态
sudo systemctl status ccdi-api
curl http://localhost:8000/health

# 检查Nginx日志
sudo tail -f /var/log/nginx/ccdi-api-error.log

# 检查SELinux（如有）
sudo getenforce
sudo setenforce 0  # 临时禁用测试
```

#### 问题4：磁盘空间不足

```bash
# 查看磁盘使用
df -h

# 查看大文件
sudo du -sh /opt/ccdi_crawler/api_results/* | sort -hr | head -10

# 清理旧文件
find /opt/ccdi_crawler/api_results -name "*.json" -mtime +7 -delete
```

### 8.2 调试模式

```bash
# 临时以前台模式启动查看错误
cd /opt/ccdi_crawler
source venv/bin/activate
gunicorn api:app -w 1 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 --log-level debug
```

### 8.3 联系支持

如遇到无法解决的问题：
1. 收集日志：`sudo tar -czf debug.tar.gz /var/log/ccdi_crawler/`
2. 查看系统信息：`uname -a && cat /etc/os-release`
3. 提供复现步骤

---

## 附录

### A. 快速部署脚本

```bash
#!/bin/bash
# quick-deploy.sh - 一键部署脚本

set -e

echo "=== 中纪委爬虫API 快速部署脚本 ==="

# 1. 更新系统
sudo apt-get update

# 2. 安装依赖
echo "[*] 安装依赖..."
sudo apt-get install -y python3-pip python3-venv git nginx

# 3. 安装Chrome
echo "[*] 安装Chrome..."
wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt-get install -y ./google-chrome-stable_current_amd64.deb || sudo apt-get --fix-broken install -y
rm -f google-chrome-stable_current_amd64.deb

# 4. 克隆代码
echo "[*] 部署应用..."
cd /opt
sudo git clone https://your-repo-url.git ccdi_crawler || true
sudo chown -R $USER:$USER /opt/ccdi_crawler
cd /opt/ccdi_crawler

# 5. 配置环境
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt gunicorn

# 6. 启动服务
echo "[*] 启动服务..."
sudo cp deployment/ccdi-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ccdi-api
sudo systemctl start ccdi-api

echo "=== 部署完成 ==="
echo "访问地址: http://$(curl -s ifconfig.me):8000"
echo "健康检查: curl http://localhost:8000/health"
```

### B. API调用示例

```python
import requests
import time

API_URL = "https://your-domain.com"

# 1. 启动任务
response = requests.post(f"{API_URL}/crawl", json={
    "urls_dict": {
        "国家单位执纪审查": "https://www.ccdi.gov.cn/scdcn/zyyj/zjsc/"
    },
    "risk_keywords": ["工商银行", "工行"],
    "max_pages": 1,
    "headless": True
})
task_id = response.json()["task_id"]
print(f"任务ID: {task_id}")

# 2. 轮询状态
while True:
    status = requests.get(f"{API_URL}/tasks/{task_id}").json()
    print(f"状态: {status['status']}, 进度: {status['progress']}%")
    if status["status"] in ["completed", "failed"]:
        break
    time.sleep(5)

# 3. 获取结果
results = requests.get(f"{API_URL}/tasks/{task_id}/results").json()
print(f"共获取 {results['total']} 条记录")
```

---

**文档版本**: 1.0
**更新日期**: 2026-03-16
**维护者**: Your Name
