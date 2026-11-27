from enum import StrEnum

from pydantic import BaseModel, Field

# A full-page PNG screenshot is a few MB at most; base64 adds a third.
MAX_SCREENSHOT_BASE64_LENGTH = 8 * 1024 * 1024


class FeedbackCategory(StrEnum):
    BUG_REPORT = "bug_report"
    FEATURE_REQUEST = "feature_request"
    PAIN_POINT = "pain_point"
    QUESTION = "question"


class FeedbackRequest(BaseModel):
    category: FeedbackCategory
    message: str = Field(min_length=1, max_length=2000)
    page: str | None = Field(default=None, max_length=300)
    """The page address, left out when the user opts out of sharing it."""

    screenshot: str | None = Field(default=None, max_length=MAX_SCREENSHOT_BASE64_LENGTH)
    """The Manta page as a base64-encoded PNG, left out when the user opts out."""

    user_agent: str = Field(max_length=300)
    window_size: str = Field(max_length=20)
    app_version: str = Field(max_length=50)
