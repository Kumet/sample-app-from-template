import subprocess
import sys
import tarfile
import tomllib
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[3]
WEB_ASSETS = {"app.css", "app.js", "index.html"}


@pytest.fixture(scope="module")
def web_archives(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[tuple[Path, Path]]:
    output_directory = tmp_path_factory.mktemp("web-archives")
    subprocess.run(  # noqa: S603 - command arguments are test constants
        [
            sys.executable,
            "-m",
            "build",
            "--sdist",
            "--wheel",
            "--no-isolation",
            "--skip-dependency-check",
            "--outdir",
            str(output_directory),
        ],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    wheels = list(output_directory.glob("*.whl"))
    source_archives = list(output_directory.glob("*.tar.gz"))
    assert len(wheels) == 1
    assert len(source_archives) == 1
    yield wheels[0], source_archives[0]


def test_package_configuration_changes_only_explicit_web_package_data() -> None:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as configuration_file:
        configuration = tomllib.load(configuration_file)

    assert configuration["tool"]["setuptools"]["package-data"] == {
        "project_board.web": ["index.html", "app.css", "app.js"]
    }
    assert configuration["build-system"] == {
        "requires": ["setuptools>=68,<81"],
        "build-backend": "setuptools.build_meta",
    }
    assert configuration["project"]["version"] == "0.1.0"
    assert configuration["project"]["dependencies"] == [
        "fastapi>=0.115,<1",
        "sqlalchemy>=2.0,<3",
        "uvicorn>=0.30,<1",
    ]
    assert configuration["project"]["optional-dependencies"]["dev"] == [
        "build>=1.2,<2",
        "httpx>=0.27,<1",
        "mypy>=1.14,<2",
        "pytest>=8,<9",
        "ruff>=0.9,<1",
    ]


def test_wheel_and_sdist_contain_exactly_the_fixed_web_assets(
    web_archives: tuple[Path, Path],
) -> None:
    wheel, source_archive = web_archives

    with zipfile.ZipFile(wheel) as built_wheel:
        wheel_assets = {
            name.removeprefix("project_board/web/")
            for name in built_wheel.namelist()
            if name.startswith("project_board/web/") and not name.endswith(".py")
        }
    with tarfile.open(source_archive, "r:gz") as built_sdist:
        sdist_assets = {
            Path(name).name
            for name in built_sdist.getnames()
            if "/src/project_board/web/" in name and not name.endswith(".py")
        }

    assert wheel_assets == WEB_ASSETS
    assert sdist_assets == WEB_ASSETS


def test_built_archives_serve_assets_independently_of_current_directory(
    web_archives: tuple[Path, Path], tmp_path: Path
) -> None:
    wheel, source_archive = web_archives
    extracted_sdist = tmp_path / "sdist"
    extracted_sdist.mkdir()
    with tarfile.open(source_archive, "r:gz") as built_sdist:
        members = built_sdist.getmembers()
        assert all(
            not Path(member.name).is_absolute() and ".." not in Path(member.name).parts
            for member in members
        )
        built_sdist.extractall(extracted_sdist, members=members)  # noqa: S202

    sdist_roots = list(extracted_sdist.glob("*/src"))
    assert len(sdist_roots) == 1
    for import_root in (wheel, sdist_roots[0]):
        result = subprocess.run(  # noqa: S603 - command and script are test constants
            [
                sys.executable,
                "-c",
                (
                    "import sys\n"
                    "sys.path.insert(0, sys.argv[1])\n"
                    "from project_board.api.web_routes import "
                    "web_index, web_script, web_stylesheet\n"
                    "assert web_index().body.startswith(b'<!doctype html>')\n"
                    "assert web_stylesheet().body\n"
                    "assert web_script().body.startswith(b'\"use strict\";')\n"
                ),
                str(import_root),
            ],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            text=True,
        )
        assert result.stdout == ""
