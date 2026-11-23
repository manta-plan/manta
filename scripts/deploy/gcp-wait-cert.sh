#!/usr/bin/env bash
# Waits for the instance's Google-managed certificate (created by
# gcp-register-lb.sh) to become ACTIVE.
#
# A new certificate takes from a few minutes to an hour, which is no reason to
# fail a deployment that is otherwise done: after WAIT_MINUTES (default 20) it
# gives up with a warning, not an error, and Google keeps provisioning it. Only
# a certificate that will never be issued fails.
#
# Writes `active` (true/false) and `status` to $GITHUB_OUTPUT.
set -euo pipefail

: "${GCP_LB_PROJECT:?}" "${VM_NAME:?}" "${SITE_HOST:?}"

CERT="manta-${VM_NAME}-cert"
WAIT_MINUTES=${WAIT_MINUTES:-20}
INTERVAL=30

output() {
  {
    echo "active=$1"
    echo "status=$2"
  } >>"${GITHUB_OUTPUT:-/dev/null}"
}

attempts=$((WAIT_MINUTES * 60 / INTERVAL))
for attempt in $(seq 1 "$attempts"); do
  cert=$(gcloud --project "$GCP_LB_PROJECT" compute ssl-certificates describe "$CERT" \
    --global --format=json)
  status=$(jq -r '.managed.status // "UNKNOWN"' <<<"$cert")
  domain_status=$(jq -r '.managed.domainStatus // {} | to_entries | map("\(.key): \(.value)") | join(", ")' <<<"$cert")

  case "$status" in
    ACTIVE)
      echo "Certificate $CERT for $SITE_HOST is active"
      output true "$status"
      exit 0
      ;;
    PROVISIONING_FAILED_PERMANENTLY)
      echo "::error::Certificate $CERT will not be issued ($domain_status). Check that $SITE_HOST resolves to the load balancer, then delete the certificate and deploy again."
      output false "$status"
      exit 1
      ;;
    RENEWAL_FAILED)
      # The current certificate is still served until it expires.
      echo "::warning::Renewal of certificate $CERT failed ($domain_status); it is still served until it expires."
      output true "$status"
      exit 0
      ;;
  esac

  # PROVISIONING, or PROVISIONING_FAILED, which Google keeps retrying.
  echo "Certificate $CERT is $status ($domain_status), attempt $attempt of $attempts"
  sleep "$INTERVAL"
done

echo "::warning::Certificate $CERT for $SITE_HOST is still $status after $WAIT_MINUTES minutes. Google keeps provisioning it: https://$SITE_HOST works once it is active, usually within the hour. Check with: gcloud --project $GCP_LB_PROJECT compute ssl-certificates describe $CERT --global"
output false "$status"
