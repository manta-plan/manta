#!/usr/bin/env bash
# Serves the VM at $SITE_HOST through the existing load balancer, which lives
# in another project than the VM:
#
#   1. An internet NEG pointing at the VM's external IP, port 80 (the frontend).
#   2. A backend service on top of it.
#   3. A host rule for $SITE_HOST in the URL map, pointing at that backend.
#   4. A Google-managed certificate for $SITE_HOST, attached to the HTTPS
#      proxy in front of the URL map (next to the certificates already there).
#
# DNS needs nothing per instance: the zone's *.manta-plan.org A record already
# points at the load balancer. Google-managed certificates cannot be wildcards,
# hence one per instance. Google provisions it once the host resolves to the
# load balancer, which takes from a few minutes to an hour the first time.
#
# Every step skips what is already there. Fails when the subdomain is already
# taken by something else (another project's VM, or a hand-made host rule).
#
# With --check-only, only checks that the subdomain is free or already ours and
# that the HTTPS proxy has room for its certificate, and changes nothing.
# Preflight runs it that way, so a taken vm_name fails the run before a VM and
# an IP are created for it.
set -euo pipefail

check_only=false
if [ "${1:-}" = "--check-only" ]; then
  check_only=true
fi

: "${GCP_LB_PROJECT:?}" "${GCP_URL_MAP:?}" "${GCP_PROJECT:?}" "${VM_NAME:?}" "${SITE_HOST:?}"
$check_only || : "${VM_IP:?}"

PORT=80
NEG="manta-${VM_NAME}-neg"
BACKEND="manta-${VM_NAME}-backend"
PATH_MATCHER="manta-${VM_NAME}"
CERT="manta-${VM_NAME}-cert"
# A target HTTPS proxy holds at most 15 SSL certificates.
MAX_PROXY_CERTS=15
# Stored on the backend service and the certificate: who the subdomain belongs
# to.
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

if cert=$(lb compute ssl-certificates describe "$CERT" --global --format=json 2>/dev/null); then
  cert_owner=$(jq -r '.description // ""' <<<"$cert")
  if [ "$cert_owner" != "$OWNER" ]; then
    echo "::error::Certificate $CERT already belongs to another instance ($cert_owner). Pick another vm_name."
    exit 1
  fi
else
  cert=""
fi

# --- Does the HTTPS proxy have room for the certificate? --------------------

proxies=$(lb compute target-https-proxies list --global \
  --filter="urlMap~'/urlMaps/${GCP_URL_MAP}\$'" --format=json)
if [ "$(jq length <<<"$proxies")" -eq 0 ]; then
  echo "::error::No target HTTPS proxy in $GCP_LB_PROJECT uses URL map $GCP_URL_MAP, so there is nothing to attach the certificate to."
  exit 1
fi
# A proxy with a certificate map ignores its SSL certificates altogether.
with_map=$(jq -r '.[] | select(.certificateMap) | .name' <<<"$proxies")
if [ -n "$with_map" ]; then
  echo "::error::Target HTTPS proxy $with_map uses a Certificate Manager map, which this workflow does not manage: add a map entry for $SITE_HOST by hand, or teach gcp-register-lb.sh about maps."
  exit 1
fi
full=$(jq -r --arg cert "/sslCertificates/$CERT" --argjson max "$MAX_PROXY_CERTS" \
  '.[] | select([.sslCertificates[]? | select(endswith($cert))] | length == 0)
       | select((.sslCertificates // []) | length >= $max) | .name' <<<"$proxies")
if [ -n "$full" ]; then
  echo "::error::Target HTTPS proxy $full already holds $MAX_PROXY_CERTS certificates, the most it can. Remove the certificate of an instance that is gone, or move the load balancer to a Certificate Manager map."
  exit 1
fi

if $check_only; then
  echo "$SITE_HOST is free or already belongs to $VM_NAME in $GCP_PROJECT, and the HTTPS proxy has room for its certificate."
  exit 0
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

# --- Certificate -------------------------------------------------------------

if [ -z "$cert" ]; then
  echo "==> Creating Google-managed certificate $CERT for $SITE_HOST"
  lb compute ssl-certificates create "$CERT" --global \
    --domains "$SITE_HOST" \
    --description "$OWNER"
fi
cert_url=$(lb compute ssl-certificates describe "$CERT" --global --format='value(selfLink)')

# attach_certificate <proxy>: adds the certificate to the proxy's list, keeping
# the others. Setting the list replaces it as a whole and the API has no
# fingerprint to guard that, so a deployment of another VM doing the same at
# the same moment could undo our change: read it back, and retry if so.
attach_certificate() {
  local proxy=$1 attempt current list
  for attempt in 1 2 3 4; do
    current=$(lb compute target-https-proxies describe "$proxy" --global --format=json)
    if jq -e --arg cert "/sslCertificates/$CERT" \
      '[.sslCertificates[]? | select(endswith($cert))] | length > 0' <<<"$current" >/dev/null; then
      echo "==> $proxy serves $CERT"
      return 0
    fi
    if [ "$attempt" -gt 1 ]; then
      echo "==> $CERT is missing from $proxy again, retrying"
    fi
    list=$(jq -r --arg cert "$cert_url" '(.sslCertificates // []) + [$cert] | join(",")' <<<"$current")
    echo "==> Adding $CERT to $proxy"
    lb compute target-https-proxies update "$proxy" --global --ssl-certificates "$list"
    sleep $((attempt * 5))
  done
  echo "::error::Could not add $CERT to $proxy: something else keeps replacing its certificates."
  return 1
}

for proxy in $(jq -r '.[].name' <<<"$proxies"); do
  attach_certificate "$proxy"
done
