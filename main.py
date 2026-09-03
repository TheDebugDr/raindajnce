#!/usr/bin/env python3
"""
RainDance — evasion scaffold, single-surface UI.

One page: a Dashboard and a Settings panel that swap in place. No tool drawer,
no redirects. Styling comes from theme.py (same tokens as the main app).

Threading note — this is why the launch path looks the way it does. The factory
uses Playwright's SYNC api, matching the packaged raindance module and its
callers. Sync Playwright refuses to start inside an asyncio loop, and NiceGUI is
an asyncio app, so a session cannot live on the UI thread. Playwright objects
are also bound to the thread that created them, so a session cannot be launched
on one pool thread and closed from another. Both constraints are satisfied the
same way the packaged runner does it: ONE worker thread owns a session for its
whole life, from sync_playwright() to close. The UI only ever exchanges signals
with that thread.
"""

from __future__ import annotations

import logging
import queue
import threading
import traceback
from typing import Optional

from nicegui import run, ui

try:  # normal package layout
    from raindance.core.settings import Settings
    from raindance.evasion.proxy_manager import ProxyManager
    from raindance.evasion.fingerprint_manager import FingerprintManager
    from raindance.evasion.browser_factory import BrowserFactory
except ImportError:  # running flat out of this folder
    from settings import Settings
    from proxy_manager import ProxyManager
    from fingerprint_manager import FingerprintManager
    from browser_factory import BrowserFactory

try:
    from raindance.evasion.proxy_manager import mask as proxy_mask
except ImportError:
    try:
        from proxy_manager import mask as proxy_mask
    except ImportError:                     # packaged manager without mask()
        def proxy_mask(pr: dict) -> str:
            return pr.get("server", "?")

import theme

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)

settings = Settings()
_evasion = settings.data.get("evasion") or {}
proxy_manager = (
    ProxyManager.from_settings(_evasion)
    if hasattr(ProxyManager, "from_settings")
    else ProxyManager.from_file(_evasion.get("proxies_file") or "proxies.txt",
                                sticky=bool(_evasion.get("sticky", True)))
)
fingerprint_manager = FingerprintManager()
PROXY_FILE = _evasion.get("proxies_file") or "proxies.txt"

# Steps are produced on worker threads and drained on the UI thread by a timer.
STEPS: "queue.Queue[str]" = queue.Queue()

factory = BrowserFactory(
    proxy_manager=proxy_manager,
    fingerprint_manager=fingerprint_manager,
    evasion_enabled=bool(_evasion.get("enabled")),
    on_step=STEPS.put,
)

sessions: dict[str, "SessionWorker"] = {}


def evasion_on() -> bool:
    return bool(settings.data["evasion"]["enabled"])


def proxy_count() -> int:
    if hasattr(proxy_manager, "count"):
        return int(proxy_manager.count())
    return len(getattr(proxy_manager, "proxies", []) or [])


class SessionWorker:
    """Owns one browser session for its entire life, on its own thread."""

    START_URL = "https://amiunique.org"

    def __init__(self, account_id: str, headless: bool):
        self.account_id = account_id
        self.headless = headless
        self.error: Optional[BaseException] = None
        self.trace: str = ""
        self.stealth: str = ""
        self.proxy: str = ""
        self._ready = threading.Event()
        self._close = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    # -- worker thread ----------------------------------------------------- #
    def _run(self) -> None:
        from playwright.sync_api import sync_playwright
        try:
            with sync_playwright() as p:
                browser, context, page = factory.create_context(
                    p,
                    account_id=self.account_id,
                    headless=self.headless,
                    user_data_dir=f"profiles/{self.account_id}",
                )
                self.stealth = factory.last_stealth
                self.proxy = (factory.last_proxy or {}).get("server", "none")
                page.goto(self.START_URL)
                STEPS.put(f"navigated to {self.START_URL}")
                self._ready.set()

                self._close.wait()          # hold the session open

                context.close()
                if browser is not None:
                    browser.close()
                STEPS.put(f"closed session account={self.account_id}")
        except Exception as exc:            # noqa: BLE001 - surfaced to the UI
            self.error = exc
            self.trace = traceback.format_exc()
            logging.exception("session %s failed", self.account_id)
        finally:
            self._ready.set()

    # -- UI thread --------------------------------------------------------- #
    def start(self) -> None:
        self._thread.start()

    def wait_ready(self, timeout: float = 120.0) -> bool:
        return self._ready.wait(timeout)

    def request_close(self) -> None:
        self._close.set()
        self._thread.join(timeout=20)

    @property
    def patched(self) -> bool:
        return bool(self.stealth) and "NOT APPLIED" not in self.stealth


