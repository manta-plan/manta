#!/usr/bin/env bash
# Prepares the hosting project and makes sure the VM exists and is running.
# Every step skips what is already there, so this is safe to re-run.
#
#   1. Enables the Compute Engine API.
#   2. Creates the firewall rules for the network tag `manta`.
#   3. Creates the VM with a static external IP, unless it already exists.
#
# Writes `created` (true/false) and `ip` to $GITHUB_OUTPUT.
set -euo pipefail

: "${GCP_PROJECT:?}" "${GCP_ZONE:?}" "${GCP_MACHINE_TYPE:?}" "${VM_NAME:?}"

NETWORK=${GCP_NETWORK:-default}
IMAGE_FAMILY=${GCP_IMAGE_FAMILY:-debian-13}
# The default 10 GB cannot hold the images the stack builds (the PyPSA block
# image alone is several GB), let alone the data.
BOOT_DISK_SIZE=${GCP_BOOT_DISK_SIZE:-50GB}
TAG=manta
ADDRESS="${VM_NAME}-ip"
REGION=${GCP_ZONE%-*}

# Where a global external Application Load Balancer's requests to a backend
# outside its own project come from (the VM is reached over its external IP,
# through an internet NEG). These are not the usual health-check ranges.
# Source: `dig +short TXT _cloud-eoips.googleusercontent.com`.
LB_SOURCE_RANGES=34.96.0.0/20,34.127.192.0/18

g() { gcloud --project "$GCP_PROJECT" --quiet "$@"; }

# Enabling an API needs roles/serviceusage.serviceUsageAdmin, so it is only
# attempted where the API is off: a project that already uses Compute Engine
# does not need that role.
if probe=$(g compute zones describe "$GCP_ZONE" --format='value(name)' 2>&1); then
  echo "==> The Compute Engine API is enabled in $GCP_PROJECT"
elif grep -q 'has not been used in project .* or it is disabled' <<<"$probe"; then
  echo "==> Enabling the Compute Engine API in $GCP_PROJECT"
  g services enable compute.googleapis.com
else
  echo "$probe" >&2
  exit 1
fi

# ensure_firewall_rule <name> <flags for `firewall-rules create`>...
ensure_firewall_rule() {
  local name=$1
  shift
  if g compute firewall-rules describe "$name" >/dev/null 2>&1; then
    echo "==> Firewall rule $name already exists"
  else
    echo "==> Creating firewall rule $name"
    g compute firewall-rules create "$name" \
      --network "$NETWORK" --direction INGRESS --target-tags "$TAG" "$@"
  fi
}

ensure_firewall_rule manta-allow-ssh \
  --allow tcp:22 --source-ranges 0.0.0.0/0 \
  --description "SSH to Manta instances, used by the deploy workflow"
# Only the frontend is reachable, and only through the load balancer. The
# stack publishes other ports on the VM (Postgres, Keycloak, Prefect, S3, the
# backend), all with default credentials: never open those.
ensure_firewall_rule manta-allow-lb \
  --allow tcp:80 --source-ranges "$LB_SOURCE_RANGES" \
  --description "The load balancer to the frontend of Manta instances"

if g compute instances describe "$VM_NAME" --zone "$GCP_ZONE" >/dev/null 2>&1; then
  created=false
  status=$(g compute instances describe "$VM_NAME" --zone "$GCP_ZONE" --format='value(status)')
  echo "==> VM $VM_NAME already exists ($status)"
  if [ "$status" = "TERMINATED" ] || [ "$status" = "SUSPENDED" ]; then
    echo "==> Starting $VM_NAME"
    if [ "$status" = "SUSPENDED" ]; then
      g compute instances resume "$VM_NAME" --zone "$GCP_ZONE"
    else
      g compute instances start "$VM_NAME" --zone "$GCP_ZONE"
    fi
  fi
else
  created=true
  if ! g compute addresses describe "$ADDRESS" --region "$REGION" >/dev/null 2>&1; then
    echo "==> Reserving static IP $ADDRESS"
    g compute addresses create "$ADDRESS" --region "$REGION"
  fi
  address=$(g compute addresses describe "$ADDRESS" --region "$REGION" --format='value(address)')

  echo "==> Creating VM $VM_NAME ($GCP_MACHINE_TYPE, $IMAGE_FAMILY, $BOOT_DISK_SIZE) at $address"
  # OS Login lets the deploy identity SSH in with an IAM role alone. No
  # service account: nothing on the VM calls Google APIs, so a compromised
  # instance holds no GCP credentials.
  g compute instances create "$VM_NAME" \
    --zone "$GCP_ZONE" \
    --machine-type "$GCP_MACHINE_TYPE" \
    --image-family "$IMAGE_FAMILY" \
    --image-project debian-cloud \
    --boot-disk-size "$BOOT_DISK_SIZE" \
    --boot-disk-type pd-balanced \
    --network "$NETWORK" \
    --address "$address" \
    --tags "$TAG" \
    --labels app=manta \
    --metadata enable-oslogin=TRUE \
    --no-service-account \
    --no-scopes
fi

# Read back from the VM rather than the reserved address, so a VM that was
# created by hand also works.
ip=$(g compute instances describe "$VM_NAME" --zone "$GCP_ZONE" \
  --format='value(networkInterfaces[0].accessConfigs[0].natIP)')
if [ -z "$ip" ]; then
  echo "::error::VM $VM_NAME has no external IP, so the load balancer cannot reach it."
  exit 1
fi
echo "==> VM $VM_NAME is at $ip"

{
  echo "created=$created"
  echo "ip=$ip"
} >>"${GITHUB_OUTPUT:-/dev/null}"
