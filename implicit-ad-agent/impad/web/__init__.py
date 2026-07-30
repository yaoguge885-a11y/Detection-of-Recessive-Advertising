"""Package-owned assets for the local developer workbench."""
from pathlib import Path


def asset_directory() -> Path:
    return Path(__file__).resolve().parent
