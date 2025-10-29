# Ansible Automation for Transcript Create

This directory contains Ansible playbooks and roles for deploying and managing transcript-create servers.

## Overview

Ansible automates the deployment of transcript-create on Ubuntu/Debian servers, including:

- Base system configuration
- Docker installation
- GPU driver installation (NVIDIA CUDA or AMD ROCm)
- Application deployment
- Monitoring setup

## Prerequisites

### Control Machine

```bash
# Install Ansible
pip install ansible

# Or on Ubuntu/Debian
sudo apt update
sudo apt install ansible

# Verify
ansible --version  # Should be 2.14+
```

### Target Servers

- Ubuntu 22.04 LTS or Debian 12
- SSH access with sudo privileges
- Python 3 installed

## Quick Start

### 1. Configure Inventory

Edit `inventory.yml`:

```yaml
all:
  children:
    production:
      hosts:
        api-01:
          ansible_host: 10.0.1.10
          ansible_user: ubuntu
        api-02:
          ansible_host: 10.0.1.11
          ansible_user: ubuntu
        worker-01:
          ansible_host: 10.0.2.10
          ansible_user: ubuntu
          gpu_type: nvidia
    staging:
      hosts:
        staging-01:
          ansible_host: 10.0.3.10
          ansible_user: ubuntu
```

### 2. Configure Variables

Edit `group_vars/all.yml`:

```yaml
# Project settings
project_name: transcript-create
environment: production

# Database
database_host: db.example.com
database_name: transcripts
database_user: transcript

# Application
app_version: v1.0.0
app_port: 8000

# GPU settings
gpu_type: nvidia  # or amd
install_gpu_drivers: true
```

### 3. Run Playbook

```bash
# Full deployment
ansible-playbook -i inventory.yml site.yml

# Specific role
ansible-playbook -i inventory.yml site.yml --tags docker

# Specific hosts
ansible-playbook -i inventory.yml site.yml --limit worker-01

# Check mode (dry run)
ansible-playbook -i inventory.yml site.yml --check
```

## Playbooks

### site.yml
Main playbook that orchestrates all roles.

```bash
ansible-playbook -i inventory.yml site.yml
```

### deploy.yml
Application deployment only.

```bash
ansible-playbook -i inventory.yml deploy.yml
```

### update.yml
Update application to new version.

```bash
ansible-playbook -i inventory.yml update.yml -e "app_version=v1.1.0"
```

## Roles

### base
System configuration, users, packages, firewall.

**Tasks:**
- Update system packages
- Install common utilities
- Configure firewall (ufw)
- Set up log rotation
- Configure system limits

**Variables:**
```yaml
base_packages:
  - curl
  - git
  - vim
  - htop
```

### docker
Docker and Docker Compose installation.

**Tasks:**
- Install Docker engine
- Install Docker Compose
- Configure Docker daemon
- Add users to docker group

**Variables:**
```yaml
docker_version: "24.0"
docker_compose_version: "2.23.0"
```

### gpu-drivers
GPU driver installation (NVIDIA CUDA or AMD ROCm).

**Tasks:**
- Detect GPU type
- Install NVIDIA drivers and CUDA toolkit
- Install AMD ROCm drivers
- Verify GPU detection

**Variables:**
```yaml
gpu_type: nvidia  # or amd
cuda_version: "12.3"
rocm_version: "6.0"
```

### app
Application deployment and configuration.

**Tasks:**
- Clone/pull repository
- Create systemd services
- Configure environment variables
- Run database migrations
- Start services

**Variables:**
```yaml
app_repo_url: "https://github.com/subculture-collective/transcript-create.git"
app_version: "main"
app_install_dir: "/opt/transcript-create"
```

### monitoring
Monitoring setup (Prometheus, Node Exporter, Grafana).

**Tasks:**
- Install Node Exporter
- Install Prometheus
- Install Grafana
- Configure dashboards

**Variables:**
```yaml
install_prometheus: true
install_grafana: true
grafana_admin_password: "changeme"
```

## Usage Examples

### Initial Server Setup

```bash
# Set up new servers
ansible-playbook -i inventory.yml site.yml --tags base,docker,gpu-drivers
```

### Deploy Application

```bash
# Deploy app to all production servers
ansible-playbook -i inventory.yml deploy.yml --limit production

# Deploy specific version
ansible-playbook -i inventory.yml deploy.yml -e "app_version=v1.0.5"
```

### Update GPU Drivers

```bash
# Update NVIDIA drivers on workers
ansible-playbook -i inventory.yml site.yml --tags gpu-drivers --limit worker-*
```

