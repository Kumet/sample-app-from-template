from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[3]
README = PROJECT_ROOT / "README.md"


def _container_section(readme: str) -> str:
    start = readme.index("## Run with Docker Compose")
    end = readme.index("\n## Run the application", start)
    return readme[start:end]


def test_readme_documents_the_complete_compose_lifecycle() -> None:
    section = _container_section(README.read_text(encoding="utf-8"))

    for command in (
        "make container-build",
        "docker compose up --build",
        "docker compose ps",
        "curl --fail http://127.0.0.1:8000/health",
        "docker compose down",
    ):
        assert command in section

    assert '{"status":"ok"}' in section
    assert "http://127.0.0.1:8000/" in section


def test_readme_explains_named_volume_persistence() -> None:
    section = _container_section(README.read_text(encoding="utf-8"))
    prose = " ".join(section.split())

    assert "project-board-data" in section
    assert "/data/project_board.sqlite3" in section
    assert "not in the repository" in prose
    assert "To verify persistence" in prose
    assert "confirm that the Project is still present" in prose
    assert "while preserving application data" in prose


def test_readme_separates_and_warns_about_destructive_cleanup() -> None:
    section = _container_section(README.read_text(encoding="utf-8"))
    prose = " ".join(section.split())
    warning = section.index("### Warning: permanently delete container data")
    normal_stop = section.index("docker compose down")
    destructive_stop = section.index("docker compose down --volumes")

    assert normal_stop < warning < destructive_stop
    assert "permanently deleting" in section[warning:]
    assert "system-wide Docker cleanup" in prose
    assert "unrelated resources" in prose
    assert "docker system prune" not in section
    assert "docker volume prune" not in section
