from html.parser import HTMLParser
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import urljoin, urlsplit
import zipfile

from fastapi.testclient import TestClient

from app import create_app
from impad.services import AnalysisService, JsonRunStore


class EmptyRetriever:
    def retrieve(self, query, top_k=5):
        return []


class DocumentParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.visible_links = []
        self.stylesheets = []
        self.scripts = []
        self._link = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "a":
            visible = (
                "hidden" not in attributes
                and (attributes.get("aria-hidden") or "").lower() != "true"
            )
            self._link = {
                "href": attributes.get("href"),
                "text": [],
                "visible": visible,
            }
        elif tag == "link":
            rel = (attributes.get("rel") or "").lower().split()
            if "stylesheet" in rel and attributes.get("href"):
                self.stylesheets.append(attributes["href"])
        elif tag == "script" and attributes.get("src"):
            self.scripts.append(attributes["src"])

    def handle_data(self, data):
        if self._link is not None:
            self._link["text"].append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._link is not None:
            if self._link["visible"] and self._link["href"]:
                text = " ".join("".join(self._link["text"]).split())
                self.visible_links.append((text, self._link["href"]))
            self._link = None


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


def test_root_navigation_reaches_workbench_and_loads_its_assets(tmp_path):
    client = _client(tmp_path)
    root = client.get("/")
    root_document = DocumentParser()
    root_document.feed(root.text)
    workbench_links = [
        href
        for text, href in root_document.visible_links
        if text == "打开开发者研究工作台"
    ]

    assert root.status_code == 200
    assert len(workbench_links) == 1

    workbench = client.get(workbench_links[0])
    workbench_document = DocumentParser()
    workbench_document.feed(workbench.text)

    assert workbench.status_code == 200
    assert workbench_document.stylesheets
    assert workbench_document.scripts

    workbench_origin = urlsplit(str(workbench.url))
    for href in workbench_document.stylesheets:
        asset_url = urlsplit(urljoin(str(workbench.url), href))
        assert (asset_url.scheme, asset_url.netloc) == (
            workbench_origin.scheme,
            workbench_origin.netloc,
        )
        response = client.get(asset_url.geturl())
        assert response.status_code == 200
        assert "text/css" in response.headers["content-type"]

    for src in workbench_document.scripts:
        asset_url = urlsplit(urljoin(str(workbench.url), src))
        assert (asset_url.scheme, asset_url.netloc) == (
            workbench_origin.scheme,
            workbench_origin.netloc,
        )
        response = client.get(asset_url.geturl())
        assert response.status_code == 200
        assert "javascript" in response.headers["content-type"]


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


def test_workbench_has_all_input_and_result_landmarks(tmp_path):
    html = _client(tmp_path).get("/workbench").text

    for marker in (
        'id="capability-status"',
        'id="runtime-mode"',
        'id="single-panel"',
        'id="batch-panel"',
        'id="url-panel"',
        'id="submission-status"',
        'id="batch-results"',
        'id="verdict-section"',
        'id="coverage-section"',
        'id="evidence-section"',
        'id="creator-shift-section"',
        'id="history-section"',
        'id="law-section"',
        'id="trace-section"',
        'id="report-section"',
        'id="raw-section"',
    ):
        assert marker in html


def test_workbench_has_accessible_status_and_tabs(tmp_path):
    html = _client(tmp_path).get("/workbench").text

    assert 'role="tablist"' in html
    assert html.count('role="tab"') == 3
    assert 'aria-live="polite"' in html
    assert 'aria-label="分析输入"' in html
    assert 'aria-label="分析结果"' in html


def test_workbench_markup_has_no_inline_or_remote_execution_path(tmp_path):
    html = _client(tmp_path).get("/workbench").text

    assert "<style" not in html.lower()
    assert re.search(r"<script[^>]+src=", html, re.IGNORECASE)
    assert not re.search(r"<script(?![^>]+src=)", html, re.IGNORECASE)
    assert not re.search(r"\son[a-z]+\s*=", html, re.IGNORECASE)
    assert 'style="' not in html.lower()
    assert "http://" not in html.lower()
    assert "https://" not in html.lower()


def test_workbench_css_has_narrow_layout_and_no_remote_assets(tmp_path):
    css = _client(tmp_path).get(
        "/workbench/assets/workbench.css"
    ).text

    assert "@media (max-width: 860px)" in css
    assert "overflow-wrap: anywhere" in css
    assert "url(http" not in css.lower()


def test_workbench_script_avoids_forbidden_browser_capabilities(tmp_path):
    script = _client(tmp_path).get(
        "/workbench/assets/workbench.js"
    ).text

    for forbidden in (
        "innerHTML",
        "outerHTML",
        "insertAdjacentHTML",
        "localStorage",
        "sessionStorage",
        "indexedDB",
        "document.cookie",
        "serviceWorker",
        "http://",
        "https://",
    ):
        assert forbidden not in script
