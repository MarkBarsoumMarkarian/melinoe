from pathlib import Path

import pytest

from melinoe.core.models import ProjectManifest


@pytest.fixture()
def demo_path() -> Path:
    return Path(__file__).parents[1] / "examples" / "multimodal_demo" / "project.json"


@pytest.fixture()
def demo_manifest(demo_path: Path) -> ProjectManifest:
    return ProjectManifest.from_json_file(demo_path)
