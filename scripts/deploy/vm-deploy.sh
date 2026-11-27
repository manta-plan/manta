#!/usr/bin/env bash
# Runs on the VM as root: checks out a commit and (re)starts the whole stack
# from docker/compose-dev-fullstack.yaml, with the frontend on ports 80 and 443
# and the temporary record server (quack-server) behind it.
#
#   scripts/deploy/gcp-ssh.sh 'sudo bash -s -- --repo <url> --sha <sha> --site-host <host> [--no-guest-login] [--reset-data]' \
#     < scripts/deploy/vm-deploy.sh
#
# --site-host is the public hostname (<vm_name>.manta-plan.org), which DNS
# already points at this VM. It becomes the frontend's SITE_ADDRESS, so its
# Caddy gets and renews a Let's Encrypt certificate for it and serves the site
# over HTTPS. The certificate lives in the caddy-data volume and outlives
# redeployments.
#
# --no-guest-login hides "Continue as guest" and makes the backend refuse guest
# logins (GUEST_LOGIN_ENABLED=false), so only existing users can sign in.
#
# --reset-data also deletes the data volumes (database, stored files, Keycloak
# users), so the instance starts from scratch. It keeps caddy-data: Let's
# Encrypt issues at most 5 certificates for the same name a week.
#
# This script comes from the branch the workflow runs from, not from the commit
# being deployed, so a branch that predates it can still be deployed.
set -euo pipefail

APP_DIR=/opt/manta
OVERRIDE=/opt/manta-compose-deploy.yaml
PORT=80
HTTPS_PORT=443
SITE_HOST=""
GUEST_LOGIN_ENABLED=true
# Compose's project name (`name:` in compose-dev-fullstack.yaml) and the
# volume that holds Caddy's certificates.
PROJECT=manta
CADDY_VOLUME=caddy-data

# The temporary-quack-setup profile adds quack-server. Variables set here take
# precedence over backend/.env, whose SITE_ADDRESS (empty, plain HTTP) and
# VITE_RECORD_SERVER (localhost:5173, read by older commits) are only right
# for a local run.
compose() {
  FRONTEND_PORT=$PORT \
    FRONTEND_HTTPS_PORT=$HTTPS_PORT \
    SITE_ADDRESS=$SITE_HOST \
    GUEST_LOGIN_ENABLED=$GUEST_LOGIN_ENABLED \
    COMPOSE_PROFILES=temporary-quack-setup \
    VITE_RECORD_SERVER=$SITE_HOST \
    docker compose \
    --env-file backend/.env \
    -f docker/compose-dev-fullstack.yaml \
    -f "$OVERRIDE" \
    "$@"
}

diagnostics() {
  echo "==> Deployment failed. State of the stack:"
  compose ps --all || true
  echo "==> Last backend logs:"
  compose logs --no-color --tail 100 backend || true
  echo "==> Last frontend (Caddy) logs, which show why a certificate was not issued:"
  compose logs --no-color --tail 50 frontend || true
}

# Deletes the stack's volumes except Caddy's certificates. Run after `down`.
delete_data_volumes() {
  local volume
  for volume in $(docker volume ls --quiet --filter "label=com.docker.compose.project=$PROJECT"); do
    if [ "$(docker volume inspect --format '{{ index .Labels "com.docker.compose.volume" }}' "$volume")" != "$CADDY_VOLUME" ]; then
      docker volume rm "$volume" >/dev/null
      echo "    deleted $volume"
    fi
  done
}

