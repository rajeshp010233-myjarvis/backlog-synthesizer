#!/bin/bash
# EC2 bootstrap script — runs once on first launch as root
# Installs: Docker, Docker Compose plugin, SSM agent, AWS CLI v2
set -euo pipefail

APP_DIR="/opt/backlog-synthesizer"
APP_USER="ec2-user"

# ── System update ─────────────────────────────────────────────────────────────
dnf update -y

# ── Docker ────────────────────────────────────────────────────────────────────
dnf install -y docker
systemctl enable --now docker
usermod -aG docker "$APP_USER"

# Docker Compose plugin (v2)
mkdir -p /usr/local/lib/docker/cli-plugins
curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# ── AWS SSM agent (Amazon Linux 2023 includes it, but ensure it's running) ───
systemctl enable --now amazon-ssm-agent || true

# ── AWS CLI v2 ────────────────────────────────────────────────────────────────
if ! command -v aws &>/dev/null; then
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
  unzip -q /tmp/awscliv2.zip -d /tmp
  /tmp/aws/install
  rm -rf /tmp/aws /tmp/awscliv2.zip
fi

# ── App directory ─────────────────────────────────────────────────────────────
mkdir -p "$APP_DIR"
chown "$APP_USER":"$APP_USER" "$APP_DIR"

# ── docker-compose.yml for production (pulls from ECR) ───────────────────────
# The deploy workflow will `docker compose up -d --no-build` after pulling images.
# ECR_REGISTRY and IMAGE_TAG are set by the deploy workflow via SSM environment.
cat > "$APP_DIR/docker-compose.yml" <<'COMPOSE'
version: "3.9"

services:
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    volumes:
      - redis_data:/data

  backend:
    image: ${ECR_REGISTRY}/backlog-synthesizer-backend:${IMAGE_TAG:-latest}
    restart: unless-stopped
    env_file: .env
    environment:
      - REDIS_URL=redis://redis:6379
    ports:
      - "8000:8000"
    depends_on:
      - redis

  mcp-server:
    image: ${ECR_REGISTRY}/backlog-synthesizer-mcp-server:${IMAGE_TAG:-latest}
    restart: unless-stopped
    env_file: .env
    environment:
      - BACKEND_URL=http://backend:8000
    ports:
      - "8002:8002"
    depends_on:
      - backend

  frontend:
    image: ${ECR_REGISTRY}/backlog-synthesizer-frontend:${IMAGE_TAG:-latest}
    restart: unless-stopped
    ports:
      - "80:80"
    depends_on:
      - backend

volumes:
  redis_data:
COMPOSE

chown "$APP_USER":"$APP_USER" "$APP_DIR/docker-compose.yml"

# ── Placeholder .env (real secrets added manually or via SSM Parameter Store) ─
if [ ! -f "$APP_DIR/.env" ]; then
  cat > "$APP_DIR/.env" <<'ENV'
# Fill these in after deployment — do NOT commit to git
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GOOGLE_API_KEY=
APP_API_KEY=
MCP_API_KEY=
JIRA_BASE_URL=
JIRA_EMAIL=
JIRA_TOKEN=
JIRA_PROJECT_KEY=
ENV
  chown "$APP_USER":"$APP_USER" "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
fi

echo "Bootstrap complete. Reboot recommended to apply docker group membership."
