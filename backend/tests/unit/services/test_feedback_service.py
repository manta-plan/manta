import base64
import json
from unittest.mock import MagicMock
from uuid import uuid4

import httpx2
import pytest
from fastapi import HTTPException

from manta.routes.v1.requests.feedback_request import FeedbackCategory, FeedbackRequest
from manta.services import feedback_service
from manta.services.errors import BackendError
from manta.services.feedback_service import FeedbackService
from manta.services.results.authenticated_user_result import AuthenticatedUserResult

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"data").decode()
USER = AuthenticatedUserResult(id=1, uuid=uuid4(), username="alice")


def _request(**overrides) -> FeedbackRequest:
    fields = {
        "category": FeedbackCategory.BUG_REPORT,
        "message": "It broke",
        "user_agent": "Firefox",
        "window_size": "1280×720",
        "app_version": "1.2.3",
    } | overrides
    return FeedbackRequest(**fields)


@pytest.fixture
def script(monkeypatch):
    monkeypatch.setenv("FEEDBACK_SCRIPT_URL", "https://script.example/exec")
    monkeypatch.setenv("FEEDBACK_SCRIPT_SECRET", "shh")
    http = MagicMock()
    http.post.return_value.json.return_value = {"ok": True}
    client = MagicMock()
    client.__enter__.return_value = http
    monkeypatch.setattr(feedback_service, "_http_client", lambda: client)
    return http


def _sent(http: MagicMock) -> dict:
    return json.loads(http.post.call_args.kwargs["content"])


def test_forwards_feedback_with_username_and_secret(script) -> None:
    # When
    result = FeedbackService().submit(_request(page="/projects"), USER)

    # Then
    assert script.post.call_args.args == ("https://script.example/exec",)
    sent = _sent(script)
    assert sent["username"] == "alice"
    assert sent["secret"] == "shh"  # noqa: S105
    assert sent["category"] == "bug_report"
    assert sent["page"] == "/projects"
    assert sent["screenshot_id"] == ""
    assert result.screenshot_id is None


def test_gives_the_screenshot_a_uuid(script) -> None:
    # When
    result = FeedbackService().submit(_request(screenshot=PNG), USER)

    # Then
    assert result.screenshot_id is not None
    sent = _sent(script)
    assert sent["screenshot_id"] == str(result.screenshot_id)
    assert sent["screenshot"] == PNG


@pytest.mark.parametrize("screenshot", ["not base64!", base64.b64encode(b"GIF89a").decode()])
def test_rejects_a_screenshot_that_is_not_a_png(script, screenshot) -> None:
    # When / Then
    with pytest.raises(HTTPException) as refused:
        FeedbackService().submit(_request(screenshot=screenshot), USER)
    assert refused.value.status_code == 422
    script.post.assert_not_called()


def test_is_unavailable_without_a_script_url(monkeypatch) -> None:
    # Given
    monkeypatch.delenv("FEEDBACK_SCRIPT_URL", raising=False)
    monkeypatch.setattr(feedback_service, "feedback_script_url", lambda: None)

    # When / Then
    with pytest.raises(BackendError) as refused:
        FeedbackService().submit(_request(), USER)
    assert refused.value.status_code == 503


def test_reports_a_bad_gateway_when_the_script_is_unreachable(script) -> None:
    # Given
    script.post.side_effect = httpx2.ConnectError("down")

    # When / Then
    with pytest.raises(BackendError) as failed:
        FeedbackService().submit(_request(), USER)
    assert failed.value.status_code == 502


def test_reports_a_bad_gateway_when_the_script_rejects_it(script) -> None:
    # Given
    script.post.return_value.json.return_value = {"ok": False, "error": "Bad secret"}

    # When / Then
    with pytest.raises(BackendError) as failed:
        FeedbackService().submit(_request(), USER)
    assert failed.value.status_code == 502
