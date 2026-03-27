from __future__ import annotations

from pydantic import BaseModel


class DomainProfile(BaseModel):
    id: str
    name: str
    description: str
    framework: str
    role_labels: dict[str, str]
    gap_categories: list[str]
    signal_types: list[str]
    priority_rules: list[str]
    system_prompt_fragment: str
    opening_message: str = ""
