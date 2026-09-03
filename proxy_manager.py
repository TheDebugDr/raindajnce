"""Proxy pool with sticky assignment per account.

Mirrors raindance/evasion/proxy_manager.py's public surface — parse_proxy,
from_lines / from_file / from_settings, count, get_proxy(account_id,
for_harvester=), mark_bad, clear_sticky — so this file drops back into the
package. Adds replace_lines() so the pool can be edited from the UI without a
restart.
"""
from __future__ import annotations

import random
import re
import socket
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

SESSION_PLACEHOLDER = "{session}"


def parse_proxy(line: str) -> Optional[Dict]:
    """Parse one proxy line into Playwright's proxy dict.

    Accepted forms:
      http://host:port
      http://user:pass@host:port
      host:port
      host:port:user:pass
      socks5://host:port
    """
    raw = (line or "").strip()
    if not raw or raw.startswith("#"):
        return None

    if "://" in raw:
        u = urlparse(raw)
        if not u.hostname:
            return None
        port = f":{u.port}" if u.port else ""
        out: Dict = {"server": f"{u.scheme}://{u.hostname}{port}"}
        if u.username:
            out["username"] = u.username
        if u.password:
            out["password"] = u.password
        return out

    parts = raw.split(":")
    if len(parts) == 2:
        return {"server": f"http://{parts[0]}:{parts[1]}"}
    if len(parts) == 4:
        return {"server": f"http://{parts[0]}:{parts[1]}",
                "username": parts[2], "password": parts[3]}
    if len(parts) == 3:
        return {"server": f"http://{parts[0]}:{parts[1]}", "username": parts[2]}
    return {"server": f"http://{raw}"}


# A hostname or IPv4 literal - deliberately strict, so junk lines are rejected
# rather than silently becoming a proxy named "not a proxy!!".
_HOST_RE = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?"
                      r"(\.[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?)*$")


def host_port(proxy: Dict) -> Tuple[str, int]:
    """(host, port) from a parsed proxy dict, port defaulting to 80."""
    try:
        u = urlparse(proxy.get("server", ""))
        return (u.hostname or ""), int(u.port or 80)
    except ValueError:
        return "", 0


def valid(proxy: Optional[Dict]) -> bool:
    """A proxy is usable only with a real hostname AND an explicit port."""
    if not proxy:
        return False
    try:
        u = urlparse(proxy.get("server", ""))
        host, port = (u.hostname or ""), u.port   # .port itself raises on junk
    except ValueError:
        return False
    if not host or not _HOST_RE.match(host):
        return False
    return bool(port and 0 < int(port) < 65536)


def mask(proxy: Dict) -> str:
    """Human-safe one-liner: credentials reduced to the username's first chars."""
    host, port = host_port(proxy)
    user = proxy.get("username")
    if not user:
        return f"{host}:{port}"
    shown = user[:3] + "…" if len(user) > 3 else user
    return f"{host}:{port}  ({shown}:••••)"