# Everything lives in a function, called on the last line: the script arrives
# on stdin, and a command that reads stdin would otherwise swallow the rest.
main() {
  local repo="" sha="" reset_data=false
  while [ $# -gt 0 ]; do
    case "$1" in
      --repo) repo=$2 && shift 2 ;;
      --sha) sha=$2 && shift 2 ;;
      --site-host) SITE_HOST=$2 && shift 2 ;;
      --reset-data) reset_data=true && shift ;;
      --no-guest-login) GUEST_LOGIN_ENABLED=false && shift ;;
      *) echo "Unknown argument: $1" >&2 && exit 2 ;;
    esac
  done
  if [ -z "$repo" ] || [ -z "$sha" ] || [ -z "$SITE_HOST" ]; then
    echo "Usage: vm-deploy.sh --repo <url> --sha <sha> --site-host <host> [--no-guest-login] [--reset-data]" >&2
    exit 2
  fi

  echo "==> Checking out $sha"
  git init --quiet "$APP_DIR"
  cd "$APP_DIR"
  git remote remove origin 2>/dev/null || true
  git remote add origin "$repo"
  git fetch --quiet --depth 1 origin "$sha"
  git checkout --quiet --force --detach FETCH_HEAD

  if [ ! -f docker/compose-dev-fullstack.yaml ]; then
    echo "This commit has no docker/compose-dev-fullstack.yaml: it predates the backend and frontend images, and cannot be deployed this way." >&2
    exit 1
  fi
  # Older frontends serve plain HTTP only (no SITE_ADDRESS, no port 443, no
  # volume for the certificate), and nothing in front of the VM adds HTTPS.
  if ! grep -q 'SITE_ADDRESS' docker/compose-dev-fullstack.yaml; then
    echo "This commit's frontend cannot serve HTTPS itself (no SITE_ADDRESS in docker/compose-dev-fullstack.yaml), so it cannot be deployed this way. Deploy a commit that includes it." >&2
    exit 1
  fi

  # The dev compose files have no restart policy on purpose (a crash should be
  # visible locally). A deployed instance must come back after a reboot or a
  # Docker upgrade, so add one to every long-lived service; the one-shot
  # services (the image builder, the provisioner) are left alone.
  cat >"$OVERRIDE" <<'EOF'
# Written by scripts/deploy/vm-deploy.sh on every deployment. Do not edit.
services:
  postgres: { restart: unless-stopped }
  seaweedfs: { restart: unless-stopped }
  prefect-server: { restart: unless-stopped }
  keycloak: { restart: unless-stopped }
  block-worker: { restart: unless-stopped }
  playbook-worker: { restart: unless-stopped }
  backend: { restart: unless-stopped }
  frontend: { restart: unless-stopped }
EOF
  # Only in commits that have it: an override for a service that does not
  # exist fails the whole compose file.
  if grep -q '^  quack-server:' docker/compose-dev-services.yaml; then
    echo "  quack-server: { restart: unless-stopped }" >>"$OVERRIDE"
  fi

  # Build while the previous version keeps serving, so the downtime is the
  # restart alone and a broken build takes nothing down.
  echo "==> Building images"
  compose build

  if [ "$reset_data" = true ]; then
    echo "==> Stopping the stack and deleting its data (keeping $CADDY_VOLUME)"
    compose down --remove-orphans
    delete_data_volumes
  else
    echo "==> Stopping the stack"
    compose down --remove-orphans
  fi

  # Returns once the frontend has started, which waits for a healthy backend,
  # which in turn waits for every service it depends on. On a fresh volume the
  # backend first downloads the example data, which takes a few minutes.
  echo "==> Starting the stack"
  if ! compose up --detach; then
    diagnostics
    exit 1
  fi

  # Over HTTPS, with the site's own name but to this VM, so the check covers
  # Caddy's certificate too. On plain HTTP Caddy only redirects to HTTPS. A
  # first certificate usually takes under a minute, more while the DNS record
  # is new.
  local url="https://$SITE_HOST/v1/health"
  echo "==> Checking $url on this VM"
  for _ in $(seq 1 60); do
    if curl -fsS -o /dev/null --max-time 5 \
      --resolve "$SITE_HOST:$HTTPS_PORT:127.0.0.1" "$url" 2>/dev/null; then
      # Each deployment leaves the previous images and build layers behind.
      docker image prune --force >/dev/null
      docker builder prune --force --filter until=168h >/dev/null
      echo "==> Deployed $sha"
      return 0
    fi
    sleep 5
  done

  echo "No 200 from $url on this VM within 5 minutes. When the backend logs look fine, the frontend logs below say whether Let's Encrypt could not reach the VM (DNS record, firewall) or refused the request (rate limit)." >&2
  diagnostics
  exit 1
}

main "$@" </dev/null