### Install Monitoring

```bash
# Set up monitoring stack
ansible-playbook -i inventory.yml site.yml --tags monitoring
```

### Ad-Hoc Commands

```bash
# Check disk space
ansible all -i inventory.yml -m shell -a "df -h"

# Restart services
ansible production -i inventory.yml -m systemd -a "name=transcript-api state=restarted" --become

# Check GPU status
ansible worker-* -i inventory.yml -m shell -a "nvidia-smi"

# Update system packages
ansible all -i inventory.yml -m apt -a "upgrade=dist" --become
```

## Directory Structure

```
ansible/
├── inventory.yml              # Inventory file
├── ansible.cfg                # Ansible configuration
├── site.yml                   # Main playbook
├── deploy.yml                 # Deployment playbook
├── update.yml                 # Update playbook
├── group_vars/
│   ├── all.yml               # Variables for all hosts
│   ├── production.yml        # Production-specific vars
│   └── staging.yml           # Staging-specific vars
├── host_vars/
│   ├── worker-01.yml         # Host-specific vars
│   └── api-01.yml
└── roles/
    ├── base/                  # Base system setup
    ├── docker/                # Docker installation
    ├── gpu-drivers/           # GPU drivers
    ├── app/                   # Application deployment
    └── monitoring/            # Monitoring setup
```

## Best Practices

### Security

1. **Use Ansible Vault** for sensitive data:
   ```bash
   # Encrypt file
   ansible-vault encrypt group_vars/production.yml
   
   # Run playbook with vault
   ansible-playbook -i inventory.yml site.yml --ask-vault-pass
   ```

2. **Use SSH keys** instead of passwords
3. **Limit privilege escalation** - only use `become: yes` when needed
4. **Keep secrets in vault** - never commit unencrypted secrets

### Testing

```bash
# Syntax check
ansible-playbook -i inventory.yml site.yml --syntax-check

# Dry run
ansible-playbook -i inventory.yml site.yml --check

# Step through
ansible-playbook -i inventory.yml site.yml --step

# Verbose output
ansible-playbook -i inventory.yml site.yml -vvv
```

### Performance

```bash
# Parallel execution
ansible-playbook -i inventory.yml site.yml --forks=10

# Use connection pipelining (in ansible.cfg)
[ssh_connection]
pipelining = True
```

## Variables Reference

### Global Variables (group_vars/all.yml)

```yaml
# Project
project_name: transcript-create
environment: production
app_version: main

# Paths
app_install_dir: /opt/transcript-create
app_data_dir: /opt/transcript-create/data
app_backup_dir: /opt/transcript-create/backups

# Database
database_url: postgresql+psycopg://user:pass@host:5432/transcripts
redis_url: redis://localhost:6379/0

# Application
app_port: 8000
app_workers: 4
worker_max_parallel_jobs: 1

# GPU
gpu_type: nvidia
install_gpu_drivers: true

# Monitoring
install_prometheus: true
install_grafana: true
prometheus_port: 9090
grafana_port: 3000
```

### Host-Specific Variables (host_vars/)

```yaml
# worker-01.yml
ansible_host: 10.0.2.10
ansible_user: ubuntu
gpu_type: nvidia
gpu_count: 1
```

## Troubleshooting

### Connection Issues

```bash
# Test connectivity
ansible all -i inventory.yml -m ping

# Test sudo access
ansible all -i inventory.yml -m shell -a "whoami" --become
```

### Failed Tasks

```bash
# Re-run from failed task
ansible-playbook -i inventory.yml site.yml --start-at-task="Install Docker"

# Debug specific task
ansible-playbook -i inventory.yml site.yml --tags docker -vvv
```

### Gathering Facts

```bash
# Gather system information
ansible all -i inventory.yml -m setup
```

## CI/CD Integration

### GitHub Actions

```yaml
name: Ansible Deploy
on:
  workflow_dispatch:
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Install Ansible
        run: pip install ansible
      
      - name: Deploy
        env:
          ANSIBLE_VAULT_PASSWORD: ${{ secrets.VAULT_PASSWORD }}
        run: |
          echo "$ANSIBLE_VAULT_PASSWORD" > .vault_pass
          ansible-playbook -i inventory.yml deploy.yml --vault-password-file .vault_pass
```

## Support

- Documentation: [docs/deployment/](../../docs/deployment/)
- GitHub Issues: https://github.com/subculture-collective/transcript-create/issues
- Ansible Documentation: https://docs.ansible.com/
