#!/usr/bin/env bash

# SPDX-FileCopyrightText: Manta contributors
#
# SPDX-License-Identifier: Apache-2.0

# Points $SITE_HOST at the VM: an A record to the VM's static IP, in the
# public Cloud DNS zone of $SITE_HOST's parent domain (manta-plan.org) in
# $GCP_DNS_PROJECT. The frontend's Caddy then gets a Let's Encrypt certificate
# for it on its own.
#
# The zone also has a *.manta-plan.org record for the sites behind the load
# balancer. A record for the exact name takes precedence over it.
#
# Skips a record that is already right. Fails when the name already points
# somewhere else, which is another instance or a site this workflow does not
# manage (baby, quack, www...). A DNS record cannot say who made it, so the IP
# is what tells them apart: the VM's address is static and reserved under its
# name, and stays the same across deployments.
#
# With --check-only, changes nothing and only checks that the name is free or
# already points at this VM. Preflight runs it that way, so a taken vm_name
# fails the run before a VM and an IP are created for it.
set -euo pipefail

check_only=false
if [ "${1:-}" = "--check-only" ]; then
  check_only=true
fi

: "${GCP_DNS_PROJECT:?}" "${GCP_PROJECT:?}" "${GCP_ZONE:?}" "${VM_NAME:?}" "${SITE_HOST:?}"
$check_only || : "${VM_IP:?}"

TTL=300
RECORD="${SITE_HOST}."
DOMAIN="${SITE_HOST#*.}."

dns() { gcloud --project "$GCP_DNS_PROJECT" --quiet dns "$@"; }

# The zone's resource name (e.g. manta-plan-squarespace) is what the record
# commands take; its DNS name is what we know.
zones=$(dns managed-zones list \
  --filter="dnsName=$DOMAIN AND visibility=public" --format='value(name)')
case $(grep -c . <<<"$zones" || true) in
  1) ZONE=$zones ;;
  0)
    echo "::error::No public Cloud DNS zone for $DOMAIN in $GCP_DNS_PROJECT. When the zone lives in another project than the VM, set the GCP_DNS_PROJECT repository variable to that project."
    exit 1
    ;;
  *)
    echo "::error::Several public Cloud DNS zones for $DOMAIN in $GCP_DNS_PROJECT ($(tr '\n' ' ' <<<"$zones")), so which one serves it is unclear."
    exit 1
    ;;
esac

current=$(dns record-sets list --zone "$ZONE" \
  --name "$RECORD" --type A --format='value(rrdatas[0])')

# The VM's IP when it already exists: from the VM itself, else from the static
# address reserved for it. Empty for a new instance.
if $check_only; then
  REGION=${GCP_ZONE%-*}
  VM_IP=$(gcloud --project "$GCP_PROJECT" compute instances describe "$VM_NAME" \
    --zone "$GCP_ZONE" --format='value(networkInterfaces[0].accessConfigs[0].natIP)' 2>/dev/null ||
    gcloud --project "$GCP_PROJECT" compute addresses describe "${VM_NAME}-ip" \
      --region "$REGION" --format='value(address)' 2>/dev/null || true)
fi

if [ -n "$current" ] && [ "$current" != "${VM_IP:-}" ]; then
  echo "::error::$SITE_HOST already points at $current, which is not $VM_NAME in $GCP_PROJECT${VM_IP:+ ($VM_IP)}. Pick another vm_name, or delete the record if it is left over from a deleted instance."
  exit 1
fi

if $check_only; then
  echo "$SITE_HOST is free or already points at $VM_NAME in $GCP_PROJECT."
  exit 0
fi

if [ "$current" = "$VM_IP" ]; then
  echo "==> $SITE_HOST already points at $VM_IP"
else
  echo "==> Pointing $SITE_HOST at $VM_IP"
  dns record-sets create "$RECORD" --zone "$ZONE" \
    --type A --ttl "$TTL" --rrdatas "$VM_IP"
fi
