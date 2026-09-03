"""Design tokens for the RainDance evasion scaffold.

Same visual vocabulary as the main app: storm-indigo ground, signal-amber
reserved for the moment that matters, semantic colours kept off the accent,
monospace carrying the display role, 5px card radii.

Call inject() once per page, then build with the helpers below.
"""
from __future__ import annotations

from contextlib import contextmanager

from nicegui import ui

CSS = """
<style>
:root {
  --rd-ground:#0C0F1A; --rd-surface:#151A2B; --rd-surface-2:#1E2540;
  --rd-line:#2E3654; --rd-line-soft:#232B47;
  --rd-ink:#E8EAF4; --rd-ink-dim:#8A90AD; --rd-ink-faint:#626A8A;
  --rd-accent:#F2A93B; --rd-accent-lit:#FFC062;
  --rd-ok:#43C08A; --rd-live:#F0524D; --rd-watch:#5B8CE6; --rd-idle:#626A8A;
  --rd-term-bg:#070A10; --rd-term-ink:#7CFC98;
  --rd-mono: ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;
}
body { background:var(--rd-ground) !important; color:var(--rd-ink); }

.rd-lab   { font-family:var(--rd-mono); text-transform:uppercase; letter-spacing:.13em;
            font-size:10.5px; font-weight:600; color:var(--rd-ink-faint); }
.rd-title { font-family:var(--rd-mono); text-transform:uppercase; letter-spacing:.14em;
            font-size:13px; font-weight:700; color:var(--rd-ink); }
.rd-mono  { font-family:var(--rd-mono); font-variant-numeric:tabular-nums; }
.rd-dim   { color:var(--rd-ink-dim); font-size:12.5px; }

.rd-card { background:var(--rd-surface); border:1px solid var(--rd-line); border-radius:5px; }
.rd-cardhd { padding:14px 16px; border-bottom:1px solid var(--rd-line);
             display:flex; align-items:center; justify-content:space-between; }

.rd-chip { font-family:var(--rd-mono); font-size:9.5px; font-weight:700; letter-spacing:.09em;
           text-transform:uppercase; padding:3px 6px; border-radius:2.5px; white-space:nowrap; }
.rd-ok      { color:var(--rd-ok);     background:rgba(67,192,138,.14); }
.rd-err     { color:var(--rd-live);   background:rgba(240,82,77,.14); }
.rd-warn    { color:var(--rd-accent); background:rgba(242,169,59,.16); }
.rd-idlec   { color:var(--rd-idle);   background:rgba(98,106,138,.16); }
.rd-watchc  { color:var(--rd-watch);  background:rgba(91,140,230,.14); }

.rd-badge { font-family:var(--rd-mono); font-size:10.5px; font-weight:700; letter-spacing:.12em;
            text-transform:uppercase; padding:5px 10px; border-radius:3px; }
.rd-badge-on  { color:var(--rd-ok);        border:1px solid var(--rd-ok); }
.rd-badge-off { color:var(--rd-ink-faint); border:1px solid var(--rd-line); }

.rd-tab { font-family:var(--rd-mono); font-size:12px; padding:6px 11px; border-radius:3px;
          color:var(--rd-ink-dim); cursor:pointer; }
.rd-tab.rd-on { color:var(--rd-ink); background:var(--rd-surface-2); }

.rd-log { background:var(--rd-term-bg) !important; border:1px solid var(--rd-line);
          border-radius:5px; font-family:var(--rd-mono); font-size:11.5px; line-height:1.45;
          color:var(--rd-ink-dim); }

.rd-warnblock { padding:10px 11px; border-radius:3px; font-size:12.5px; color:var(--rd-ink);
                background:rgba(242,169,59,.13); border:1px solid rgba(242,169,59,.45); }

/* the launch moment - the one place the accent is spent */
.q-btn.rd-go, .rd-go {
  border-radius:3px !important; border:0; font-family:var(--rd-mono); font-weight:700;
  letter-spacing:.18em; text-transform:uppercase; font-size:12px;
  background:radial-gradient(circle at 50% 42%,var(--rd-accent-lit),var(--rd-accent) 62%) !important;
  color:#12100A !important;
  box-shadow:0 0 0 1px rgba(242,169,59,.35), 0 12px 34px -18px var(--rd-accent);
}
.q-btn.rd-go .q-btn__content { color:#12100A; }
</style>
"""


def inject() -> None:
    ui.add_head_html(CSS)


def title(text: str):
    return ui.label(text).classes("rd-title")


def lab(text: str):
    return ui.label(text).classes("rd-lab")


def chip(text: str, kind: str = "idlec"):
    return ui.label(text).classes(f"rd-chip rd-{kind}")


@contextmanager
def card(extra: str = ""):
    with ui.element("div").classes(f"rd-card w-full {extra}") as c:
        yield c


@contextmanager
def card_header(heading: str):
    with ui.element("div").classes("rd-cardhd w-full") as h:
        title(heading)
        yield h


def stat(label_text: str, value: str, sub: str = "", value_color: str = "var(--rd-ink)"):
    """A compact stat tile."""
    with card("p-4"):
        with ui.column().classes("gap-2 w-full"):
            lab(label_text)
            ui.label(value).classes("rd-mono").style(
                f"font-size:26px;font-weight:500;line-height:1;color:{value_color}")
            if sub:
                ui.label(sub).classes("rd-mono").style(
                    "font-size:11.5px;color:var(--rd-ink-faint)")
