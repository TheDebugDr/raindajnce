# betatest2 — superseded

Everything worked out here has been merged into the real project at
`~/raindancev2`. **Run and demo that one** (`python app.py`), not this folder.

What moved, and where it lives now:

| worked out here | merged into |
|---|---|
| loud stealth failure + `last_stealth` + `strict_evasion` | `raindance/evasion/browser_factory.py` |
| proxy validation, `mask`, `replace_lines`, `as_lines`, `save_to`, `check` | `raindance/evasion/proxy_manager.py` |
| proxy paste / save & apply / reachability UI | `raindance/plugins/evasion.py` |
| strict-mode persistence + bus wiring | `app.py`, `raindance/core/engine.py` |

The `.py` files still here are the earlier standalone scaffold. They are now
DUPLICATES of package modules and will drift — keep them only as scratch, and
change the package copies instead.

The three UI directions are on the design canvas, not in this folder.
