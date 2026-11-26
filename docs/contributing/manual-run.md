<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Run a playbook through the REST API

This guide shows how to run a playbook on real model data on your own computer, through the REST API.
Use these steps to check a change to the backend, the runner, or a block from start to end, without the web app.
You need the local stack set up as [Installation: Full stack](../installation/full-stack.md) describes.

## Start a run and follow it

You need three terminals: one for the Docker stack, one for the backend, and
one for the requests.

1. In the first terminal, bring up the stack (from `docker/`) and leave it
   running so you can see the container logs:

   ```bash
   docker compose --env-file ../backend/.env -f compose-dev-services.yaml up
   ```

   Wait until the logs settle before going on. Two dashboards are then up, for
   following along in later steps:

   - Prefect, at [localhost:4200](http://localhost:4200): each run, and the
     flow run of each of its steps, with their logs.
   - SeaweedFS, at [localhost:23646](http://localhost:23646): the `manta`
     bucket's files, such as the example data and the revisions runs write.

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

4. List the playbooks you can run, then look at one in detail. The detail
   shows each step's block, its settings schema, and the playbook's
   `default_config`:

   ```bash
   curl -s http://localhost:8000/v1/playbooks -H "Authorization: Bearer $TOKEN"
   curl -s http://localhost:8000/v1/playbooks/expand -H "Authorization: Bearer $TOKEN"
   ```

5. Check a config before running it. The answer lists every issue, each naming
   its step and, where there is one, the setting at fault. This config switches
   the playbook to its myopic branch, which needs a `period`
   dimension the playbook's data does not have. The answer has `"valid": false`
   and one `dims` issue on `expansion_myopic`:

   ```bash
   curl -s -X POST http://localhost:8000/v1/playbooks/expand/validate \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"config": {"inputs": {"expansion_mode": "myopic"}}}'
   ```

   Sending `{}` instead checks the `default_config`, which has no issues.

6. Create a run in manta-admin's example project
   (`33b9abe3-2f25-4824-89e2-5a3d93671b6c`, see [Example data](backend.md#example-data)),
   from the `inputs` revision of its `BEL-pre-aggregated` store. Each step
   writes its output as a new revision into that same store. Leaving out `playbook.config`
   runs the playbook with its `default_config`. A config with issues is refused with a
   `422` listing the same issues the check above returns:

   ```bash
   curl -s -X POST http://localhost:8000/v1/runs \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"project_uuid": "33b9abe3-2f25-4824-89e2-5a3d93671b6c", "playbook": {"name": "expand"}, "data_record": {"store_url": "s3://manta/33b9abe3-2f25-4824-89e2-5a3d93671b6c/BEL-pre-aggregated", "revision_uuid": "8ff7a95a-8aed-42a3-9acb-a2e36906685f"}}'
   ```

   Copy the returned `uuid` as `RUN_UUID`.

7. Follow the run. The first request returns the run's overall `status`, and the
   `config` and `data_record` it was started with. The `config` is resolved: it has the
   default of each input that the run left out, and each step has its `with` merged
   in. A step that runs has every expression evaluated, and a step that does not run has
   its `with` as written. A run cannot set what `with` sets, so for a playbook with
   settings in `with`, the backend refuses this `config` for a new run. The second
   returns each step's `status`:
   `SKIPPED` when the run's config turns the step off, `NOT_STARTED` before it
   begins, and Prefect's own state from then on, plus its `output` record once
   it has completed, or the `message` with its error if it failed. The third returns the run's
   logs:

   ```bash
   curl -s http://localhost:8000/v1/runs/RUN_UUID -H "Authorization: Bearer $TOKEN"
   curl -s http://localhost:8000/v1/runs/RUN_UUID/steps -H "Authorization: Bearer $TOKEN"
   curl -s http://localhost:8000/v1/runs/RUN_UUID/logs -H "Authorization: Bearer $TOKEN"
   ```

   Repeat them until the run's `status` is `COMPLETED`. The Prefect dashboard
   shows the same run as it goes, as a `run-playbook` flow run with a `run-block`
   flow run for each step.

8. Each step that ran wrote a new revision into the project's store, under
   `33b9abe3-2f25-4824-89e2-5a3d93671b6c/BEL-pre-aggregated/layers/`, which
   you can browse in the SeaweedFS dashboard. The steps response names it as the
   step's `output` (`store_url` and `revision_uuid`). The last step that ran
   holds the run's final record.

9. Tear down (from `docker/`, in the third terminal). This also stops the
   stack in the first terminal. Stop the backend in the second terminal with
   `Ctrl+C`:

   ```bash
   docker compose --env-file ../backend/.env -f compose-dev-services.yaml down
   ```

   The stack's volumes keep the database, the stored files, and the
   revisions this run wrote, so the next `up` starts where this one ended.

!!! warning "Reset the stack"
    To start again from empty volumes, add `-v`.
    This deletes every project, user, run, and stored file of the local stack, and the backend downloads the example data again at its next start.

    ```bash
    docker compose --env-file ../backend/.env -f compose-dev-services.yaml down -v
    ```
