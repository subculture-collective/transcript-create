# Development Setup Guide

This guide walks you through setting up Transcript Create for local development.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Getting the Code](#getting-the-code)
- [Environment Configuration](#environment-configuration)
- [Installation Methods](#installation-methods)
  - [Docker Compose (Recommended)](#docker-compose-recommended)
  - [Local Development](#local-development)
- [Database Setup](#database-setup)
- [Verification](#verification)
- [Common Issues](#common-issues)

## Prerequisites

### Required

- **Git**: Version control system
  - Install: [https://git-scm.com/downloads](https://git-scm.com/downloads)

- **Docker & Docker Compose**: For containerized development
  - Install Docker: [https://docs.docker.com/get-docker/](https://docs.docker.com/get-docker/)
  - Docker Compose is included with Docker Desktop
  - Minimum version: Docker 24.0+, Compose V2

### For Local Development (without Docker)

- **Python 3.11+**: Backend and worker runtime
  - Install: [https://www.python.org/downloads/](https://www.python.org/downloads/)
  - Verify: `python --version` or `python3 --version`

- **Node.js 20+**: Frontend development
  - Install: [https://nodejs.org/](https://nodejs.org/)
  - We recommend using [nvm](https://github.com/nvm-sh/nvm) or [fnm](https://github.com/Schniz/fnm)
  - Verify: `node --version` and `npm --version`

- **PostgreSQL 15+**: Database
  - Install: [https://www.postgresql.org/download/](https://www.postgresql.org/download/)
  - Or use Docker: `docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:15`

### Optional

- **AMD GPU with ROCm**: For GPU-accelerated transcription
  - ROCm installation: [https://rocm.docs.amd.com/](https://rocm.docs.amd.com/)
  - Supported GPUs: AMD Radeon RX 6000/7000 series, MI series

- **NVIDIA GPU with CUDA**: Alternative GPU support
  - CUDA installation: [https://developer.nvidia.com/cuda-downloads](https://developer.nvidia.com/cuda-downloads)

## Getting the Code

### 1. Fork the Repository (for contributors)

Visit [https://github.com/subculture-collective/transcript-create](https://github.com/subculture-collective/transcript-create) and click "Fork" to create your own copy.

### 2. Clone Your Fork

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/transcript-create.git
cd transcript-create

# Add upstream remote (to sync with main repo)
git remote add upstream https://github.com/subculture-collective/transcript-create.git

# Verify remotes
git remote -v
```

### 3. Create a Branch

```bash
# Create and switch to a new branch
git checkout -b feature/my-awesome-feature

# Or for bug fixes
git checkout -b fix/bug-description
```

## Environment Configuration

### 1. Copy Example Environment File

```bash
cp .env.example .env
```

### 2. Configure Required Variables

Edit `.env` and set these **required** values:

```bash
# Generate a secure session secret
# Run this command and copy the output:
openssl rand -hex 32

# Paste the generated value here:
SESSION_SECRET=your_generated_secret_here

# Database (automatically configured by Docker Compose)
# For local dev without Docker:
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/postgres

# Frontend origin (default is fine for local dev)
FRONTEND_ORIGIN=http://localhost:5173
```

### 3. Optional Configuration

```bash
# Hugging Face token for speaker diarization
HF_TOKEN=hf_your_token_here

# OpenSearch for advanced search (optional)
SEARCH_BACKEND=postgres  # or 'opensearch'

# OAuth providers (for authentication features)
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret

TWITCH_CLIENT_ID=your_twitch_client_id
TWITCH_CLIENT_SECRET=your_twitch_client_secret

# Stripe (for billing features)
STRIPE_API_KEY=sk_test_your_key
STRIPE_WEBHOOK_SECRET=whsec_your_secret
```

## Installation Methods

### Docker Compose (Recommended)

Docker Compose provides a complete development environment with all services pre-configured.

#### 1. Build Images

```bash
# Build all services
docker compose build

# Or build with specific ROCm version
docker compose build --build-arg ROCM_WHEEL_INDEX=https://download.pytorch.org/whl/rocm6.1
```

#### 2. Start Services

```bash
# Start all services (database, API, worker)
docker compose up -d

# View logs
docker compose logs -f

# View logs for specific service
docker compose logs -f api
```

#### 3. Start Frontend

The frontend runs outside Docker for faster development:

```bash
cd frontend
npm install
npm run dev
```

Frontend will be available at [http://localhost:5173](http://localhost:5173)

#### 4. Verify Services

```bash
# Check service status
docker compose ps

# Test API
curl http://localhost:8000/health

# Test database connection
docker compose exec db psql -U postgres -c "SELECT 1;"
```

### Local Development

For development without Docker (faster iteration, easier debugging).

#### 1. Install Backend Dependencies

```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On macOS/Linux:
source .venv/bin/activate
# On Windows:
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install development dependencies
pip install -r requirements-dev.txt
```

#### 2. Install Frontend Dependencies

```bash
cd frontend
npm install
cd ..
```

#### 3. Install Pre-commit Hooks

```bash
# Quick setup script (recommended)
./scripts/setup_precommit.sh

# Or manual installation
pip install pre-commit
pre-commit install
```

#### 4. Start Services

You'll need **three terminal windows**:

**Terminal 1 - API:**
```bash
source .venv/bin/activate  # If not already activated
uvicorn app.main:app --reload --port 8000
```

**Terminal 2 - Worker:**
```bash
source .venv/bin/activate  # If not already activated
python -m worker.loop
```

**Terminal 3 - Frontend:**
```bash
cd frontend
npm run dev
```

## Database Setup

### With Docker Compose

Database is automatically initialized with the schema when you run `docker compose up`.

### Without Docker (Local PostgreSQL)

#### 1. Create Database

```bash
# Connect to PostgreSQL
psql -U postgres

# Create database (if needed)
CREATE DATABASE transcripts;

# Exit psql
\q
```

#### 2. Apply Schema

```bash
# Using Alembic migrations (recommended)
python scripts/run_migrations.py upgrade

# Or apply schema directly (for fresh database)
psql $DATABASE_URL -f sql/schema.sql
```

#### 3. Verify

```bash
# Check migrations
python scripts/run_migrations.py current

# List tables
psql $DATABASE_URL -c "\dt"
```

## Verification

### 1. Access Services

- **Frontend**: [http://localhost:5173](http://localhost:5173)
- **API**: [http://localhost:8000](http://localhost:8000)
- **API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **API Health**: [http://localhost:8000/health](http://localhost:8000/health)

### 2. Test API

```bash
# Create a test job
curl -X POST http://localhost:8000/jobs \
  -H 'Content-Type: application/json' \
  -d '{
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "kind": "single"
  }'

# Check job status (replace {job_id} with the ID from above)
curl http://localhost:8000/jobs/{job_id}
```

### 3. Run Tests

```bash
# Backend tests
pytest tests/ -v

# Frontend tests
cd frontend
npm test

# E2E tests (requires services running)
cd e2e
npm test
```

### 4. Run Linters

```bash
# Backend
ruff check app/ worker/
black --check app/ worker/
isort --check-only app/ worker/

# Frontend
cd frontend
npm run lint
npm run format:check
```

## Common Issues

### Port Already in Use

If you get "port already in use" errors:

```bash
# Check what's using the port
lsof -i :8000  # or :5173, :5432

# Kill the process (on Unix)
kill -9 <PID>

# Or use different ports
DB_HOST_PORT=5435 API_HOST_PORT=8001 docker compose up -d
```

### Python Version Issues

```bash
# Check Python version
python --version

# Use pyenv to install specific version
pyenv install 3.11.7
pyenv local 3.11.7
```

### Node Version Issues

```bash
# Check Node version
node --version

# Use nvm to switch versions
nvm install 20
nvm use 20
```

### Database Connection Errors

```bash
# Check PostgreSQL is running
docker compose ps db

# View database logs
docker compose logs db

# Test connection
psql $DATABASE_URL -c "SELECT 1;"
```

### GPU Not Detected

```bash
# Check ROCm devices
ls -la /dev/kfd /dev/dri

# Verify Docker can access GPU
docker run --rm --device=/dev/kfd --device=/dev/dri rocm/pytorch:latest rocm-smi

# Fall back to CPU
# In .env, set: FORCE_GPU=false
```

### Pre-commit Hooks Failing

```bash
# Update hooks
pre-commit autoupdate

# Run manually to see detailed errors
pre-commit run --all-files

# Skip hooks temporarily (not recommended)
git commit --no-verify
```

## Next Steps

Now that your development environment is set up:

1. **Read the Architecture Guide**: [architecture.md](architecture.md)
2. **Review Code Guidelines**: [code-guidelines.md](code-guidelines.md)
3. **Learn Testing Practices**: [testing.md](testing.md)
4. **Find Your First Issue**: Look for [`good first issue`](https://github.com/subculture-collective/transcript-create/labels/good%20first%20issue) labels

## Getting Help

- Check [CONTRIBUTING.md](../../CONTRIBUTING.md) for development workflows
- Read [First-Time Contributors Guide](../contributing/first-time.md)
- Ask questions in [GitHub Issues](https://github.com/subculture-collective/transcript-create/issues)
- Review existing [Pull Requests](https://github.com/subculture-collective/transcript-create/pulls) for examples

Happy coding! 🚀
