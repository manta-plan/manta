#!/usr/bin/env bash
# Runs on the VM as root: checks out a commit and (re)starts the whole stack
# from docker/compose-dev-fullstack.yaml, with the frontend on port 80 and the
# temporary record server (quack-server) behind it.
#
#   scripts/deploy/gcp-ssh.sh 'sudo bash -s -- --repo <url> --sha <sha> --site-host <host> [--reset-data]' \
#     < scripts/deploy/vm-deploy.sh
#
# --site-host is the public hostname (<vm_name>.manta-plan.org). The frontend
# reaches the record server through its own Caddy at that hostname (same
# origin, HTTPS through the load balancer), never at the record server's
# published port, so the frontend is built with VITE_RECORD_SERVER set to it.
#
# --reset-data also deletes the data volumes (database, stored files, Keycloak
# users), so the instance starts from scratch.
#
# This script comes from the branch the workflow runs from, not from the commit
# being deployed, so a branch that predates it can still be deployed.
set -euo pipefail

APP_DIR=/opt/manta
OVERRIDE=/opt/manta-compose-deploy.yaml
PORT=80
SITE_HOST=""

# The temporary-quack-setup profile adds quack-server. Variables set here take
# precedence over backend/.env, whose VITE_RECORD_SERVER (localhost:5173) is
# only right for a local run.
compose() {
  FRONTEND_PORT=$PORT \
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
      *) echo "Unknown argument: $1" >&2 && exit 2 ;;
    esac
  done
  if [ -z "$repo" ] || [ -z "$sha" ] || [ -z "$SITE_HOST" ]; then
    echo "Usage: vm-deploy.sh --repo <url> --sha <sha> --site-host <host> [--reset-data]" >&2
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
    echo "==> Stopping the stack and deleting its data"
    compose down --remove-orphans --volumes
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

  echo "==> Checking http://localhost:$PORT/v1/health"
  for _ in $(seq 1 30); do
    if curl -fsS -o /dev/null --max-time 5 "http://localhost:$PORT/v1/health"; then
      # Each deployment leaves the previous images and build layers behind.
      docker image prune --force >/dev/null
      docker builder prune --force --filter until=168h >/dev/null
      echo "==> Deployed $sha"
      return 0
    fi
    sleep 2
  done

  echo "No 200 from http://localhost:$PORT/v1/health within 60s." >&2
  diagnostics
  exit 1
}

main "$@" </dev/null
