# Deployment

> [!IMPORTANT]
> This page is for the Manta core team. It covers the test instances we run on
> our own GCP projects (demo, pen-testing, MVP) and is not a supported way to
> run Manta in production. To try Manta yourself, see
> [Running Manta locally](../README.md#running-manta-locally).

One GitHub Action, [Deploy](../.github/workflows/deploy.yml), deploys any
branch to a VM on GCP and serves it at `https://<vm_name>.manta-plan.org`. It
creates the VM if it doesn't exist yet, and posts the outcome to Discord.

The Google Cloud steps on this page are written for the
[Google Cloud console](https://console.cloud.google.com). Before each one,
select the right project in the project picker at the top of the page. The few
commands that remain have no console equivalent.

## Deploying

Go to **Actions > Deploy > Run workflow** and fill in the form:

| Input         | Meaning                                                                    |
| ------------- | -------------------------------------------------------------------------- |
| `vm_name`     | The VM, and the subdomain: `demo` is served at `demo.manta-plan.org`       |
| `gcp_project` | The GCP project that hosts the VM (see [Per hosting project](#per-hosting-project)) |
| `ref`         | Branch, tag or SHA to deploy (default `main`)                              |
| `reset_data`  | Delete the database, stored files and users first                          |
| `dry_run`     | Change nothing: only check the setup and list any missing permissions      |

Or from a terminal:

```bash
gh workflow run deploy.yml -f vm_name=demo -f gcp_project=<project> -f ref=main
```

Things to know:

- **New or existing VM.** If a VM called `vm_name` exists in the project (in
  the zone set by `GCP_ZONE`), it is redeployed, and started first if it was
  stopped. Otherwise it is created. `vm_name` is 1 to 30 lowercase letters,
  digits and hyphens, starting with a letter.
- **Two refs.** **Use workflow from**, at the top of the form, picks the branch
  the workflow and the scripts under [`scripts/deploy/`](../scripts/deploy)
  come from. `ref` is the commit that ends up running on the VM. Any commit
  that has `docker/compose-dev-fullstack.yaml` can be deployed.
- **Inputs and variables.** The inputs change per run. What is the same for
  every run (the load balancer, the zone, the VM size, how to sign in to GCP)
  comes from repository variables, see [GitHub](#github).
- **Duration.** A first deployment to a new VM is the slow one, because it
  builds every image; later ones reuse the build cache. The instance is down
  only while the containers restart, not while the images build.
- **The form is missing.** GitHub only shows **Run workflow** for workflows
  whose file is on the repository's default branch.

When the run is green, open `https://<vm_name>.manta-plan.org`. You land on
the login page: sign in with `manta-admin` / `manta-admin`.
`https://manta-plan.org` without a subdomain is the public website, a
different thing behind the same load balancer.

> [!WARNING]
> An instance runs with the credentials committed in `backend/.env` and
> `docker/conf/manta-realm.json`, including the `manta-admin` / `manta-admin`
> login, and anyone can reach it. Don't put anything on one that matters.

## How a request reaches an instance

What happens when someone opens `https://demo.manta-plan.org`:

1. **DNS.** One wildcard record, `*.manta-plan.org`, sends every subdomain
   that has no record of its own to the same address: the load balancer,
   `34.54.90.4`. DNS knows nothing about VMs.
2. **Certificate.** The load balancer answers over HTTPS, and has to present a
   certificate that is valid for `demo.manta-plan.org`.
3. **Host rule.** The load balancer reads the hostname of the request and
   looks it up in its routing table, the URL map `manta-website`. The rule for
   `demo.manta-plan.org` points at the backend service `manta-demo-backend`.
   A hostname without a rule gets a 404.
4. **Backend service and endpoint group.** `manta-demo-backend` forwards the
   request, as plain HTTP, to the address held in `manta-demo-neg`: the VM's
   static IP, port 80.
5. **VM.** The firewall lets port 80 in from the load balancer only. The
   frontend container (Caddy) answers: it serves the app and passes `/v1/*`
   to the backend container.

Steps 1 and 2 are set up once and serve every instance
([DNS](#dns), [TLS certificate](#tls-certificate)). The action creates steps 3
to 5 for each VM. The load balancer itself already exists: it also serves the
website.

| Term                         | What it is here                                                                                                                                                         |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Load balancer                | Google's front door for `manta-plan.org`: one IP, HTTPS, and routing by hostname. Listed under **Network services > Load balancing** as `manta-website`                  |
| URL map                      | The load balancer's routing table, from hostname to backend service. The console shows its name as the load balancer's name, which is why `GCP_URL_MAP` is `manta-website` |
| Host rule                    | One row of the URL map: `<vm_name>.manta-plan.org` goes to `manta-<vm_name>-backend`                                                                                     |
| Backend service              | A load balancer setting that means "a place to send traffic". Not Manta's backend API. Its description records which project and VM own the subdomain                    |
| Network endpoint group (NEG) | Holds the actual destination: the VM's IP and port 80                                                                                                                   |
| Firewall rules               | `manta-allow-ssh` (port 22, from anywhere) and `manta-allow-lb` (port 80, from the load balancer only). They apply to VMs with the network tag `manta`                   |
| Service account              | `github-manta-deployer`: the identity the action acts as in GCP. It can do what its roles allow and nothing else                                                        |
| Workload Identity Federation | Lets a GitHub Actions run prove which repository it belongs to, and act as the service account without a stored key                                                     |
| OS Login                     | SSH access to a VM granted by an IAM role, instead of keys copied onto the VM                                                                                           |

## What a deployment does

Each step skips whatever already exists, so re-running is always safe.

1. **Preflight** ([`gcp-preflight.sh`](../scripts/deploy/gcp-preflight.sh)):
   checks the inputs, resolves `ref` to a commit, authenticates to GCP and
   lists any permission the deploy service account is missing. With `dry_run`
   the run stops here.
2. **Project and VM** ([`gcp-ensure-vm.sh`](../scripts/deploy/gcp-ensure-vm.sh)):
   enables the Compute Engine API if it is off, creates the two firewall rules,
   and creates the VM with a static IP, or starts it if it was stopped.
3. **VM setup** ([`vm-setup.sh`](../scripts/deploy/vm-setup.sh), on the VM):
   installs Docker and git. Nothing else is needed, since the whole stack runs
   in containers.
4. **Load balancer** ([`gcp-register-lb.sh`](../scripts/deploy/gcp-register-lb.sh)):
   in the load balancer's project, creates the endpoint group pointing at the
   VM's IP, the backend service on top of it, and the host rule for the
   subdomain. Fails if the subdomain already belongs to another VM. A new host
   rule takes a few minutes to reach all of Google's front ends, which is why
   this runs before the images build.
5. **Deploy** ([`vm-deploy.sh`](../scripts/deploy/vm-deploy.sh), on the VM):
   checks the commit out into `/opt/manta`, builds the images, restarts the
   stack from `docker/compose-dev-fullstack.yaml` with the frontend on port 80,
   and waits for `/v1/health`.
6. **Public check**: waits up to ten minutes for
   `https://<vm_name>.manta-plan.org/v1/health`. This is the step that fails
   when the DNS record or the certificate is missing.
7. **Discord**: posts the URL, VM, project, commit, user and result.

## One-time setup

This is done once, not per deployment. It is written down so the setup can be
checked, repaired or repeated. Everything is in `paros-491610`, the project of
the `manta-website` load balancer (shown as "manta" in the project picker).

Granting roles needs a project Owner. For everyone else, **Grant access** on
the IAM page is greyed out.

### APIs

Under **APIs & Services > Library**, search for each of these and click
**Enable**:

| API                                 | Needed for                                                                                   |
| ----------------------------------- | -------------------------------------------------------------------------------------------- |
| IAM Service Account Credentials API | Signing in from GitHub                                                                       |
| Security Token Service API          | Signing in from GitHub                                                                       |
| Compute Engine API                  | The load balancer and the VMs                                                                |
| Certificate Manager API             | The wildcard certificate                                                                     |
| Cloud Resource Manager API          | The **Check permissions** step. Without it the step cannot check anything and only warns     |

### Deploy service account and Workload Identity Federation

The action signs in to GCP as the service account `github-manta-deployer`.
There is no key to store or rotate: GitHub hands each run a short-lived token
that names the repository, and GCP accepts it if the repository is ours.

1. **Service account.** **IAM & Admin > Service Accounts > Create service
   account**, name `github-manta-deployer`. Skip the optional steps.
2. **Pool and provider.** **IAM & Admin > Workload Identity Federation >
   Create pool**:
   - Pool name: `gh-action-pool`
   - Provider: **OpenID Connect (OIDC)**, name `github`
   - Issuer URL: `https://token.actions.githubusercontent.com`
   - Audiences: **Default audience**
   - Attribute mapping, two rows:

     | Google attribute       | OIDC claim             |
     | ---------------------- | ---------------------- |
     | `google.subject`       | `assertion.sub`        |
     | `attribute.repository` | `assertion.repository` |

   - Attribute conditions: `assertion.repository == 'manta-plan/manta'`
3. **Let the repository act as the service account.** On the page of
   `gh-action-pool`, click **Grant access > Grant access using service account
   impersonation**. Select `github-manta-deployer`, choose the attribute name
   `repository` and enter the value `manta-plan/manta`. Save, and dismiss the
   offer to download a configuration file.
4. **Let it add instances to the load balancer.** **IAM & Admin > IAM > Grant
   access**. New principal:
   `github-manta-deployer@paros-491610.iam.gserviceaccount.com`. Role:
   **Compute Load Balancer Admin**.

The repository is checked twice: the condition in step 2 decides which
repositories may sign in at all, and step 3 decides which of those may act as
this service account. Both have to name the repository the workflow runs in.

Grant access on the `repository` attribute as above, not on the token's
subject. The deploy job runs in a GitHub environment named after the VM, which
changes the subject to `repo:manta-plan/manta:environment:<vm_name>`, so access
tied to a branch subject would reject it.

### DNS

`manta-plan.org` is hosted on Cloud DNS, in the zone `manta-plan-squarespace`.
One wildcard record makes every instance's name resolve:

1. **Network services > Cloud DNS**, click `manta-plan-squarespace`.
2. Click **Add standard**.
3. DNS name `*`, resource record type **A**, IPv4 address `34.54.90.4` (the
   same address as the `manta-plan.org` record), then **Create**.

`*` stands for any name that has no record of its own. Names with their own
record, like `www`, keep using it, so the wildcard changes nothing for them.
It also does not decide which VM answers: every name gets the same address,
and the load balancer picks the VM from the hostname.

### TLS certificate

The load balancer needs a certificate that is valid for the name in the
address bar. Without the wildcard certificate it has one certificate per
hostname (`manta-plan.org` with `www`, `baby`, `quack`), so a new instance
shows a certificate warning in the browser and fails the **Public check**.

One wildcard certificate for `manta-plan.org` and `*.manta-plan.org` fixes
this for every current and future instance. Google issues and renews it for
free, but only through Certificate Manager, and only after a DNS record proves
that we control the domain.

Do this together with whoever owns the website: the last step changes which
certificate every `manta-plan.org` site presents.

1. **Request the certificate.** **Security > Certificate Manager >
   Certificates > Add Certificate**:
   - Certificate name: `manta-plan-org`
   - Location: **Global**, scope: **Default**
   - Certificate type: **Create Google-managed certificate**
   - Certificate Authority type: **Public**
   - Domain names: `manta-plan.org, *.manta-plan.org`
   - Authorization type: **DNS authorization**. Click **Create missing DNS
     authorization**, name it `manta-plan-org`, and click **Create DNS
     authorization**.
   - **Create**
2. **Prove control of the domain.** The DNS authorization comes with a CNAME
   record: its name is `_acme-challenge.manta-plan.org.` and its value ends
   in `.authorize.certificatemanager.goog.`. Look for the value in the
   certificate's details. Google only documents a command for reading it, so
   if the console does not show it, run this in Cloud Shell (the terminal icon
   at the top right of the console):

   ```bash
   gcloud certificate-manager dns-authorizations describe manta-plan-org \
     --project paros-491610 --format='value(dnsResourceRecord.data)'
   ```

   Then add the record in **Network services > Cloud DNS >
   `manta-plan-squarespace` > Add standard**: DNS name `_acme-challenge`,
   resource record type **CNAME**, canonical name: the value. Keep this record
   for good: Google checks it again at every renewal.
3. **Wait** until the certificate's status on the **Certificates** tab is
   **Active**. This usually takes minutes. After a few hours without it, the
   CNAME record is wrong.
4. **Create the certificate map.** On the **Certificate maps** tab, click
   **Create certificate map**, name `manta-website`. Add two entries with
   **Add map entry**, both using the certificate `manta-plan-org`, and leave
   **Primary entry** unticked:

   | Map entry name | Hostname           |
   | -------------- | ------------------ |
   | `apex`         | `manta-plan.org`   |
   | `wildcard`     | `*.manta-plan.org` |

   Nothing live has changed so far.
5. **Attach the map to the load balancer.** Only once the certificate is
   **Active**. **Network services > Load balancing**, click `manta-website`,
   then **Edit > Frontend configuration**, and open the HTTPS frontend (port
   443). Write down the certificates it lists now. Under **Choose certificate
   repository** select **Use certificate map**, select `manta-website`, then
   **Done** and **Update**.
6. **Check** after a few minutes that `manta-plan.org`, `www`, `baby`, `quack`
   and one instance all open without a warning.

From step 5 on, the map decides which certificate is presented, and the
certificates attached to the frontend directly are ignored. That is why the
map has an entry for `manta-plan.org` itself: a wildcard covers `www` and
every other subdomain, but not the bare domain. It covers one level only, so
`a.b.manta-plan.org` is not covered either.

**To undo step 5**, edit the same frontend again, switch **Choose certificate
repository** back to the classic certificates, and select the ones you wrote
down. If the frontend still lists them next to the map, detaching the map from
Cloud Shell does the same:

```bash
gcloud compute target-https-proxies list --project paros-491610   # find the proxy
gcloud compute target-https-proxies update <proxy> --project paros-491610 \
  --global --clear-certificate-map
```

**A certificate for one instance only.** Where the wildcard certificate is not
in place, a single instance can get its own, with no change for the other
sites. **Security > Certificate Manager > Classic Certificates > Create SSL
certificate**, choose **Create Google-managed certificate**, and enter the
domain `<vm_name>.manta-plan.org`. Then edit the HTTPS frontend as in step 5,
but add the new certificate under **Additional certificates** and leave the
existing ones selected. Issuing takes up to an hour, and a frontend takes 15
certificates at most. This has no effect once a certificate map is attached.

### GitHub

Under **Settings > Secrets and variables > Actions > Variables**, add these
repository variables. They are settings, not secrets: none of them grants
access by itself.

| Variable              | Value                                                                                     | Where to find it                                                                                                          |
| --------------------- | ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `GCP_WIF_PROVIDER`    | `projects/314555626448/locations/global/workloadIdentityPools/gh-action-pool/providers/github` | **IAM & Admin > Workload Identity Federation > `gh-action-pool`**, edit `github`: the default audience, without `https://iam.googleapis.com/` |
| `GCP_SERVICE_ACCOUNT` | `github-manta-deployer@paros-491610.iam.gserviceaccount.com`                              | **IAM & Admin > Service Accounts**, the Email column                                                                      |
| `GCP_LB_PROJECT`      | `paros-491610`                                                                            | The ID column in the project picker                                                                                       |
| `GCP_URL_MAP`         | `manta-website`                                                                           | **Network services > Load balancing**, the Name column                                                                    |
| `GCP_ZONE`            | Where VMs are created, for example `europe-north2-a`                                      | Our choice                                                                                                                |
| `GCP_MACHINE_TYPE`    | The VM size, for example `e2-standard-4` (4 vCPUs, 16 GB)                                 | Our choice                                                                                                                |

On the **Secrets** tab, add the repository secret `DISCORD_WEBHOOK_URL`: in
Discord, **Edit channel > Integrations > Webhooks > New webhook > Copy webhook
URL**. Without it the deployment still works and only the notification is
skipped.

## Per hosting project

Any number of projects can host instances; `paros-491610` itself can be one.
For each, create the project and link billing. Then a project Owner does two
things in that project:

1. **APIs & Services > Library**: enable the **Compute Engine API**.
2. **IAM & Admin > IAM > Grant access**. New principal:
   `github-manta-deployer@paros-491610.iam.gserviceaccount.com`. Add these
   four roles with **Add another role**:

| Role in the console         | Role ID                          | Used for                                              |
| --------------------------- | -------------------------------- | ----------------------------------------------------- |
| Compute Instance Admin (v1) | `roles/compute.instanceAdmin.v1` | Creating and starting the VM                          |
| Compute Public IP Admin     | `roles/compute.publicIpAdmin`    | Reserving its static IP                               |
| Compute Security Admin      | `roles/compute.securityAdmin`    | The two firewall rules                                |
| Compute OS Admin Login      | `roles/compute.osAdminLogin`     | SSH into the VM as an administrator                   |

The administrator login is needed because the action installs Docker on the
VM and runs it as root. To have the action enable the Compute Engine API
itself, skip step 1 and add the role **Service Usage Admin** instead.

The IAM page only lists principals that hold at least one role, so the service
account shows up there after this step, not before.

Then run the action with `dry_run` ticked: the **Check permissions** step
lists anything that is still missing, in this project and in the load
balancer's.

## Working on an instance

Under **Compute Engine > VM instances**, click **SSH** next to the VM. It opens
a terminal on the VM in the browser. There:

```bash
cd /opt/manta
sudo git log -1                      # what is deployed
sudo docker compose -p manta ps      # state of the stack
sudo docker compose -p manta logs -f backend
```

The VM publishes Postgres, Keycloak, Prefect and the object store on its own
ports, all with default credentials. The firewall keeps them unreachable from
outside: don't open them. To look at one, forward its port over SSH instead.
This needs the gcloud CLI on your machine, for example for Prefect on
`localhost:4200`:

```bash
gcloud compute ssh <vm_name> --project <project> --zone <zone> -- -L 4200:localhost:4200
```

A running VM is billed by the hour. Select it under **Compute Engine > VM
instances** and click **Stop** to save most of its cost. The next deployment
starts it again, with its data and its address intact.

## Removing an instance

There is no action for this yet. Remove the routing first, then the VM.

In the load balancer's project, `paros-491610`:

1. **Network services > Load balancing**, click `manta-website`, then **Edit >
   Routing rules**. Delete the rule for `<vm_name>.manta-plan.org` (it points
   at `manta-<vm_name>-backend`), then **Update**. Leave the other rules as
   they are: they serve the website and the other instances.
2. On the **Backends** tab of **Load balancing**, delete
   `manta-<vm_name>-backend`. This is refused while a rule still points at it.
3. **Compute Engine > Network endpoint groups**: delete `manta-<vm_name>-neg`.

In the hosting project:

4. **Compute Engine > VM instances**: delete the VM. Its disk and data go
   with it.
5. **VPC network > IP addresses**: release `<vm_name>-ip`. A reserved address
   without a VM keeps costing money.

On GitHub, delete the `<vm_name>` environment under **Settings >
Environments**.

The firewall rules `manta-allow-ssh` and `manta-allow-lb` are shared by every
instance in the project, so leave them.

## Troubleshooting

The messages below are what the run log shows.

**Preflight**

- **`Repository variable ... is not set`**: add the variable, see
  [GitHub](#github). Variables belong to one repository, so a fork starts
  with none.
- **`The given credential is rejected by the attribute condition`**: the
  workflow ran in a repository that the identity provider does not accept,
  typically a fork. See [Running from a fork](#running-from-a-fork).
- **Sign-in passes the condition but is denied
  `iam.serviceAccounts.getAccessToken`**: the repository may sign in, but has
  not been granted access to the service account (step 3 of
  [the setup](#deploy-service-account-and-workload-identity-federation)).
- **Warning `Could not check the permissions in ...`**: the Cloud Resource
  Manager API is off in the service account's project, `paros-491610` (see
  [APIs](#apis)). The run continues, but missing permissions are then only
  found one at a time, by the step that needs them.
- **`MISSING compute...`**: a role is missing. The first block of the list is
  about the hosting project ([roles](#per-hosting-project)), the second about
  the load balancer's project (Compute Load Balancer Admin).

**Deploy**

- **`PERMISSION_DENIED` with `serviceusage.services.enable`**: the Compute
  Engine API is off in the hosting project and the service account may not
  switch it on. Enable it by hand, see [Per hosting project](#per-hosting-project).
- **Any other `PERMISSION_DENIED` or `Required '...' permission`**: a role is
  missing in the project named in the message. Role changes take a minute or
  two to apply.
- **`does not accept SSH yet`, `Connection refused`**: normal for the first
  minute of a new VM. The step retries for five minutes.
- **`... is already used by another instance`** or **`already routed by path
  matcher`**: the subdomain belongs to a VM in another project, or to a rule
  somebody made by hand. Pick another `vm_name`.

**Public check**

Each attempt prints `Got <code> from https://...`, followed by the reason when
there was no answer at all.

- **`Got 000 ... Could not resolve host`**: the wildcard [DNS](#dns) record
  is missing.
- **`Got 000 ... SSL: no alternative certificate subject name matches`**: no
  certificate covers this subdomain, see [TLS certificate](#tls-certificate).
  The instance itself works: the browser opens it after the warning.
- **`Got 404`**: the new host rule has not reached every front end yet. This
  clears up within a few minutes.
- **`Got 502` or `503`**: the load balancer cannot reach the VM. Check that the
  VM is running, and that the firewall rule `manta-allow-lb` exists in the
  hosting project (**VPC network > Firewall**).

When this step fails, the instance is already deployed and healthy on the VM.
After fixing the cause, run the action again with the same inputs: it reuses
the VM and only repeats what is needed.

**Other**

- **The browser shows a login page**: that is Manta. Sign in with
  `manta-admin` / `manta-admin`.
- **Nothing arrives in Discord**: the secret `DISCORD_WEBHOOK_URL` is not set.
  The **Notify Discord** job says so in a warning.

### Running from a fork

The action can be tried out in a fork before it changes anything upstream:

1. Merge the workflow into the fork's default branch, and add the six
   variables to the fork.
2. In `paros-491610`, extend the provider's attribute condition, for example
   `assertion.repository == 'manta-plan/manta' || assertion.repository == '<user>/manta'`,
   and repeat **Grant access** with the value `<user>/manta`.
3. Deploy a `ref` that exists in the fork: the VM clones the repository the
   workflow runs in.

Undo step 2 afterwards. Until then, every workflow in that fork can act as the
deploy service account.

## Known limits

- Anyone with write access to the repository can run the action, from any
  branch, with the service account's rights. Restricting that (required
  reviewers on the environments, a branch condition on the identity provider)
  is for when it matters.
- Traffic between the load balancer and the VM is plain HTTP over the VM's
  public IP.
- Secrets are the committed defaults (see the warning above).
