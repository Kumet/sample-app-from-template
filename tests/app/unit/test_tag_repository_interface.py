import json
import subprocess
import sys
from pathlib import Path


def test_importing_tag_repository_does_not_load_concrete_infrastructure() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    script = """
import json
import sys

import project_board.repositories.tag_repository

watched_modules = (
    "sqlalchemy",
    "project_board.repositories.sqlalchemy_project_repository",
    "project_board.repositories.sqlalchemy_task_repository",
    "project_board.repositories.sqlalchemy_tag_repository",
    "project_board.infrastructure.database",
    "project_board.infrastructure.models",
)
print(json.dumps([name for name in watched_modules if name in sys.modules]))
"""

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        cwd=repository_root,
        env={"PYTHONPATH": str(repository_root / "src")},
        text=True,
    )

    assert json.loads(completed.stdout) == []


def test_importing_repository_package_with_tag_protocol_is_isolated() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    script = """
import json
import sys

from project_board.repositories import TagRepository

watched_modules = (
    "sqlalchemy",
    "project_board.repositories.sqlalchemy_tag_repository",
    "project_board.infrastructure.database",
    "project_board.infrastructure.models",
)
print(json.dumps({
    "protocol": TagRepository.__name__,
    "loaded": [name for name in watched_modules if name in sys.modules],
}))
"""

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        cwd=repository_root,
        env={"PYTHONPATH": str(repository_root / "src")},
        text=True,
    )

    assert json.loads(completed.stdout) == {
        "protocol": "TagRepository",
        "loaded": [],
    }
