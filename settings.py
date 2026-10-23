"""Load this project's ignored local settings without executing shell code."""

import os
import re
from pathlib import Path


def load_local_env(path=None):
    target = Path(path) if path else Path(__file__).resolve().parent / ".env.local"
    if not target.is_file():
        return
    for line in target.read_text().splitlines():
        name, separator, value = line.partition("=")
        name = name.strip()
        if (
            not separator
            or name not in ("OPENAI_API_KEY", "OPENAI_MODEL")
            or name in os.environ
        ):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in (chr(34), chr(39)):
            value = value[1:-1]
        if not value:
            continue
        if name == "OPENAI_API_KEY" and not re.fullmatch(r"sk-[A-Za-z0-9_-]+", value):
            raise ValueError(
                "Invalid local API key format; no credential value displayed."
            )
        if name == "OPENAI_MODEL" and not re.fullmatch(r"[A-Za-z0-9_.:/-]+", value):
            raise ValueError("Invalid local model setting.")
        os.environ[name] = value
