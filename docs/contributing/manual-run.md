<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Run a playbook through the REST API

This guide shows how to run a playbook on real model data on your own computer, through the REST API.
The web app cannot start a run on real model data, so use these steps to check a change to the backend, the runner or a block from start to end.
You need the local stack set up as [Installation: Full stack](../installation/full-stack.md) describes.

## Start a run and follow it

You need three terminals: one for the Docker stack, one for the backend, and
one for the requests.

1. In the first terminal, bring up the stack (from `docker/`) and leave it
   running so you can see the container logs:

   ```bash
   docker compose --env-file ../backend/.env -f compose-dev-services.yaml up
   ```

   Wait until the logs settle before going on.

2. In the second terminal, start the backend (from `backend/`) and leave it
   running:

   ```bash
   uv run manta
   ```

3. In the third terminal, log in as the dev user and keep the token (from
   `backend/`). This also registers the user with Manta, which every other
   request needs:

   ```bash
   export TOKEN=$(uv run python -c "
   import base64, json, urllib.request

   def post(path, body):
       request = urllib.request.Request(
           f'http://localhost:8000{path}',
           data=json.dumps(body).encode(),
           headers={'Content-Type': 'application/json'},
       )
       return json.load(urllib.request.urlopen(request))

   token = post('/v1/auth/login', {'username': 'manta-admin', 'password': 'manta-admin'})['access_token']
   payload = token.split('.')[1]
   claims = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
   post('/v1/auth/register', {'username': 'manta-admin', 'idp_subject': claims['sub'], 'idp_source': claims['iss']})
   print(token)
   ")
   ```

   The token expires after 5 minutes. Repeat this step when a request returns
   `401`.

4. Create a project:

   ```bash
   curl -s -X POST http://localhost:8000/v1/projects \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"name": "Manual test", "description": "Manual test project"}'
   ```

   Copy the returned `uuid` as `PROJECT_UUID`.

5. Copy a starting datarecord store to S3. The `ac-dc-meshed` store of the
   public `manta-public-test-data` bucket works; its `revisions.json` names the
   revision to start from (`inputs`, `e5f2eacd-ba5c-463c-a663-3017ef904d1d`):

   ```bash
   uv run python -c "
   import boto3
   import httpx2
   from botocore.config import Config
   client = boto3.client(
       's3',
       endpoint_url='http://localhost:8333',
       aws_access_key_id='dev',
       aws_secret_access_key='dev',
       config=Config(s3={'addressing_style': 'path'}),
   )
   prefix = 'ac-dc-meshed/'
   listing = httpx2.get('https://storage.googleapis.com/storage/v1/b/manta-public-test-data/o', params={'prefix': prefix}).json()
   for item in listing['items']:
       key = item['name'].removeprefix(prefix)
       client.put_object(Bucket='manta', Key=f'manual-test/store/{key}', Body=httpx2.get(item['mediaLink']).content)
   "
   ```

6. List the playbooks you can run, then look at one in detail. The detail
   shows each step's block, its settings schema, and the playbook's
   `default_config`:

   ```bash
   curl -s http://localhost:8000/v1/playbooks -H "Authorization: Bearer $TOKEN"
   curl -s http://localhost:8000/v1/playbooks/expand -H "Authorization: Bearer $TOKEN"
   ```

7. Check a config before running it. The answer lists every issue, each naming
   its step and, where there is one, the setting at fault. This config switches
   the playbook to its myopic branch, which needs a `period`
   dimension the playbook's data does not have. The answer has `"valid": false`
   and one `dims` issue on `expansion_myopic`:

   ```bash
   curl -s -X POST http://localhost:8000/v1/playbooks/expand/validate \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"config": {"globals": {"expansion_mode": "myopic"}}}'
   ```

   Sending `{}` instead checks the `default_config`, which has no issues.

8. Create a run from a revision of the uploaded store. Each step writes its
   output as a new revision into that same store. Leaving out `config` runs the
   playbook with its `default_config`. A config with issues is refused with a
   `422` listing the same issues the check above returns:

   ```bash
   curl -s -X POST http://localhost:8000/v1/runs \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"project_uuid": "PROJECT_UUID", "playbook": "expand", "data_record_url": "s3://manta/manual-test/store", "revision_uuid": "e5f2eacd-ba5c-463c-a663-3017ef904d1d"}'
   ```

   Copy the returned `uuid` as `RUN_UUID`.

9. Follow the run. The first request returns the run's overall `status` and the
   `config` it was started with. The second returns each step's `status`:
   `SKIPPED` when the run's config turns the step off, `NOT_STARTED` before it
   begins, and Prefect's own state from then on. The third returns the run's
   logs:

   ```bash
   curl -s http://localhost:8000/v1/runs/RUN_UUID -H "Authorization: Bearer $TOKEN"
   curl -s http://localhost:8000/v1/runs/RUN_UUID/steps -H "Authorization: Bearer $TOKEN"
   curl -s http://localhost:8000/v1/runs/RUN_UUID/logs -H "Authorization: Bearer $TOKEN"
   ```

   Repeat them until the run's `status` is `COMPLETED`.

10. Each step that ran wrote a new revision into the uploaded store, under
    `manual-test/store/revisions/`. `GET /v1/runs/RUN_UUID/outputs` does not list
    them yet: it still lists the run's old output folder, which stays empty.

11. Tear down (from `docker/`, in the third terminal). This also stops the
    stack in the first terminal. Stop the backend in the second terminal with
    `Ctrl+C`:

    ```bash
    docker compose --env-file ../backend/.env -f compose-dev-services.yaml down -v
    ```
