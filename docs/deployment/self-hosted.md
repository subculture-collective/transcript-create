# Self-Hosted Deployment Guide

Complete guide for deploying transcript-create on your own bare-metal or VM server with Ubuntu/Debian.

## Table of Contents

1. [Overview](#overview)
2. [Server Requirements](#server-requirements)
3. [Initial Server Setup](#initial-server-setup)
4. [Install Dependencies](#install-dependencies)
5. [GPU Driver Installation](#gpu-driver-installation)
6. [Application Setup](#application-setup)
7. [Systemd Services](#systemd-services)
8. [Nginx Reverse Proxy](#nginx-reverse-proxy)
9. [SSL with Certbot](#ssl-with-certbot)
10. [Monitoring and Logging](#monitoring-and-logging)
11. [Maintenance](#maintenance)

## Overview

This guide covers deploying transcript-create on a single server without Docker or Kubernetes, using systemd services and native dependencies.

**When to use this approach:**
- You have a powerful server with GPU
- You want maximum performance without containerization overhead
- You need fine-grained control over the environment
- You're running on bare metal or dedicated server

**Trade-offs:**
- More manual setup and maintenance
- Requires more Linux administration knowledge
- Updates are more complex
- Less portable than containers

## Server Requirements

### Minimum Specifications

- **CPU**: 8+ cores
- **RAM**: 32 GB
- **Storage**: 500 GB SSD
- **GPU**: NVIDIA (8GB+ VRAM) or AMD (16GB+ VRAM)
- **OS**: Ubuntu 22.04 LTS or Debian 12 (recommended)
- **Network**: Public IP, 100+ Mbps

### Recommended Specifications

- **CPU**: 16+ cores (AMD Ryzen 9 or Intel Core i9)
- **RAM**: 64 GB
- **Storage**: 1 TB NVMe SSD
- **GPU**: NVIDIA RTX 4090 or AMD RX 7900 XTX
- **Network**: 1 Gbps, static IP

## Initial Server Setup

### 1. Update System

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y build-essential curl git vim wget software-properties-common
```

### 2. Create Application User

```bash
# Create dedicated user
sudo useradd -r -m -s /bin/bash -d /opt/transcript transcript
sudo usermod -aG video,render transcript  # For GPU access

# Create directories
sudo mkdir -p /opt/transcript/{app,data,backups,logs}
sudo chown -R transcript:transcript /opt/transcript
```

### 3. Configure Firewall

```bash
# Install and configure UFW
sudo apt install -y ufw

# Allow SSH
sudo ufw allow 22/tcp

# Allow HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Enable firewall
sudo ufw --force enable
sudo ufw status
```

### 4. Configure System Limits

```bash
# Increase file descriptors and process limits
sudo tee /etc/security/limits.d/transcript.conf > /dev/null <<'EOF'
transcript soft nofile 65536
transcript hard nofile 65536
transcript soft nproc 32768
transcript hard nproc 32768
EOF

# Apply sysctl tuning
sudo tee /etc/sysctl.d/99-transcript.conf > /dev/null <<'EOF'
# Network tuning
net.core.somaxconn = 1024
net.ipv4.tcp_max_syn_backlog = 2048
net.ipv4.ip_local_port_range = 10000 65535

# Memory tuning
vm.swappiness = 10
vm.vfs_cache_pressure = 50
EOF

sudo sysctl -p /etc/sysctl.d/99-transcript.conf
```

## Install Dependencies

### 1. Install Python 3.11

```bash
# Add deadsnakes PPA (Ubuntu) or use system Python on Debian 12
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev python3-pip

# Set Python 3.11 as default
sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1
```

### 2. Install PostgreSQL 16

```bash
# Add PostgreSQL repository
sudo sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list'
wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo apt-key add -
sudo apt update

# Install PostgreSQL
sudo apt install -y postgresql-16 postgresql-contrib-16

# Start and enable
sudo systemctl enable postgresql
sudo systemctl start postgresql

# Create database and user
sudo -u postgres psql <<EOF
CREATE DATABASE transcripts;
CREATE USER transcript WITH PASSWORD 'change-me-secure-password';
GRANT ALL PRIVILEGES ON DATABASE transcripts TO transcript;
ALTER DATABASE transcripts OWNER TO transcript;
\q
EOF

# Configure for local access
sudo tee -a /etc/postgresql/16/main/pg_hba.conf > /dev/null <<'EOF'
# transcript application
local   transcripts     transcript                              scram-sha-256
host    transcripts     transcript     127.0.0.1/32             scram-sha-256
EOF

sudo systemctl restart postgresql
```

### 3. Install Redis

```bash
sudo apt install -y redis-server

# Configure Redis
sudo tee /etc/redis/redis.conf > /dev/null <<'EOF'
bind 127.0.0.1 ::1
protected-mode yes
port 6379
daemonize yes
supervised systemd
pidfile /run/redis/redis-server.pid
loglevel notice
logfile /var/log/redis/redis-server.log
dir /var/lib/redis
save 900 1
save 300 10
save 60 10000
maxmemory 2gb
maxmemory-policy allkeys-lru
EOF

sudo systemctl enable redis-server
sudo systemctl restart redis-server
```

### 4. Install ffmpeg

```bash
sudo apt install -y ffmpeg

# Verify
ffmpeg -version
```

## GPU Driver Installation

### NVIDIA CUDA

```bash
# Install NVIDIA driver
sudo apt install -y nvidia-driver-535

# Add CUDA repository
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
sudo apt update
sudo apt install -y cuda-toolkit-12-3

# Add to PATH
echo 'export PATH=/usr/local/cuda/bin:$PATH' | sudo tee -a /etc/profile.d/cuda.sh
echo 'export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH' | sudo tee -a /etc/profile.d/cuda.sh
source /etc/profile.d/cuda.sh

# Reboot to load driver
sudo reboot

# Verify after reboot
nvidia-smi
```

### AMD ROCm

```bash
# Add ROCm repository
wget https://repo.radeon.com/amdgpu-install/6.0/ubuntu/jammy/amdgpu-install_6.0.60000-1_all.deb
sudo apt install -y ./amdgpu-install_6.0.60000-1_all.deb

# Install ROCm
sudo amdgpu-install -y --usecase=graphics,rocm --no-dkms

# Add user to groups
sudo usermod -aG video,render transcript

# Add to PATH
echo 'export PATH=/opt/rocm/bin:$PATH' | sudo tee -a /etc/profile.d/rocm.sh
echo 'export LD_LIBRARY_PATH=/opt/rocm/lib:$LD_LIBRARY_PATH' | sudo tee -a /etc/profile.d/rocm.sh
source /etc/profile.d/rocm.sh

# Reboot
sudo reboot

# Verify after reboot
rocm-smi
```

## Application Setup

### 1. Clone Repository

```bash
sudo -u transcript bash <<'EOF'
cd /opt/transcript
git clone https://github.com/subculture-collective/transcript-create.git app
cd app
EOF
```

### 2. Create Virtual Environment

```bash
sudo -u transcript bash <<'EOF'
cd /opt/transcript/app
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip wheel
pip install -r requirements.txt

# Install PyTorch with CUDA or ROCm support
# For NVIDIA:
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# For AMD ROCm:
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.0
EOF
```

### 3. Configure Environment

```bash
sudo -u transcript bash <<'EOF'
cd /opt/transcript/app
cp .env.example .env

# Edit .env with production settings
cat > .env <<'ENVEOF'
# Database
DATABASE_URL=postgresql+psycopg://transcript:password@localhost:5432/transcripts

# Redis
REDIS_URL=redis://localhost:6379/0

# Security
SESSION_SECRET=$(openssl rand -hex 32)
ENVIRONMENT=production
LOG_LEVEL=INFO
LOG_FORMAT=json

# Frontend
FRONTEND_ORIGIN=https://app.example.com

# Whisper
WHISPER_MODEL=large-v3
WHISPER_BACKEND=faster-whisper
FORCE_GPU=true
GPU_DEVICE_PREFERENCE=cuda,hip
CHUNK_SECONDS=900

# Paths
DATA_DIR=/opt/transcript/data
BACKUP_DIR=/opt/transcript/backups

# Cleanup
CLEANUP_AFTER_PROCESS=true
CLEANUP_DELETE_RAW=true
CLEANUP_DELETE_CHUNKS=true

# OAuth and Stripe (configure as needed)
OAUTH_GOOGLE_CLIENT_ID=
OAUTH_GOOGLE_CLIENT_SECRET=
STRIPE_API_KEY=
ENVEOF

chmod 600 .env
EOF
```

### 4. Run Database Migrations

```bash
sudo -u transcript bash <<'EOF'
cd /opt/transcript/app
source venv/bin/activate
alembic upgrade head
EOF
```

### 5. Test Application

```bash
sudo -u transcript bash <<'EOF'
cd /opt/transcript/app
source venv/bin/activate

# Test API
uvicorn app.main:app --host 127.0.0.1 --port 8000 &
API_PID=$!
sleep 5
curl http://localhost:8000/health
kill $API_PID

# Test worker with GPU
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
EOF
```

## Systemd Services

### 1. Create API Service

```bash
sudo tee /etc/systemd/system/transcript-api.service > /dev/null <<'EOF'
[Unit]
Description=Transcript Create API
After=network.target postgresql.service redis-server.service
Wants=postgresql.service redis-server.service

[Service]
Type=notify
User=transcript
Group=transcript
WorkingDirectory=/opt/transcript/app
Environment="PATH=/opt/transcript/app/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="PYTHONUNBUFFERED=1"
EnvironmentFile=/opt/transcript/app/.env

ExecStart=/opt/transcript/app/venv/bin/uvicorn app.main:app \
    --host 127.0.0.1 \
    --port 8000 \
    --workers 4 \
    --log-config config/logging.yaml

Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=transcript-api

# Security
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/transcript/data /opt/transcript/logs
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictRealtime=true
LimitNOFILE=65536
LimitNPROC=32768

[Install]
WantedBy=multi-user.target
EOF
```

### 2. Create Worker Service

```bash
sudo tee /etc/systemd/system/transcript-worker.service > /dev/null <<'EOF'
[Unit]
Description=Transcript Create Worker
After=network.target postgresql.service redis-server.service
Wants=postgresql.service redis-server.service

[Service]
Type=simple
User=transcript
Group=transcript
WorkingDirectory=/opt/transcript/app
Environment="PATH=/opt/transcript/app/venv/bin:/usr/local/bin:/usr/bin:/bin:/opt/rocm/bin:/usr/local/cuda/bin"
Environment="LD_LIBRARY_PATH=/opt/rocm/lib:/usr/local/cuda/lib64"
Environment="PYTHONUNBUFFERED=1"
EnvironmentFile=/opt/transcript/app/.env

ExecStart=/opt/transcript/app/venv/bin/python -m worker.loop

Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=transcript-worker

# Security (less restrictive for GPU access)
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/transcript/data /opt/transcript/logs
DeviceAllow=/dev/kfd rw
DeviceAllow=/dev/dri rw
DeviceAllow=/dev/nvidia* rw
LimitNOFILE=65536
LimitNPROC=32768

[Install]
WantedBy=multi-user.target
EOF
```

### 3. Enable and Start Services

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable services
sudo systemctl enable transcript-api
sudo systemctl enable transcript-worker

# Start services
sudo systemctl start transcript-api
sudo systemctl start transcript-worker

# Check status
sudo systemctl status transcript-api
sudo systemctl status transcript-worker

# View logs
sudo journalctl -u transcript-api -f
sudo journalctl -u transcript-worker -f
```

## Nginx Reverse Proxy

### 1. Install Nginx

```bash
sudo apt install -y nginx
```

### 2. Configure Nginx

```bash
sudo tee /etc/nginx/sites-available/transcript > /dev/null <<'EOF'
# Upstream
upstream transcript_api {
    server 127.0.0.1:8000 fail_timeout=0;
}

# Rate limiting
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
limit_conn_zone $binary_remote_addr zone=conn_limit:10m;

# HTTP (redirect to HTTPS)
server {
    listen 80;
    listen [::]:80;
    server_name api.example.com;

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name api.example.com;

    # SSL certificates (configured by certbot)
    ssl_certificate /etc/letsencrypt/live/api.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.example.com/privkey.pem;
    
    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    ssl_stapling on;
    ssl_stapling_verify on;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options DENY always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Logging
    access_log /var/log/nginx/transcript-access.log combined;
    error_log /var/log/nginx/transcript-error.log warn;

    # Client settings
    client_max_body_size 100M;
    client_body_timeout 60s;

    # Proxy settings
    location / {
        limit_req zone=api_limit burst=20 nodelay;
        limit_conn conn_limit 10;

        proxy_pass http://transcript_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 300s;
        
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }

    # Health check endpoint (no rate limiting)
    location /health {
        access_log off;
        proxy_pass http://transcript_api;
    }
}
EOF

# Enable site
sudo ln -sf /etc/nginx/sites-available/transcript /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Test configuration
sudo nginx -t

# Restart Nginx
sudo systemctl restart nginx
sudo systemctl enable nginx
```

## SSL with Certbot

### 1. Install Certbot

```bash
sudo apt install -y certbot python3-certbot-nginx
```

### 2. Obtain Certificate

```bash
# Obtain and install certificate
sudo certbot --nginx -d api.example.com --non-interactive --agree-tos --email admin@example.com

# Test auto-renewal
sudo certbot renew --dry-run
```

### 3. Configure Auto-Renewal

```bash
# Certbot should have created a systemd timer
sudo systemctl list-timers | grep certbot

# Or create cron job
echo "0 3 * * * root certbot renew --quiet --post-hook 'systemctl reload nginx'" | sudo tee -a /etc/crontab
```

## Monitoring and Logging

### 1. Configure Log Rotation

```bash
sudo tee /etc/logrotate.d/transcript > /dev/null <<'EOF'
/opt/transcript/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 transcript transcript
    sharedscripts
    postrotate
        systemctl reload transcript-api transcript-worker > /dev/null 2>&1 || true
    endscript
}

/var/log/nginx/transcript-*.log {
    daily
    rotate 30
    compress
    delaycompress
    notifempty
    create 0640 www-data adm
    sharedscripts
    postrotate
        systemctl reload nginx > /dev/null 2>&1 || true
    endscript
}
EOF
```

### 2. Set Up Monitoring

```bash
# Install node_exporter for Prometheus metrics
cd /tmp
wget https://github.com/prometheus/node_exporter/releases/download/v1.7.0/node_exporter-1.7.0.linux-amd64.tar.gz
tar xzf node_exporter-1.7.0.linux-amd64.tar.gz
sudo mv node_exporter-1.7.0.linux-amd64/node_exporter /usr/local/bin/
sudo useradd -rs /bin/false node_exporter

# Create systemd service
sudo tee /etc/systemd/system/node_exporter.service > /dev/null <<'EOF'
[Unit]
Description=Node Exporter
After=network.target

[Service]
User=node_exporter
Group=node_exporter
Type=simple
ExecStart=/usr/local/bin/node_exporter

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable node_exporter
sudo systemctl start node_exporter
```

### 3. Database Backup Script

```bash
sudo -u transcript tee /opt/transcript/backups/backup.sh > /dev/null <<'EOF'
#!/bin/bash
BACKUP_DIR="/opt/transcript/backups"
DATE=$(date +%Y%m%d_%H%M%S)
DB_FILE="$BACKUP_DIR/db/transcript_$DATE.sql.gz"

mkdir -p "$BACKUP_DIR/db"

# Backup database
PGPASSWORD="password" pg_dump -h localhost -U transcript transcripts | gzip > "$DB_FILE"

# Keep only last 30 days
find "$BACKUP_DIR/db" -name "transcript_*.sql.gz" -mtime +30 -delete

echo "Backup completed: $DB_FILE"
EOF

sudo chmod +x /opt/transcript/backups/backup.sh

# Add to crontab
(sudo -u transcript crontab -l 2>/dev/null; echo "0 2 * * * /opt/transcript/backups/backup.sh >> /opt/transcript/logs/backup.log 2>&1") | sudo -u transcript crontab -
```

## Maintenance

### Service Management

```bash
# Restart services
sudo systemctl restart transcript-api transcript-worker

# View logs
sudo journalctl -u transcript-api -f
sudo journalctl -u transcript-worker -f
sudo tail -f /var/log/nginx/transcript-access.log

# Check status
sudo systemctl status transcript-api transcript-worker nginx postgresql redis-server
```

### Updates

```bash
# Stop services
sudo systemctl stop transcript-api transcript-worker

# Backup database
sudo -u transcript /opt/transcript/backups/backup.sh

# Update code
sudo -u transcript bash <<'EOF'
cd /opt/transcript/app
git fetch origin
git checkout v1.2.0
source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
EOF

# Start services
sudo systemctl start transcript-api transcript-worker

# Verify
curl https://api.example.com/health
```

### Performance Tuning

```bash
# PostgreSQL tuning
sudo -u postgres psql <<EOF
ALTER SYSTEM SET shared_buffers = '8GB';
ALTER SYSTEM SET effective_cache_size = '24GB';
ALTER SYSTEM SET maintenance_work_mem = '2GB';
ALTER SYSTEM SET checkpoint_completion_target = 0.9;
ALTER SYSTEM SET wal_buffers = '16MB';
ALTER SYSTEM SET default_statistics_target = 100;
ALTER SYSTEM SET random_page_cost = 1.1;
ALTER SYSTEM SET effective_io_concurrency = 200;
ALTER SYSTEM SET work_mem = '20MB';
ALTER SYSTEM SET min_wal_size = '2GB';
ALTER SYSTEM SET max_wal_size = '8GB';
ALTER SYSTEM SET max_worker_processes = 8;
ALTER SYSTEM SET max_parallel_workers_per_gather = 4;
ALTER SYSTEM SET max_parallel_workers = 8;
EOF

sudo systemctl restart postgresql
```

## Troubleshooting

See [Troubleshooting Guide](./troubleshooting.md) for common issues.

### Quick Checks

```bash
# Check services
sudo systemctl status transcript-api transcript-worker nginx postgresql redis-server

# Check GPU
nvidia-smi  # or rocm-smi

# Test database
psql -h localhost -U transcript -d transcripts -c "SELECT version();"

# Test API
curl http://localhost:8000/health
curl https://api.example.com/health

# Check logs
sudo journalctl -xe
tail -f /opt/transcript/logs/*.log
```

## Security Hardening

```bash
# Install fail2ban
sudo apt install -y fail2ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban

# Configure SSH (disable password auth)
sudo sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo systemctl restart sshd

# Enable automatic security updates
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

## Next Steps

- [ ] Set up monitoring dashboards (Grafana + Prometheus)
- [ ] Configure backup to remote storage (S3, rsync)
- [ ] Set up alerts (email, Slack)
- [ ] Configure CDN for static assets
- [ ] Implement backup verification
- [ ] Document runbooks for common operations

## Additional Resources

- [Production Checklist](./production-checklist.md)
- [Troubleshooting Guide](./troubleshooting.md)
- [Upgrade Guide](./upgrade-guide.md)
