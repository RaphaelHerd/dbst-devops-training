"""Configuration for OpsPilot: project paths, time zone and settings from the .env file."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent      # the opspilot/ project folder
DATA_DIR = ROOT / "data"                            # mock exports - read only
OUT_DIR = ROOT / "out"                              # everything OpsPilot writes
TIMEZONE = "Europe/Berlin"                          # all timestamps are converted to this zone


def load_env(path: Path | None = None) -> None:
    """Read KEY=VALUE lines from .env into the environment. Variables that are already set win."""
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value or value.startswith("<"):
        raise RuntimeError(f"{name} is not set. Copy .env.example to .env and add the values from your trainer.")
    return value


def model_id() -> str:
    """The Claude inference profile ID, e.g. us.anthropic.claude-haiku-5-5 (from OPSPILOT_MODEL)."""
    return _required("OPSPILOT_MODEL")


def embed_model_id() -> str:
    """The Bedrock embedding model (Lab 4): OPSPILOT_EMBED_MODEL, default Amazon Titan Text Embeddings V2."""
    return os.environ.get("OPSPILOT_EMBED_MODEL", "").strip() or "amazon.titan-embed-text-v2:0"


def aws_region() -> str:
    """The AWS region of the Bedrock endpoint, e.g. us-west-2 (from AWS_REGION)."""
    return _required("AWS_REGION")
