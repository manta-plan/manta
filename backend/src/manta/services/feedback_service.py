import base64
import binascii
import json
import logging
from uuid import UUID, uuid4

import httpx2
from fastapi import HTTPException, status

from manta.config.feedback_config import feedback_script_secret, feedback_script_url
from manta.routes.v1.requests.feedback_request import FeedbackRequest
from manta.services.errors import BackendError
from manta.services.results.authenticated_user_result import AuthenticatedUserResult
from manta.services.results.feedback_result import SubmitFeedbackResult

logger = logging.getLogger(__name__)

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_PNG_IHDR = b"\x00\x00\x00\x0dIHDR"
_PNG_IEND = b"\x00\x00\x00\x00IEND\xaeB`\x82"


def _http_client() -> httpx2.Client:
    # Apps Script answers a POST with a redirect to the result, so follow it.
    return httpx2.Client(timeout=30, follow_redirects=True)


class FeedbackService:
    """Forwards feedback to the Apps Script web app that appends it to OET's Google
    Sheet. The backend holds only the means to add feedback, never to read or delete
    it, so stored feedback survives a compromised or wiped app."""

    def submit(
        self, request: FeedbackRequest, user: AuthenticatedUserResult
    ) -> SubmitFeedbackResult:
        url = feedback_script_url()
        if url is None:
            raise BackendError(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Feedback is not configured on this server",
            )

        # Decode before forwarding so a bad screenshot is the caller's error.
        screenshot_id = self._check_screenshot(request.screenshot)

        payload = {
            "secret": feedback_script_secret(),
            "category": request.category.value,
            "message": request.message,
            "page": request.page or "",
            "screenshot_id": str(screenshot_id) if screenshot_id else "",
            "screenshot": request.screenshot or "",
            "user_agent": request.user_agent,
            "window_size": request.window_size,
            "app_version": request.app_version,
            "username": user.username,
        }
        try:
            with _http_client() as http:
                response = http.post(
                    url,
                    # text/plain keeps this a "simple" request, which Apps Script accepts.
                    content=json.dumps(payload),
                    headers={"Content-Type": "text/plain;charset=utf-8"},
                )
                response.raise_for_status()
                result = response.json()
        except httpx2.HTTPError, ValueError:
            logger.exception("Could not forward feedback to the Apps Script")
            raise BackendError(
                status_code=status.HTTP_502_BAD_GATEWAY, detail="Could not store the feedback"
            ) from None
        if not isinstance(result, dict) or not result.get("ok"):
            logger.error("The Apps Script rejected the feedback: %s", result)
            raise BackendError(
                status_code=status.HTTP_502_BAD_GATEWAY, detail="Could not store the feedback"
            )
        return SubmitFeedbackResult(screenshot_id=screenshot_id)

    def _check_screenshot(self, screenshot: str | None) -> UUID | None:
        if not screenshot:
            return None
        try:
            data = base64.b64decode(screenshot, validate=True)
        except binascii.Error, ValueError:
            data = b""
        # A complete PNG is the signature, an IHDR chunk first, and an IEND chunk last.
        if not (
            data.startswith(_PNG_SIGNATURE + _PNG_IHDR)
            and data.endswith(_PNG_IEND)
            and len(data) >= len(_PNG_SIGNATURE + _PNG_IHDR) + 13 + 4 + len(_PNG_IEND)
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="The screenshot must be a base64-encoded PNG",
            )
        return uuid4()
