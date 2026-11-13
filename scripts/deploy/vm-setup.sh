#!/usr/bin/env bash
# Runs on the VM as root: installs what a deployment needs, which is only
# Docker (with Compose) and git, since the whole stack runs in containers.
# Safe to re-run; the deploy workflow runs it before every deployment, so a
# VM whose first setup was interrupted repairs itself.
#
#   scripts/deploy/gcp-ssh.sh 'sudo bash -s' < scripts/deploy/vm-setup.sh
set -euo pipefail

# Everything lives in a function, called on the last line: the script arrives
# on stdin, and a command that reads stdin (apt-get can) would otherwise
# swallow the rest of it.
main() {
  export DEBIAN_FRONTEND=noninteractive

  if command -v git >/dev/null && command -v curl >/dev/null && docker compose version >/dev/null 2>&1; then
    echo "==> Docker, git and curl are already installed"
  else
    # A VM that just booted may still hold the dpkg lock for its own first-boot
    # package run: wait for it instead of failing.
    apt_get() { apt-get -o DPkg::Lock::Timeout=300 -y "$@"; }

    echo "==> Installing Docker and git"
    apt_get update
    apt_get install ca-certificates curl git

    # Docker's own apt repository, see https://docs.docker.com/engine/install/debian/
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    cat >/etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/debian
Suites: $(. /etc/os-release && echo "$VERSION_CODENAME")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

    apt_get update
    apt_get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  fi

  systemctl enable --now docker
  docker --version
  docker compose version
}

main "$@" </dev/null
