#!/usr/bin/env bash
# Runs a command on the VM over SSH, as the deploy identity (OS Login).
#
#   scripts/deploy/gcp-ssh.sh '<remote command>'
#
# Stdin is passed through to the remote command, which is how the vm-*.sh
# scripts reach the VM:
#
#   scripts/deploy/gcp-ssh.sh 'sudo bash -s' < scripts/deploy/vm-setup.sh
set -euo pipefail

: "${GCP_PROJECT:?}" "${GCP_ZONE:?}" "${VM_NAME:?}"

# The keepalive stops the connection from being dropped as idle while a long,
# quiet step (an image build layer, a data download) runs on the VM.
exec gcloud compute ssh "$VM_NAME" \
  --project "$GCP_PROJECT" \
  --zone "$GCP_ZONE" \
  --quiet \
  --ssh-flag="-o ServerAliveInterval=30" \
  --command "$1"
