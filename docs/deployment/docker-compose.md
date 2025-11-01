# Docker Compose Production Deployment

This guide covers deploying transcript-create on a single server using Docker Compose with production-grade configurations including SSL/TLS, monitoring, and automated backups.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Server Setup](#server-setup)
3. [Installation](#installation)
4. [SSL/TLS Configuration](#ssltls-configuration)
5. [Environment Configuration](#environment-configuration)
6. [Deployment](#deployment)
7. [Monitoring](#monitoring)
8. [Backup and Restore](#backup-and-restore)
9. [Upgrades](#upgrades)
10. [Troubleshooting](#troubleshooting)

## Prerequisites

### Hardware Requirements

**Minimum:**
- CPU: 4 cores
- RAM: 16 GB
- Storage: 100 GB SSD
- GPU: AMD ROCm-compatible or NVIDIA GPU with 8GB+ VRAM

**Recommended:**
- CPU: 8+ cores
- RAM: 32 GB
- Storage: 500 GB NVMe SSD
- GPU: AMD Radeon RX 6800/6900 or NVIDIA RTX 3090/4090

### Software Requirements

- Ubuntu 22.04 LTS or Debian 12 (recommended)
- Docker 24.0+
- Docker Compose V2
- GPU drivers:
  - AMD: ROCm 5.7+ or 6.0+
  - NVIDIA: CUDA 11.8+ or 12.x
- Domain name with DNS configured
- SSL certificate (Let's Encrypt recommended)

### Network Requirements

- Public IP address
- Ports open:
  - 80 (HTTP - for SSL certificate challenge and redirect)
  - 443 (HTTPS)
  - 22 (SSH - for management)
- Optional: 
  - 5434 (PostgreSQL - if remote access needed)
  - 9090 (Prometheus - monitoring)
  - 3000 (Grafana - dashboards)

## Server Setup

### 1. Initial Server Configuration

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install essential packages
sudo apt install -y curl git vim ufw fail2ban

# Configure firewall
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable

# Configure fail2ban for SSH protection
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

### 2. Install Docker

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
rm get-docker.sh

# Install Docker Compose
sudo apt install -y docker-compose-plugin

# Verify installation
docker --version
docker compose version
```

### 3. Install GPU Drivers

#### AMD ROCm

```bash
# Add ROCm repository
wget https://repo.radeon.com/amdgpu-install/6.0/ubuntu/jammy/amdgpu-install_6.0.60000-1_all.deb
sudo apt install -y ./amdgpu-install_6.0.60000-1_all.deb
rm amdgpu-install_6.0.60000-1_all.deb

# Install ROCm
sudo amdgpu-install -y --usecase=graphics,rocm

# Add user to video and render groups
sudo usermod -aG video,render $USER

# Verify installation
rocm-smi
```

#### NVIDIA CUDA

```bash
# Install NVIDIA drivers
sudo apt install -y nvidia-driver-535

# Install NVIDIA Container Toolkit
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt update
sudo apt install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# Verify installation
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.0-base-ubuntu22.04 nvidia-smi
```

## Installation

### 1. Clone Repository

```bash
# Create application directory
sudo mkdir -p /opt/transcript-create
sudo chown $USER:$USER /opt/transcript-create
cd /opt/transcript-create

# Clone repository
git clone https://github.com/subculture-collective/transcript-create.git .
```

### 2. Create Production Docker Compose File

The production compose file extends the development configuration with additional services and security:

```bash
# Create production compose file
cat > docker-compose.prod.yml << 'EOF'
services:
  # Extend base services from docker-compose.yml
  db:
    environment:
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - dbdata:/var/lib/postgresql/data
      - /opt/transcript-create/backups/db:/backups
    restart: unless-stopped

  redis:
    restart: unless-stopped

  api:
    env_file: .env.prod
    environment:
      DATABASE_URL: postgresql+psycopg://postgres:${DB_PASSWORD}@db:5432/transcripts
      REDIS_URL: redis://redis:6379/0
      OPENSEARCH_URL: http://opensearch:9200
      ENVIRONMENT: production
      LOG_LEVEL: INFO
      LOG_FORMAT: json
    restart: unless-stopped
    labels:
      - "com.centurylinklabs.watchtower.enable=true"

  worker:
    env_file: .env.prod
    environment:
      DATABASE_URL: postgresql+psycopg://postgres:${DB_PASSWORD}@db:5432/transcripts
      OPENSEARCH_URL: http://opensearch:9200
      ENVIRONMENT: production
      LOG_LEVEL: INFO
      LOG_FORMAT: json
    restart: unless-stopped
    labels:
      - "com.centurylinklabs.watchtower.enable=true"

  # Reverse proxy with automatic SSL
  caddy:
    image: caddy:2-alpine
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp"  # HTTP/3
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy-data:/data
      - caddy-config:/config
    depends_on:
      - api
    restart: unless-stopped

  # Automated backups
  backup:
    image: transcript-create:latest
    env_file: .env.prod
    environment:
      DATABASE_URL: postgresql+psycopg://postgres:${DB_PASSWORD}@db:5432/transcripts
    volumes:
      - ./data:/data:ro
      - /opt/transcript-create/backups:/backups
      - ./scripts:/scripts:ro
    entrypoint: ["/bin/bash", "-c"]
    command:
      - |
        echo "0 2 * * * /scripts/backup_db.sh" > /etc/crontabs/root
        echo "0 3 * * * /scripts/backup_media.sh" > /etc/crontabs/root
        echo "0 4 * * 0 /scripts/verify_backup.sh" > /etc/crontabs/root
        crond -f -l 2
    depends_on:
      - db
    restart: unless-stopped

  # Automatic container updates (optional)
  watchtower:
    image: containrrr/watchtower:latest
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      WATCHTOWER_CLEANUP: "true"
      WATCHTOWER_POLL_INTERVAL: 86400  # Check daily
      WATCHTOWER_LABEL_ENABLE: "true"
    restart: unless-stopped

volumes:
  dbdata:
  caddy-data:
  caddy-config:

EOF
```

### 3. Create Caddyfile for SSL

```bash
# Create Caddyfile
cat > Caddyfile << 'EOF'
{
    # Global options
    email admin@example.com  # Replace with your email
}

api.example.com {  # Replace with your domain
    # Automatic HTTPS with Let's Encrypt
    
    # Rate limiting
    rate_limit {
        zone general {
            key {remote_host}
            events 100
            window 1m
        }
    }

    # Security headers
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        X-XSS-Protection "1; mode=block"
        Referrer-Policy "strict-origin-when-cross-origin"
        -Server  # Remove server header
    }

    # Proxy to API
    reverse_proxy api:8000 {
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
        header_up X-Forwarded-Proto {scheme}
        
        # Health check
        health_uri /health
        health_interval 30s
        health_timeout 5s
    }

    # Logging
    log {
        output file /data/access.log {
            roll_size 100mb
            roll_keep 10
        }
        format json
    }

    # Error handling
    handle_errors {
        respond "{err.status_code} {err.status_text}"
    }
}
EOF
```

## Environment Configuration

### 1. Create Production Environment File

```bash
# Copy example and create production env
cp .env.example .env.prod

# Generate secure secrets
openssl rand -hex 32  # For SESSION_SECRET
```

### 2. Configure Production Variables

Edit `.env.prod` with production values:

```bash
# Core Configuration
DATABASE_URL=postgresql+psycopg://postgres:${DB_PASSWORD}@db:5432/transcripts
REDIS_URL=redis://redis:6379/0
ENVIRONMENT=production

# Security
SESSION_SECRET=<generated-secret-from-openssl>
ADMIN_EMAILS=admin@example.com

# Frontend
FRONTEND_ORIGIN=https://app.example.com

# OAuth (configure based on your providers)
OAUTH_GOOGLE_CLIENT_ID=your-client-id
OAUTH_GOOGLE_CLIENT_SECRET=your-client-secret
OAUTH_GOOGLE_REDIRECT_URI=https://api.example.com/auth/callback/google

# Stripe (use live keys for production)
STRIPE_API_KEY=sk_live_...
STRIPE_PRICE_PRO_MONTHLY=price_...
STRIPE_PRICE_PRO_YEARLY=price_...
STRIPE_WEBHOOK_SECRET=whsec_...

# HuggingFace (for speaker diarization)
HF_TOKEN=hf_...

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json

# Monitoring
ENABLE_METRICS=true

# Sentry (optional error tracking)
SENTRY_DSN=https://...
SENTRY_ENVIRONMENT=production

# Backup
BACKUP_ENCRYPT=true
BACKUP_GPG_RECIPIENT=admin@example.com
BACKUP_S3_BUCKET=transcript-backups  # Optional cloud backup
```

### 3. Secure Environment Files

```bash
# Restrict access to environment files
chmod 600 .env.prod

# Create separate file for sensitive DB password
echo "DB_PASSWORD=$(openssl rand -base64 32)" > .env.db
chmod 600 .env.db
```

## Deployment

### 1. Build Images

```bash
# Build production image
docker compose -f docker-compose.yml build \
  --build-arg ROCM_WHEEL_INDEX=https://download.pytorch.org/whl/rocm6.0

# Tag as latest
docker tag transcript-create:latest transcript-create:prod
```

### 2. Initialize Database

```bash
# Start database first
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d db

# Wait for database to be ready
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec db \
  pg_isready -U postgres

# Run migrations
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm migrations
```

### 3. Start Services

```bash
# Start all services
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Verify services are running
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps

# Check logs
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f
```

### 4. Verify Deployment

```bash
# Check API health
curl https://api.example.com/health

# Check SSL certificate
curl -vI https://api.example.com 2>&1 | grep -A 5 "SSL certificate"

# Test GPU in worker
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec worker rocm-smi
# or for NVIDIA
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec worker nvidia-smi

# Submit a test job
curl -X POST https://api.example.com/api/jobs \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'
```

## Monitoring

### 1. Access Monitoring Dashboards

```bash
# Prometheus: http://your-server-ip:9090
# Grafana: http://your-server-ip:3000 (default: admin/admin)
```

### 2. Configure Grafana

1. Log in to Grafana
2. Add Prometheus data source (http://prometheus:9090)
3. Import dashboards from `config/grafana/dashboards/`
4. Configure alerting (email, Slack, etc.)

### 3. Set Up External Monitoring

```bash
# Install monitoring agent (example: Prometheus node_exporter)
docker run -d \
  --name node_exporter \
  --network transcript-create_default \
  --pid host \
  -v /proc:/host/proc:ro \
  -v /sys:/host/sys:ro \
  -v /:/rootfs:ro \
  prom/node-exporter:latest \
  --path.procfs=/host/proc \
  --path.sysfs=/host/sys \
  --collector.filesystem.mount-points-exclude="^/(sys|proc|dev|host|etc)($$|/)"
```

## Backup and Restore

### Manual Backup

```bash
# Database backup
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backup \
  /scripts/backup_db.sh

# Media backup
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backup \
  /scripts/backup_media.sh

# Verify backup
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backup \
  /scripts/verify_backup.sh /backups/db/latest.sql.gz
```

### Automated Backups

Backups run automatically via the `backup` service:
- Database: Daily at 2:00 AM UTC
- Media: Daily at 3:00 AM UTC
- Verification: Weekly on Sunday at 4:00 AM UTC

### Restore from Backup

```bash
# Stop services
docker compose -f docker-compose.yml -f docker-compose.prod.yml stop api worker

# Restore database
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backup \
  /scripts/restore_db.sh /backups/db/backup-2025-01-15.sql.gz

# Restart services
docker compose -f docker-compose.yml -f docker-compose.prod.yml start api worker
```

### Cloud Backup Configuration

```bash
# Add to .env.prod for AWS S3
BACKUP_S3_BUCKET=transcript-backups-prod

# Configure AWS credentials
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backup \
  aws configure
```

## Upgrades

### Zero-Downtime Upgrade Process

```bash
# 1. Backup current state
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backup \
  /scripts/backup_db.sh

# 2. Pull latest code
git fetch origin
git checkout v1.2.0  # Replace with target version

# 3. Build new image
docker compose -f docker-compose.yml -f docker-compose.prod.yml build

# 4. Run migrations (if any)
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm migrations

# 5. Rolling update API (one container at a time)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps --scale api=6 api
sleep 30
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps --scale api=3 api

# 6. Update worker
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps worker

# 7. Verify
curl https://api.example.com/health

# 8. Check logs for errors
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail=100 api worker
```

### Rollback Procedure

```bash
# 1. Stop services
docker compose -f docker-compose.yml -f docker-compose.prod.yml down

# 2. Revert code
git checkout v1.1.0  # Previous working version

# 3. Restore database if needed
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backup \
  /scripts/restore_db.sh /backups/db/pre-upgrade-backup.sql.gz

# 4. Rebuild and restart
docker compose -f docker-compose.yml -f docker-compose.prod.yml build
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# 5. Verify rollback
curl https://api.example.com/health
```

## Troubleshooting

### Service Won't Start

```bash
# Check service status
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps

# View logs
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs <service>

# Inspect container
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec <service> bash
```

### SSL Certificate Issues

```bash
# Check Caddy logs
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs caddy

# Manually trigger certificate renewal
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec caddy \
  caddy reload --config /etc/caddy/Caddyfile

# Verify certificate
echo | openssl s_client -servername api.example.com -connect api.example.com:443 2>/dev/null | openssl x509 -noout -dates
```

### GPU Not Detected

```bash
# Check GPU visibility
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec worker rocm-smi
# or
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec worker nvidia-smi

# Verify container has GPU access
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec worker \
  python -c "import torch; print(torch.cuda.is_available())"

# Check device permissions
ls -l /dev/kfd /dev/dri  # ROCm
ls -l /dev/nvidia*  # NVIDIA
```

### Database Connection Errors

```bash
# Test database connectivity
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api \
  python -c "from app.db import engine; engine.connect(); print('Connected')"

# Check PostgreSQL status
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec db \
  pg_isready -U postgres

# View database logs
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs db
```

### High Memory Usage

```bash
# Check container resource usage
docker stats

# Adjust worker memory limits in compose file
# worker:
#   deploy:
#     resources:
#       limits:
#         memory: 16G

# Reduce concurrent jobs
# In .env.prod: MAX_PARALLEL_JOBS=1
```

## Maintenance

### Log Rotation

```bash
# Configure Docker log rotation
cat > /etc/docker/daemon.json << EOF
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "100m",
    "max-file": "10"
  }
}
EOF

sudo systemctl restart docker
```

### Cleanup Old Data

```bash
# Prune Docker system
docker system prune -a --volumes --filter "until=720h"

# Clean old backups (keep last 30 days)
find /opt/transcript-create/backups -type f -mtime +30 -delete
```

### Security Updates

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Update Docker images
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Restart with watchtower for automatic updates (already configured)
```

## Performance Tuning

### Database Optimization

```bash
# Add to db service in docker-compose.prod.yml
db:
  command:
    - "postgres"
    - "-c"
    - "max_connections=200"
    - "-c"
    - "shared_buffers=2GB"
    - "-c"
    - "effective_cache_size=6GB"
    - "-c"
    - "maintenance_work_mem=512MB"
    - "-c"
    - "checkpoint_completion_target=0.9"
    - "-c"
    - "wal_buffers=16MB"
    - "-c"
    - "default_statistics_target=100"
```

### Worker Scaling

```bash
# Scale workers based on available GPUs
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --scale worker=3
```

## Cost Estimation

### Monthly Costs (Single Server)

**Basic Setup:**
- Server: $100-200/month (dedicated server with GPU)
- Domain: $10-15/year
- SSL: Free (Let's Encrypt)
- **Total: ~$100-200/month**

**Production Setup:**
- Server: $300-500/month (high-performance with enterprise GPU)
- Backup storage: $10-50/month (S3/GCS)
- Monitoring service: $20-50/month (optional)
- **Total: ~$330-600/month**

## Next Steps

- [ ] Configure monitoring alerts
- [ ] Set up automated backups to cloud storage
- [ ] Configure user management and OAuth providers
- [ ] Enable billing integration (Stripe)
- [ ] Set up staging environment
- [ ] Document runbooks for common operations
- [ ] Configure multi-region setup (for global deployments)

## Support Resources

- Full documentation: [docs/](../)
- Kubernetes guide: [kubernetes.md](./kubernetes.md)
- Troubleshooting: [troubleshooting.md](./troubleshooting.md)
- GitHub Issues: https://github.com/subculture-collective/transcript-create/issues
