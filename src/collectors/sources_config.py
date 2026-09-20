from pathlib import Path

import yaml
from pydantic import BaseModel


class SourceConfig(BaseModel):
    id: str
    name: str
    type: str
    url: str
    language: str
    source_type: str
    poll_interval_minutes: int
    active: bool = True


def load_sources_config(path: str | Path) -> list[SourceConfig]:
    data = yaml.safe_load(Path(path).read_text())
    return [SourceConfig(**entry) for entry in data["sources"]]
