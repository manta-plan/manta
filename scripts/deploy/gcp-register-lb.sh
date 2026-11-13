#!/usr/bin/env bash
# Serves the VM at $SITE_HOST through the existing load balancer, which lives
# in another project than the VM:
#
#   1. An internet NEG pointing at the VM's external IP, port 80 (the frontend).
#   2. A backend service on top of it.
#   3. A host rule for $SITE_HOST in the URL map, pointing at that backend.
#
# Every step skips what is already there. Fails when the subdomain is already
# taken by something else (another project's VM, or a hand-made host rule).
set -euo pipefail

: "${GCP_LB_PROJECT:?}" "${GCP_URL_MAP:?}" "${GCP_PROJECT:?}" "${VM_NAME:?}" "${VM_IP:?}" "${SITE_HOST:?}"

PORT=80
NEG="manta-${VM_NAME}-neg"
BACKEND="manta-${VM_NAME}-backend"
PATH_MATCHER="manta-${VM_NAME}"
# Stored on the backend service: who the subdomain belongs to.
OWNER="manta-deploy project=${GCP_PROJECT} vm=${VM_NAME}"

lb() { gcloud --project "$GCP_LB_PROJECT" --quiet "$@"; }

# --- Is the subdomain free, or already ours? -------------------------------

url_map=$(lb compute url-maps describe "$GCP_URL_MAP" --global --format=json)
host_matcher=$(jq -r --arg host "$SITE_HOST" \
  '.hostRules[]? | select(.hosts | index($host)) | .pathMatcher' <<<"$url_map")
if [ -n "$host_matcher" ] && [ "$host_matcher" != "$PATH_MATCHER" ]; then
  echo "::error::$SITE_HOST is already routed by path matcher '$host_matcher' in $GCP_URL_MAP, which this workflow does not manage. Pick another vm_name."
  exit 1
fi

if backend=$(lb compute backend-services describe "$BACKEND" --global --format=json 2>/dev/null); then
  backend_owner=$(jq -r '.description // ""' <<<"$backend")
  if [ "$backend_owner" != "$OWNER" ]; then
    echo "::error::$SITE_HOST is already used by another instance ($backend_owner). Pick another vm_name."
    exit 1
  fi
else
  backend=""
fi

# --- Internet NEG ------------------------------------------------------------

if ! lb compute network-endpoint-groups describe "$NEG" --global >/dev/null 2>&1; then
  echo "==> Creating network endpoint group $NEG"
  lb compute network-endpoint-groups create "$NEG" --global \
    --network-endpoint-type INTERNET_IP_PORT
fi

# An internet NEG holds a single endpoint: replace it when the IP changed.
endpoints=$(lb compute network-endpoint-groups list-network-endpoints "$NEG" --global \
  --format='csv[no-heading](networkEndpoint.ipAddress,networkEndpoint.port)')
if [ "$endpoints" = "$VM_IP,$PORT" ]; then
  echo "==> $NEG already points at $VM_IP:$PORT"
else
  while IFS=, read -r old_ip old_port; do
    [ -n "$old_ip" ] || continue
    echo "==> Removing stale endpoint $old_ip:$old_port from $NEG"
    lb compute network-endpoint-groups update "$NEG" --global \
      --remove-endpoint "ip=$old_ip,port=$old_port"
  done <<<"$endpoints"
  echo "==> Pointing $NEG at $VM_IP:$PORT"
  lb compute network-endpoint-groups update "$NEG" --global \
    --add-endpoint "ip=$VM_IP,port=$PORT"
fi

# --- Backend service ---------------------------------------------------------

# A backend service must use the same scheme as the load balancer it joins:
# EXTERNAL_MANAGED (global external Application LB) or EXTERNAL (classic).
# Read it off the forwarding rule in front of the URL map.
lb_scheme() {
  local kind proxy scheme
  for kind in https http; do
    for proxy in $(lb compute "target-${kind}-proxies" list --global \
      --filter="urlMap~'/urlMaps/${GCP_URL_MAP}\$'" --format='value(name)'); do
      scheme=$(lb compute forwarding-rules list --global \
        --filter="target~'/${proxy}\$'" --format='value(loadBalancingScheme)' | head -n 1)
      if [ -n "$scheme" ]; then
        echo "$scheme"
        return 0
      fi
    done
  done
  return 1
}

if [ -z "$backend" ]; then
  if ! scheme=${GCP_LB_SCHEME:-$(lb_scheme)}; then
    echo "::error::Could not find a forwarding rule in front of URL map $GCP_URL_MAP in $GCP_LB_PROJECT, so the load balancing scheme is unknown."
    exit 1
  fi
  echo "==> Creating backend service $BACKEND ($scheme)"
  # No health check: a global internet NEG does not support one.
  lb compute backend-services create "$BACKEND" --global \
    --load-balancing-scheme "$scheme" \
    --protocol HTTP \
    --description "$OWNER"
  backend=$(lb compute backend-services describe "$BACKEND" --global --format=json)
fi

if jq -e --arg neg "/networkEndpointGroups/$NEG" \
  '[.backends[]?.group | select(endswith($neg))] | length > 0' <<<"$backend" >/dev/null; then
  echo "==> $BACKEND already serves $NEG"
else
  echo "==> Adding $NEG to $BACKEND"
  lb compute backend-services add-backend "$BACKEND" --global \
    --network-endpoint-group "$NEG" --global-network-endpoint-group
fi

# --- Host rule ---------------------------------------------------------------

if [ "$host_matcher" = "$PATH_MATCHER" ]; then
  echo "==> $GCP_URL_MAP already routes $SITE_HOST"
else
  echo "==> Routing $SITE_HOST to $BACKEND in $GCP_URL_MAP"
  lb compute url-maps add-path-matcher "$GCP_URL_MAP" --global \
    --path-matcher-name "$PATH_MATCHER" \
    --default-service "$BACKEND" \
    --new-hosts "$SITE_HOST"
  echo "A new host rule takes a few minutes to reach every Google front end."
fi
