from typing import Any

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    detail: str
    errors: list[dict[str, Any]] | None = None

    def as_body(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)