class ProxyManager:
    """Handles proxies with optional sticky sessions per account_id."""

    def __init__(self, proxies: List[Dict] | None = None, sticky: bool = True,
                 health_check: bool = True, sticky_session: bool = True):
        self.proxies: List[Dict] = list(proxies or [])
        self.harvester_proxies: List[Dict] = self._harvester_slice(self.proxies)
        self.sticky = sticky
        self.sticky_session = sticky_session
        self.health_check = health_check
        self._sticky_map: Dict[str, Dict] = {}
        self._index = 0
        self._bad: set[str] = set()

    # -- construction ------------------------------------------------------ #
    @staticmethod
    def _harvester_slice(proxies: List[Dict]) -> List[Dict]:
        return list(proxies[-2:]) if len(proxies) > 4 else []

    @classmethod
    def from_lines(cls, lines: List[str], sticky: bool = True) -> "ProxyManager":
        parsed = [p for p in (parse_proxy(l) for l in lines) if p]
        return cls(parsed, sticky=sticky)

    @classmethod
    def from_file(cls, path: str | Path, sticky: bool = True) -> "ProxyManager":
        p = Path(path)
        if not p.exists():
            return cls([], sticky=sticky)
        return cls.from_lines(p.read_text().splitlines(), sticky=sticky)

    @classmethod
    def from_settings(cls, evasion: dict, *,
                      proxies_file: str = "proxies.txt") -> "ProxyManager":
        evasion = evasion or {}
        sticky = bool(evasion.get("sticky", True))
        inline = evasion.get("proxies") or []
        if inline:
            return cls.from_lines(list(inline), sticky=sticky)
        return cls.from_file(evasion.get("proxies_file") or proxies_file, sticky=sticky)

    # -- editing ----------------------------------------------------------- #
    def replace_lines(self, text: str) -> Tuple[int, List[str]]:
        """Swap the pool for the proxies in `text`. Returns (kept, rejected)."""
        kept: List[Dict] = []
        rejected: List[str] = []
        for line in (text or "").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parsed = parse_proxy(stripped)
            if not valid(parsed):
                rejected.append(stripped)
                continue
            kept.append(parsed)
        self.proxies = kept
        self.harvester_proxies = self._harvester_slice(kept)
        self._sticky_map.clear()
        self._bad.clear()
        self._index = 0
        return len(kept), rejected

    def as_lines(self) -> str:
        """The pool back as editable text (credentials intact)."""
        out: List[str] = []
        for p in self.proxies:
            u = urlparse(p["server"])
            auth = ""
            if p.get("username"):
                auth = p["username"]
                if p.get("password"):
                    auth += f":{p['password']}"
                auth += "@"
            port = f":{u.port}" if u.port else ""
            out.append(f"{u.scheme}://{auth}{u.hostname}{port}")
        return "\n".join(out)

    def save_to(self, path: str | Path) -> None:
        Path(path).write_text(self.as_lines() + "\n" if self.proxies else "")

    # -- reachability ------------------------------------------------------ #
    def check(self, proxy: Dict, timeout: float = 3.0) -> bool:
        """Best-effort TCP reachability of the proxy endpoint (no auth needed)."""
        host, port = host_port(proxy)
        if not host:
            return False
        try:
            with socket.create_connection((host, port), timeout=timeout):
                self._bad.discard(proxy["server"])
                return True
        except OSError:
            self._bad.add(proxy["server"])
            return False

    def is_bad(self, proxy: Dict) -> bool:
        return proxy.get("server", "") in self._bad

    # -- selection --------------------------------------------------------- #
    def count(self) -> int:
        return len(self.proxies)

    def healthy_count(self) -> int:
        return sum(1 for p in self.proxies if not self.is_bad(p))

    def _is_healthy(self, proxy: Dict) -> bool:
        return True if not self.health_check else not self.is_bad(proxy)

    def get_proxy(self, account_id: Optional[str] = None, *,
                  for_harvester: bool = False) -> Optional[Dict]:
        pool = self.harvester_proxies if for_harvester else self.proxies
        if not pool:
            pool = self.proxies
        if not pool:
            return None

        if self.sticky and account_id and not for_harvester:
            current = self._sticky_map.get(account_id)
            if current is None or not self._is_healthy(current):
                self._sticky_map[account_id] = random.choice(pool)
            return dict(self._sticky_map[account_id])

        chosen = pool[0]
        for _ in range(len(pool)):
            proxy = pool[self._index % len(pool)]
            self._index = (self._index + 1) % len(pool)
            if self._is_healthy(proxy):
                chosen = proxy
                break
        return dict(chosen)

    def sticky_for(self, account_id: str) -> Optional[Dict]:
        return self._sticky_map.get(account_id)

    def mark_bad(self, proxy: Dict, account_id: Optional[str] = None) -> None:
        self._bad.add(proxy.get("server", ""))
        if account_id:
            self._sticky_map.pop(account_id, None)

    def clear_sticky(self, account_id: Optional[str] = None) -> None:
        if account_id:
            self._sticky_map.pop(account_id, None)
        else:
            self._sticky_map.clear()
