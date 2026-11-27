#!/usr/bin/env bash
# Lists which of the permissions a deployment needs the current identity is
# missing, in the hosting project and in the project of the DNS zone. Changes
# nothing, so it is safe to run at any time, also locally:
#
#   GCP_PROJECT=my-project GCP_DNS_PROJECT=paros-491610 scripts/deploy/gcp-preflight.sh
#
# The roles that grant these are listed in the comments below.
set -euo pipefail

: "${GCP_PROJECT:?}" "${GCP_DNS_PROJECT:?}"

# roles/compute.instanceAdmin.v1, roles/compute.publicIpAdmin,
# roles/compute.securityAdmin and roles/compute.osAdminLogin.
# serviceusage.services.enable is left out: it is only needed in a project
# where the Compute Engine API is still off.
HOSTING_PERMISSIONS=(
  compute.zones.get
  compute.instances.create
  compute.instances.get
  compute.instances.start
  compute.instances.setMetadata
  compute.instances.setTags
  compute.instances.setLabels
  compute.disks.create
  compute.addresses.create
  compute.addresses.get
  compute.addresses.use
  compute.subnetworks.use
  compute.subnetworks.useExternalIp
  compute.firewalls.create
  compute.firewalls.get
  compute.networks.updatePolicy
  compute.instances.osAdminLogin
)

# roles/dns.admin, or a custom role with only these.
DNS_PERMISSIONS=(
  dns.managedZones.list
  dns.resourceRecordSets.list
  dns.resourceRecordSets.create
  dns.changes.create
  dns.changes.get
)

account=$(gcloud config get-value account 2>/dev/null)
token=$(gcloud auth print-access-token)
echo "Authenticated as ${account:-unknown}"

missing=0
unchecked=0

# check <project> <permission>...
check() {
  local project=$1
  shift
  local body response granted permission

  echo
  echo "Permissions in $project:"
  body=$(printf '%s\n' "$@" | jq -R . | jq -sc '{permissions: .}')
  if ! response=$(curl -sS --fail-with-body -X POST \
    -H "Authorization: Bearer $token" \
    -H "Content-Type: application/json" \
    -d "$body" \
    "https://cloudresourcemanager.googleapis.com/v1/projects/${project}:testIamPermissions"); then
    # Typically the Cloud Resource Manager API being disabled in the service
    # account's own project. Not fatal: a missing permission still fails the
    # step that needs it, just one at a time.
    echo "::warning::Could not check the permissions in $project: $(jq -r '.error.message // .' <<<"$response" 2>/dev/null || echo "$response")"
    unchecked=1
    return 0
  fi

  granted=$(jq -r '.permissions[]?' <<<"$response")
  for permission in "$@"; do
    if grep -qxF "$permission" <<<"$granted"; then
      echo "  ok       $permission"
    else
      echo "  MISSING  $permission"
      missing=1
    fi
  done
}

check "$GCP_PROJECT" "${HOSTING_PERMISSIONS[@]}"
check "$GCP_DNS_PROJECT" "${DNS_PERMISSIONS[@]}"

echo
if [ "$missing" -ne 0 ]; then
  echo "::error::$account is missing permissions (see the list above). The roles to grant are listed in the comments of scripts/deploy/gcp-preflight.sh."
  exit 1
fi
if [ "$unchecked" -ne 0 ]; then
  echo "Some permissions could not be checked (see the warnings above), so they are unverified."
else
  echo "All checked permissions are granted."
fi
