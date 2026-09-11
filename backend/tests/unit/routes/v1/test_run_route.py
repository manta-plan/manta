from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from manta.routes.v1.run_route import router
from manta.services.results.run_result import GetRunSummaryResult, ListRunsResult
from manta.services.run_service import RunService


class _StubRunService:
    def __init__(self) -> None:
        self.list_runs_call = None

    def list_runs(self, **kwargs) -> ListRunsResult:
        self.list_runs_call = kwargs
        return ListRunsResult(
            items=[],
            total=0,
            limit=kwargs["limit"],
            offset=kwargs["offset"],
            summary=GetRunSummaryResult(total=0, statuses={}),
        )


def test_list_runs_binds_query_params_to_request_model() -> None:
    # Given
    project_uuid = uuid4()
    service = _StubRunService()
    app = FastAPI()
    app.dependency_overrides[RunService] = lambda: service
    app.include_router(router)
    client = TestClient(app)

    # When
    response = client.get(
        "/runs",
        params=[
            ("project_uuid", str(project_uuid)),
            ("limit", "25"),
            ("offset", "50"),
            ("statuses", "RUNNING"),
            ("statuses", "COMPLETED"),
        ],
    )

    # Then
    assert response.status_code == 200
    assert service.list_runs_call == {
        "project_uuid": project_uuid,
        "limit": 25,
        "offset": 50,
        "status_filters": ["RUNNING", "COMPLETED"],
    }
