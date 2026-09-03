"""Create Playwright browser contexts with optional evasion (stealth + proxy).

Mirrors raindance/evasion/browser_factory.py so this file can drop straight back
into the package. Same signature, same sync API, same (browser, context, page)
return, same caller-owned Playwright lifetime.

ONE behavioural change from the packaged version, and it is the point of this
copy: evasion failures are no longer swallowed. The packaged `_apply_stealth`
wraps everything in bare `except Exception: pass`, so a missing package or a
renamed API leaves `evasion_enabled` reporting True while nothing is patched.
Here every step reports, `last_stealth` records what actually happened, and
`strict_evasion` (default True) raises instead of continuing unpatched.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

try:  # normal package layout
    from raindance.evasion.fingerprint_manager import FingerprintManager
    from raindance.evasion.proxy_manager import ProxyManager
except ImportError:  # running flat out of this folder
    from fingerprint_manager import FingerprintManager
    from proxy_manager import ProxyManager

log = logging.getLogger(__name__)

# Conservative flags: strip the automation banner/flags without disabling
# security features that could break real store pages.
_STEALTH_ARGS: List[str] = [
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-infobars",
    "--disable-dev-shm-usage",
    "--disable-popup-blocking",
]


class EvasionError(RuntimeError):
    """Evasion was switched on but could not actually be applied."""


class BrowserFactory:
    """Creates Playwright browser contexts with optional evasion features."""

    def __init__(
        self,
        proxy_manager: Optional[ProxyManager] = None,
        fingerprint_manager: Optional[FingerprintManager] = None,
        evasion_enabled: bool = False,
        strict_evasion: bool = True,
        on_step: Optional[Callable[[str], None]] = None,
    ):
        self.proxy_manager = proxy_manager
        self.fingerprint_manager = fingerprint_manager or FingerprintManager()
        self.evasion_enabled = bool(evasion_enabled)
        self.strict_evasion = bool(strict_evasion)
        self.on_step = on_step
        # Set on the most recent create_context so callers can log what was used.
        self.last_proxy: Optional[Dict] = None
        self.last_fingerprint: str = ""
        self.last_stealth: str = ""

    def configure(
        self,
        *,
        evasion_enabled: Optional[bool] = None,
        proxy_manager: Optional[ProxyManager] = None,
        strict_evasion: Optional[bool] = None,
    ) -> None:
        """Hot-update factory flags (e.g. after the Evasion UI toggle)."""
        if evasion_enabled is not None:
            self.evasion_enabled = bool(evasion_enabled)
        if proxy_manager is not None:
            self.proxy_manager = proxy_manager
        if strict_evasion is not None:
            self.strict_evasion = bool(strict_evasion)

    def _step(self, msg: str) -> None:
        log.info(msg)
        if self.on_step is not None:
            self.on_step(msg)

    def create_context(
        self,
        playwright,
        *,
        account_id: str = "default",
        headless: bool = False,
        user_data_dir: Optional[str] = None,
        slow_mo: int = 0,
        viewport: Optional[Dict] = None,
        user_agent: Optional[str] = None,
        for_harvester: bool = False,
        keep_open_hint: bool = False,  # reserved for callers
    ) -> Tuple[Any, Any, Any]:
        """Launch a browser/context/page.

        Returns (browser, context, page). For persistent profiles, browser is
        None (the context owns the process).
        """
        proxy = self._pick_proxy(account_id, for_harvester)
        self.last_proxy = proxy
        self._step(f"proxy: {proxy['server'] if proxy else 'none'}")

        if self.evasion_enabled:
            context_opts = self._context_options(viewport, user_agent)
            self.last_fingerprint = self._describe_fingerprint()
        else:
            context_opts = {}
            if viewport:
                context_opts["viewport"] = viewport
            if user_agent:
                context_opts["user_agent"] = user_agent
            self.last_fingerprint = ""
        self._step(f"fingerprint: {self.last_fingerprint or 'disabled'}")

        launch_kwargs: Dict[str, Any] = {
            "headless": headless,
            "slow_mo": int(slow_mo or 0),
        }
        if self.evasion_enabled:
            launch_kwargs["args"] = list(_STEALTH_ARGS)
            launch_kwargs["ignore_default_args"] = ["--enable-automation"]
        if proxy:
            launch_kwargs["proxy"] = proxy

        browser = None
        if user_data_dir:
            Path(user_data_dir).mkdir(parents=True, exist_ok=True)
            # Persistent: launch flags and context options go in one call. A
            # persistent context never goes through new_context(), so options
            # handed to new_context() would be silently dropped on this path.
            context = playwright.chromium.launch_persistent_context(
                user_data_dir, **launch_kwargs, **context_opts
            )
            self._step(f"launched persistent context: {user_data_dir}")
        else:
            browser = playwright.chromium.launch(**launch_kwargs)
            context = browser.new_context(**context_opts)
            self._step("launched fresh (non-persistent) context")

        if self.evasion_enabled:
            self.last_stealth = self._apply_stealth(context)
            self._step(f"stealth: {self.last_stealth}")
        else:
            self.last_stealth = ""
            self._step("stealth: skipped (evasion disabled)")

        page = context.pages[0] if context.pages else context.new_page()
        self._step(f"page ready ({len(context.pages)} open)")
        return browser, context, page

    # -- internals --------------------------------------------------------- #
    def _pick_proxy(self, account_id: str, for_harvester: bool) -> Optional[Dict]:
        if not (self.evasion_enabled and self.proxy_manager):
            return None
        try:
            return self.proxy_manager.get_proxy(account_id, for_harvester=for_harvester)
        except TypeError:
            # Tolerate an older ProxyManager without the for_harvester kwarg.
            return self.proxy_manager.get_proxy(account_id)

    def _context_options(self, viewport, user_agent) -> Dict:
        """Full fingerprint when the manager supports it, else its plain dict."""
        fm = self.fingerprint_manager
        if hasattr(fm, "context_options"):
            return fm.context_options(
                override={"viewport": viewport, "user_agent": user_agent}
            )
        opts = dict(fm.generate())
        if viewport:
            opts["viewport"] = viewport
        if user_agent:
            opts["user_agent"] = user_agent
        return opts

    def _describe_fingerprint(self) -> str:
        fm = self.fingerprint_manager
        if hasattr(fm, "describe"):
            return fm.describe()
        return "static stub"

    def _apply_stealth(self, context) -> str:
        """Inject the fingerprint-aligned script, then playwright-stealth.

        Unlike the packaged version, neither step fails silently: each one
        reports, and strict_evasion turns a failure into an EvasionError rather
        than a browser that only looks patched.
        """
        notes: List[str] = []

        # 1. our own init script (absent on the stub FingerprintManager)
        script = ""
        try:
            script = self.fingerprint_manager.init_script()
        except AttributeError:
            notes.append("no init_script on this FingerprintManager")
        except Exception as exc:
            return self._problem(f"init_script raised {type(exc).__name__}: {exc}", exc)
        if script:
            try:
                context.add_init_script(script)
                notes.append("init_script ok")
            except Exception as exc:
                return self._problem(
                    f"add_init_script failed {type(exc).__name__}: {exc}", exc
                )

        # 2. playwright-stealth (2.x Stealth class, else 1.x module functions)
        try:
            import playwright_stealth
        except ImportError as exc:
            return self._problem(
                "playwright-stealth is not installed "
                "(pip install playwright-stealth)", exc, notes
            )

        version = getattr(playwright_stealth, "__version__", "unknown")

        stealth_cls = getattr(playwright_stealth, "Stealth", None)
        if stealth_cls is not None:
            stealth = stealth_cls()
            fn = getattr(stealth, "apply_stealth_sync", None)
            if fn is not None:
                try:
                    fn(context)
                except Exception as exc:
                    return self._problem(
                        f"Stealth().apply_stealth_sync failed "
                        f"{type(exc).__name__}: {exc}", exc, notes
                    )
                notes.append(
                    f"Stealth().apply_stealth_sync(context) "
                    f"[playwright-stealth {version}]"
                )
                return " · ".join(notes)

        legacy = getattr(playwright_stealth, "stealth_sync", None)
        if legacy is not None:
            try:
                legacy(context)
            except Exception as exc:
                return self._problem(
                    f"stealth_sync failed {type(exc).__name__}: {exc}", exc, notes
                )
            notes.append(f"stealth_sync(context) [playwright-stealth {version}]")
            return " · ".join(notes)

        return self._problem(
            f"playwright-stealth {version} exposes no known entrypoint "
            "(looked for Stealth and stealth_sync)", None, notes
        )

    def _problem(
        self,
        msg: str,
        cause: Optional[BaseException] = None,
        notes: Optional[List[str]] = None,
    ) -> str:
        if self.strict_evasion:
            raise EvasionError(msg) from cause
        log.warning("evasion degraded: %s", msg)
        parts = list(notes or [])
        parts.append(f"NOT APPLIED - {msg}")
        return " · ".join(parts)
