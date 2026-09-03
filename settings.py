"""Minimal stand-in for raindance.core.settings.Settings.

Mirrors the packaged class's contract for the keys this scaffold touches —
same config.json filename, same evasion/browser/checkout/captcha shapes — so
code written against it behaves identically once the real package is importable.
main.py prefers raindance.core.settings and only falls back to this file.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

APP_CONFIG = Path("config.json")

DEFAULTS: dict[str, Any] = {
    "browser": {
        "headless": False,
        "user_data_dir": "profile",
        "slow_mo_ms": 0,
        "viewport": {"width": 1280, "height": 900},
    },
    "evasion": {
        "enabled": False,
        "sticky": True,
        "account_id": "default",
        "proxies_file": "proxies.txt",
        "proxies": [],
    },
    "checkout": {"dry_run": True, "force_dry_run": False},
    "captcha": {
        "mode": "manual",
        "timeout_seconds": 300,
        "poll_seconds": 1.5,
        "capsolver_key": "",
        "twocaptcha_key": "",
    },
}


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


class Settings:
    def __init__(self, path: str | Path = APP_CONFIG):
        self.path = Path(path)
        loaded: dict[str, Any] = {}
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text())
            except json.JSONDecodeError:
                loaded = {}
        # Merge over defaults so a missing key can never KeyError.
        self.data = _merge(DEFAULTS, loaded)

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data, indent=2))
