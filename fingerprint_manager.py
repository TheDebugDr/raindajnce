from __future__ import annotations
import random
from typing import Dict


class FingerprintManager:
    """Generates browser fingerprints."""

    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)

    def generate(self) -> Dict:
        return {
            "user_agent": self._get_user_agent(),
            "viewport": {"width": 1920, "height": 1080},
            "locale": "en-US",
            "timezone_id": "America/Denver",
        }

    def _get_user_agent(self) -> str:
        agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        ]
        return self.rng.choice(agents)
