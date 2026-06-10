from __future__ import annotations

from pydantic import BaseModel, Field


class CommandRequest(BaseModel):
    command: str = Field(..., min_length=1, max_length=800)


class CommandResponse(BaseModel):
    ok: bool
    command: str
    status: str
    summary: str = ""
    output_files: list[str] = []
    latest_status: dict = {}
    stdout: str = ""
    stderr: str = ""
    error: str = ""


class FileEntry(BaseModel):
    name: str
    path: str
    suffix: str
    size: int
    size_text: str
    modified_at: str
    category: str


class HealthResponse(BaseModel):
    ok: bool
    service: str
