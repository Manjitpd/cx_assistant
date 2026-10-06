from uuid import UUID

from pydantic import BaseModel, ConfigDict


class BrandRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
