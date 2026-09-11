#!/usr/bin/env bash
# Public edge for AI Service Mesh on factory host (factory-host / 203.0.113.10).
# DNS: A record service-mesh.modelmarket.dev → this host.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MESH="$ROOT/ai-service-mesh"
DOMAIN="service-mesh.modelmarket.dev"
NGINX_SRC="$ROOT/deploy/nginx/service-mesh.modelmarket.dev.conf"
EMAIL="${CERTBOT_EMAIL:-ops@modelmarket.dev}"

echo "=== Service Mesh public edge ($DOMAIN) ==="

if [[ ! -d "$MESH" ]]; then
  echo "ERROR: $MESH not found" >&2
  exit 1
fi

# Public dashboard reads (no Bearer) + CORS for same-origin SPA
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
python3 <<PY
from pathlib import Path
env = Path("$ENV_FILE")
text = env.read_text(encoding="utf-8") if env.is_file() else ""
lines = [ln for ln in text.splitlines() if ln.strip()]
def set_kv(key: str, val: str) -> None:
    global lines
    lines = [ln for ln in lines if not ln.startswith(key + "=")]
    lines.append(f"{key}={val}")
set_kv("MESH_PUBLIC_READ", "1")
cors = "https://service-mesh.modelmarket.dev,http://127.0.0.1:8091,http://localhost:5173"
set_kv("MESH_CORS_ORIGINS", cors)
env.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("Updated", env, "MESH_PUBLIC_READ=1 + CORS")
PY

# Compose interpolates ${MESH_*} from the shell — export after writing .env
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
export MESH_PUBLIC_READ=1
export MESH_CORS_ORIGINS="https://service-mesh.modelmarket.dev,http://127.0.0.1:8091,http://localhost:5173"

cd "$MESH"
export AICOM_IMAGE_TAG="${AICOM_IMAGE_TAG:-$("$ROOT/scripts/docker_image_tag.sh")}"
echo "Image tag: $AICOM_IMAGE_TAG"

# Recreate API with public_read + build dashboard
docker compose -f docker-compose.prod.yml up -d --force-recreate --build mesh-api
docker compose -f docker-compose.prod.yml -f docker-compose.dashboard.yml build mesh-dashboard
docker compose -f docker-compose.prod.yml -f docker-compose.dashboard.yml up -d mesh-dashboard

echo "Waiting for API + dashboard..."
for _ in $(seq 1 40); do
  if curl -sf "http://127.0.0.1:8090/health" >/dev/null && curl -sf "http://127.0.0.1:8091/" >/dev/null; then
    break
  fi
  sleep 2
done
curl -sf "http://127.0.0.1:8090/health" | head -c 200; echo
# stats may 401 until recreate picks up MESH_PUBLIC_READ — soft check
curl -s "http://127.0.0.1:8090/v1/stats" | head -c 300; echo

# Nginx site
if [[ "$(id -u)" -eq 0 ]]; then
  mkdir -p /var/www/certbot
  cp "$NGINX_SRC" /etc/nginx/sites-available/service-mesh.modelmarket.dev.conf
  ln -sfn /etc/nginx/sites-available/service-mesh.modelmarket.dev.conf /etc/nginx/sites-enabled/service-mesh.modelmarket.dev.conf
  nginx -t
  systemctl reload nginx

  if [[ ! -d "/etc/letsencrypt/live/$DOMAIN" ]]; then
    echo "Requesting Let's Encrypt cert for $DOMAIN..."
    certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$EMAIL" --redirect || {
      echo "WARN: certbot failed — is DNS A for $DOMAIN pointing here? Retry later." >&2
    }
  else
    echo "Cert already present for $DOMAIN"
    certbot renew --dry-run >/dev/null 2>&1 || true
  fi
  # Ensure renew timer is active (auto-renewal)
  systemctl enable --now certbot.timer 2>/dev/null || systemctl enable --now certbot.service 2>/dev/null || true
  systemctl list-timers --all 2>/dev/null | grep -i certbot || true
else
  echo "Not root — copy nginx conf and run certbot manually:"
  echo "  sudo cp $NGINX_SRC /etc/nginx/sites-available/"
  echo "  sudo ln -sfn /etc/nginx/sites-available/service-mesh.modelmarket.dev.conf /etc/nginx/sites-enabled/"
  echo "  sudo nginx -t && sudo systemctl reload nginx"
  echo "  sudo certbot --nginx -d $DOMAIN --agree-tos -m $EMAIL --redirect"
fi

echo "Live: https://$DOMAIN/"
echo "API:  https://$DOMAIN/health"
