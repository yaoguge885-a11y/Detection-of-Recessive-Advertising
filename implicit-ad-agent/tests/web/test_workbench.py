import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

from fastapi.testclient import TestClient

from app import create_app
from impad.services import AnalysisService, JsonRunStore


class EmptyRetriever:
    def retrieve(self, query, top_k=5):
        return []


def _client(tmp_path: Path) -> TestClient:
    service = AnalysisService(
        retriever=EmptyRetriever(),
        run_store=JsonRunStore(tmp_path / "runs"),
    )
    return TestClient(create_app(service))


def test_workbench_document_and_assets_are_served(tmp_path):
    client = _client(tmp_path)

    document = client.get("/workbench")
    stylesheet = client.get("/workbench/assets/workbench.css")
    script = client.get("/workbench/assets/workbench.js")

    assert document.status_code == 200
    assert document.encoding.lower() == "utf-8"
    assert "text/html" in document.headers["content-type"]
    assert stylesheet.status_code == 200
    assert "text/css" in stylesheet.headers["content-type"]
    assert script.status_code == 200
    assert "javascript" in script.headers["content-type"]


def test_workbench_document_has_strict_security_headers(tmp_path):
    response = _client(tmp_path).get("/workbench")

    assert response.headers["content-security-policy"] == (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'"
    )
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"


def test_built_wheel_contains_workbench_assets(tmp_path):
    project_root = Path(__file__).resolve().parents[2]
    build_root = tmp_path / "project"
    wheel_directory = tmp_path / "wheel"
    build_root.mkdir()
    shutil.copy2(project_root / "pyproject.toml", build_root / "pyproject.toml")
    shutil.copytree(project_root / "impad", build_root / "impad")

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--disable-pip-version-check",
            "--no-build-isolation",
            "--no-deps",
            "--wheel-dir",
            str(wheel_directory),
            str(build_root),
        ],
        check=True,
        capture_output=True,
        env={**os.environ, "PIP_NO_INDEX": "1"},
        text=True,
    )

    wheel = next(wheel_directory.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        packaged_files = set(archive.namelist())

    assert {
        "impad/web/index.html",
        "impad/web/workbench.css",
        "impad/web/workbench.js",
    } <= packaged_files