@ui.page("/")
def index():
    ui.dark_mode(True)
    ui.page_title("RainDance")
    theme.inject()
    ui.query(".nicegui-content").classes("p-0 gap-0")

    view = {"tab": "dashboard"}

    with ui.header().classes("items-center gap-3 px-4").style(
        "background:var(--rd-surface);border-bottom:1px solid var(--rd-line);"
        "height:52px;min-height:52px;box-shadow:none"
    ):
        ui.html(
            '<span style="display:inline-block;width:22px;height:22px;border-radius:50%;'
            'border:1.5px solid var(--rd-accent);position:relative">'
            '<span style="position:absolute;inset:5px;border-radius:50%;'
            'background:var(--rd-accent)"></span></span>',
            sanitize=False,
        )
        ui.label("RainDance").classes("rd-mono").style(
            "font-weight:700;letter-spacing:.22em;text-transform:uppercase;"
            "font-size:13px;color:var(--rd-ink)"
        )
        ui.space()

        tabs: dict[str, ui.label] = {}

        def switch(tab: str) -> None:
            view["tab"] = tab
            for name, el in tabs.items():
                el.classes(replace="rd-tab rd-on" if name == tab else "rd-tab")
            render()

        for name, text in (("dashboard", "Dashboard"), ("settings", "Settings")):
            el = ui.label(text).classes("rd-tab rd-on" if name == "dashboard" else "rd-tab")
            el.on("click", lambda _=None, n=name: switch(n))
            tabs[name] = el

        evasion_badge = ui.label().classes("rd-badge")

    def paint_badge() -> None:
        on = evasion_on()
        evasion_badge.set_text("Evasion on" if on else "Evasion off")
        evasion_badge.classes(replace=f"rd-badge rd-badge-{'on' if on else 'off'}")

    paint_badge()

    body = ui.column().classes("w-full gap-4 p-4")
    log_view = ui.log(max_lines=400).classes("rd-log w-full").style("height:190px")

    def drain() -> None:
        while True:
            try:
                log_view.push(STEPS.get_nowait())
            except queue.Empty:
                return

    ui.timer(0.2, drain)

    # ------------------------------------------------------------- launching
    async def launch(account_id: str, headless: bool) -> None:
        aid = account_id or "default"
        if aid in sessions:
            ui.notify(f"{aid} is already running", type="warning")
            return
        STEPS.put(f"--- launch account={aid} evasion={evasion_on()} ---")
        worker = SessionWorker(aid, headless)
        worker.start()
        await run.io_bound(worker.wait_ready)
        if worker.error is not None:
            STEPS.put(f"FAILED {type(worker.error).__name__}: {worker.error}")
            for line in worker.trace.rstrip().splitlines():
                STEPS.put(line)
            ui.notify(f"{type(worker.error).__name__}: {worker.error}",
                      type="negative", multi_line=True)
        else:
            sessions[aid] = worker
            ui.notify("Session launched", type="positive")
        render()

    async def close(aid: str) -> None:
        worker = sessions.pop(aid, None)
        if worker is None:
            return
        await run.io_bound(worker.request_close)
        render()

    # ------------------------------------------------------------- dashboard
    def dashboard() -> None:
        live = len(sessions)
        patched = sum(1 for w in sessions.values() if w.patched)
        stealth_colour = ("var(--rd-ok)" if live and patched == live
                          else "var(--rd-accent)" if live else "var(--rd-ink)")

        with ui.row().classes("w-full gap-4 no-wrap"):
            theme.stat("Live sessions", str(live), "one worker thread each")
            healthy = (proxy_manager.healthy_count()
                       if hasattr(proxy_manager, "healthy_count") else proxy_count())
            theme.stat("Proxy pool",
                       f"{healthy} / {proxy_count()}" if proxy_count() else "0",
                       "sticky per account" if getattr(proxy_manager, "sticky", True)
                       else "round robin",
                       "var(--rd-ok)" if proxy_count() and healthy == proxy_count()
                       else "var(--rd-accent)" if proxy_count() else "var(--rd-ink)")
            theme.stat("Stealth", f"{patched} / {live}" if live else "—",
                       "applied to live sessions", stealth_colour)
            theme.stat("Strict mode", "on" if factory.strict_evasion else "off",
                       "fail loudly if unpatched")

        with theme.card():
            with theme.card_header("Sessions"):
                ui.label(f"{live} open").classes("rd-mono").style(
                    "font-size:11px;color:var(--rd-ink-faint)")
            if not sessions:
                ui.label("No sessions running. Launch one below.").classes("rd-dim p-4")
            for aid, worker in sessions.items():
                with ui.row().classes("items-center gap-3 w-full px-4 py-3").style(
                    "border-top:1px solid var(--rd-line-soft)"
                ):
                    ui.label(aid).style("font-size:13.5px;min-width:130px")
                    ui.label(worker.proxy or "none").classes("rd-mono").style(
                        "font-size:11.5px;color:var(--rd-ink-dim);flex-grow:1")
                    theme.chip("Stealth ok" if worker.patched else "Unpatched",
                               "ok" if worker.patched else "warn")
                    ui.button("Close", on_click=lambda _=None, a=aid: close(a)) \
                        .props("flat dense no-caps").classes("rd-mono") \
                        .style("color:var(--rd-live)")

        with theme.card("p-4"):
            with ui.row().classes("items-center gap-3 w-full no-wrap"):
                account = ui.input(value="default").props("dense dark outlined") \
                    .classes("rd-mono").style("flex-grow:1")
                headless = ui.switch("Headless", value=False).props("dense")
                ui.button("Launch",
                          on_click=lambda: launch(account.value, headless.value)) \
                    .classes("rd-go").style("height:38px;padding:0 26px")

    # -------------------------------------------------------------- settings
    def settings_panel() -> None:
        with theme.card():
            with theme.card_header("Evasion"):
                theme.chip("On" if evasion_on() else "Off",
                           "ok" if evasion_on() else "idlec")

            def toggle_evasion(value: bool) -> None:
                settings.data["evasion"]["enabled"] = value
                settings.save()
                factory.configure(evasion_enabled=value)
                paint_badge()
                STEPS.put(f"evasion {'enabled' if value else 'disabled'}")
                render()

            with ui.row().classes("items-center w-full px-4 py-4 gap-5 no-wrap").style(
                "border-top:1px solid var(--rd-line-soft)"
            ):
                with ui.column().classes("gap-1").style("flex-grow:1"):
                    ui.label("Stealth + proxies").style("font-size:14px")
                    ui.label("Applies to browser sessions. HTTP checks are unaffected.") \
                        .classes("rd-dim")
                ui.switch(value=evasion_on(),
                          on_change=lambda e: toggle_evasion(e.value)).props("dense")

            with ui.row().classes("items-center w-full px-4 py-4 gap-5 no-wrap").style(
                "border-top:1px solid var(--rd-line-soft)"
            ):
                with ui.column().classes("gap-1").style("flex-grow:1"):
                    ui.label("Strict mode").style("font-size:14px")
                    ui.label("Raise on launch if stealth cannot be applied, instead of "
                             "running a session that only looks patched.").classes("rd-dim")
                ui.switch(value=factory.strict_evasion,
                          on_change=lambda e: factory.configure(strict_evasion=e.value)) \
                    .props("dense")

        with theme.card():
            with theme.card_header("Fingerprint"):
                theme.chip("Static" if not hasattr(fingerprint_manager, "describe")
                           else "Coherent", "idlec")
            with ui.column().classes("w-full gap-3 p-4"):
                fp = (fingerprint_manager.context_options()
                      if hasattr(fingerprint_manager, "context_options")
                      else fingerprint_manager.generate())
                for key in ("user_agent", "viewport", "locale", "timezone_id"):
                    with ui.row().classes("items-center justify-between w-full no-wrap"):
                        theme.lab(key.replace("_", " "))
                        ui.label(str(fp.get(key, "—"))).classes("rd-mono").style(
                            "font-size:12.5px;color:var(--rd-ink);text-align:right")
                ui.html(
                    '<div class="rd-warnblock">Timezone is a fixed value and is not '
                    'correlated with the proxy exit — that mismatch is itself a signal.'
                    '</div>', sanitize=False)

        with theme.card():
            with theme.card_header("Proxies"):
                theme.chip(f"{proxy_count()} loaded", "idlec")
            with ui.column().classes("w-full gap-3 p-4"):
                ui.label("One per line. Blank lines and # comments ignored.") \
                    .classes("rd-dim")
                ui.label("host:port   ·   host:port:user:pass   ·   "
                         "http://user:pass@host:port   ·   socks5://host:port") \
                    .classes("rd-mono").style(
                        "font-size:11.5px;color:var(--rd-ink-faint)")

                box = ui.textarea(value=proxy_manager.as_lines()) \
                    .props("dark outlined rows=7 spellcheck=false") \
                    .classes("w-full rd-mono").style("font-size:12.5px")

                feedback = ui.column().classes("w-full gap-2")

                def report(kept: int, rejected: list[str]) -> None:
                    feedback.clear()
                    with feedback:
                        if rejected:
                            ui.html(
                                '<div class="rd-warnblock">Ignored '
                                f'{len(rejected)} unparseable line'
                                f'{"" if len(rejected) == 1 else "s"}: '
                                + ", ".join(
                                    f"<code>{r[:40]}</code>" for r in rejected[:4])
                                + ("…" if len(rejected) > 4 else "")
                                + "</div>", sanitize=False)
                        ui.label(f"{kept} proxy{'' if kept == 1 else 'ies'} loaded"
                                 f" · saved to {PROXY_FILE}").classes("rd-dim")

                def save_proxies() -> None:
                    kept, rejected = proxy_manager.replace_lines(box.value)
                    try:
                        proxy_manager.save_to(PROXY_FILE)
                    except OSError as exc:
                        ui.notify(f"Could not write {PROXY_FILE}: {exc}",
                                  type="negative")
                        return
                    box.set_value(proxy_manager.as_lines())
                    STEPS.put(f"proxy pool reloaded — {kept} loaded"
                              + (f", {len(rejected)} rejected" if rejected else ""))
                    report(kept, rejected)
                    ui.notify(f"{kept} proxies loaded", type="positive")
                    render()

                def _test_all() -> int:
                    return sum(1 for pr in proxy_manager.proxies
                               if proxy_manager.check(pr))

                async def test_proxies() -> None:
                    if not proxy_manager.proxies:
                        ui.notify("No proxies to test", type="warning")
                        return
                    total = proxy_count()
                    STEPS.put(f"testing {total} proxies (tcp connect, 3s each)…")
                    ok = await run.io_bound(_test_all)
                    STEPS.put(f"proxy check: {ok}/{total} reachable")
                    ui.notify(f"{ok} of {total} reachable",
                              type="positive" if ok == total else "warning")
                    render()

                with ui.row().classes("gap-2"):
                    ui.button("Save & reload", on_click=save_proxies) \
                        .props("no-caps").classes("rd-mono")
                    ui.button("Test reachability", on_click=test_proxies) \
                        .props("flat no-caps").classes("rd-mono") \
                        .style("color:var(--rd-ink-dim)")

            if proxy_manager.proxies:
                for pr in proxy_manager.proxies:
                    bad = proxy_manager.is_bad(pr)
                    holder = next((a for a, sp in
                                   getattr(proxy_manager, "_sticky_map", {}).items()
                                   if sp is pr), "")
                    with ui.row().classes(
                        "items-center gap-3 w-full px-4 py-2"
                    ).style("border-top:1px solid var(--rd-line-soft)"):
                        ui.label(proxy_mask(pr)).classes("rd-mono").style(
                            "font-size:12px;flex-grow:1;color:var(--rd-ink)")
                        if holder:
                            ui.label(f"sticky → {holder}").classes("rd-mono").style(
                                "font-size:11px;color:var(--rd-ink-faint)")
                        theme.chip("Unreachable" if bad else "Ready",
                                   "err" if bad else "ok")

        with theme.card():
            with theme.card_header("Runtime"):
                theme.chip("Diagnostics", "idlec")
            with ui.column().classes("w-full gap-3 p-4"):
                for mod in ("playwright", "nicegui", "playwright_stealth"):
                    try:
                        ver = getattr(__import__(mod), "__version__", "?")
                    except ImportError:
                        ver = "MISSING"
                    with ui.row().classes("items-center justify-between w-full no-wrap"):
                        theme.lab(mod)
                        ui.label(ver).classes("rd-mono").style(
                            "font-size:12.5px;color:"
                            + ("var(--rd-live)" if ver == "MISSING" else "var(--rd-ok)"))

    def render() -> None:
        body.clear()
        with body:
            dashboard() if view["tab"] == "dashboard" else settings_panel()

    render()


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(title="RainDance", port=8080, dark=True)
