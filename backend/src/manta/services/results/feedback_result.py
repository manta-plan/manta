from uuid import UUID

from pydantic import BaseModel


class SubmitFeedbackResult(BaseModel):
    screenshot_id: UUID | None
    """The ID the screenshot is stored under, None when none was sent."""
