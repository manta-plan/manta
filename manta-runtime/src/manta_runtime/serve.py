"""Register the run-playbook deployment and execute its runs.

    python -m manta_runtime.serve

Started as a subprocess of the app (see the backend's main.py). Serving is what
lets the API dispatch runs by deployment name without importing any flow
machinery at request time.

TODO(post-MVP): run this as its own long-lived service so in-flight playbook
runs survive an app restart.
"""

from manta_runtime.flows import PLAYBOOK_FLOW_NAME, run_playbook


def main() -> None:
    run_playbook.serve(name=PLAYBOOK_FLOW_NAME)


if __name__ == "__main__":
    main()
