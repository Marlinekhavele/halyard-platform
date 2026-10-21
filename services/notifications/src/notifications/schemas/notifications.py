"""API request and response models: notifications."""

import datetime

import pydantic


class NotificationOut(pydantic.BaseModel):
    """An in-app notification."""

    model_config = pydantic.ConfigDict(from_attributes=True)

    id: str
    audience: str
    company_id: str | None
    kind: str
    title: str
    body: str
    link: str | None
    event_type: str
    email_status: str
    created_at: datetime.datetime
    read_at: datetime.datetime | None


class StatusOut(pydantic.BaseModel):
    """Acknowledgement of an action."""

    status: str = "ok"
