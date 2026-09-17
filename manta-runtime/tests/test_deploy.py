"""What the deployer stamps into job containers, checked without a Prefect server."""

from manta_runtime import deploy


def test_job_containers_get_the_addresses_and_credentials_they_need(monkeypatch):
    monkeypatch.setenv("PREFECT_API_URL", "http://prefect-server:4200/api")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "dev")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "dev")
    monkeypatch.setenv("AWS_ENDPOINT_URL", "http://seaweedfs:8333")
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)

    env = deploy.job_environment()

    assert env == {
        "PREFECT_API_URL": "http://prefect-server:4200/api",
        "AWS_ACCESS_KEY_ID": "dev",
        "AWS_SECRET_ACCESS_KEY": "dev",
        "AWS_ENDPOINT_URL": "http://seaweedfs:8333",
    }


def test_nothing_unrelated_leaks_into_job_containers(monkeypatch):
    monkeypatch.setenv("PREFECT_API_URL", "http://prefect-server:4200/api")
    monkeypatch.setenv("POSTGRES_PASSWORD", "must-not-leak")

    assert "POSTGRES_PASSWORD" not in deploy.job_environment()
