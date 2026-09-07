from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PublicMeta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    filename: str
    content_type: str
    byte_size: int | None
    created_at: datetime
    expires_at: datetime | None
