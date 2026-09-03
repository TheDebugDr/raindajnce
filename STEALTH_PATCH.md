# Silent evasion failure — patch for `raindance/evasion/browser_factory.py`

Not applied. raindancev2 is untouched; this is the diff to review.

## The problem

The packaged `_apply_stealth` swallows every failure:

```python
    def _apply_stealth(self, context) -> None:
        try:
            script = self.fingerprint_manager.init_script()
            if script:
                context.add_init_script(script)
        except Exception:
            pass                      # <- init script silently skipped

        try:
            from playwright_stealth import Stealth
            Stealth().apply_stealth_sync(context)
        except Exception:
            try:
                from playwright_stealth import stealth_sync  # type: ignore
                stealth_sync(context)
            except Exception:
                pass                  # <- stealth silently skipped
```

Both `except ... pass` arms are reachable in normal operation: an uninstalled
or upgraded `playwright-stealth`, or a `FingerprintManager` without
`init_script`. When one fires, `evasion_enabled` still reports `True`, the
Evasion page still shows ON, the log says nothing, and the session runs
unpatched. The failure mode is a browser that only *looks* protected — the
worst possible one, because nothing tells you.

Confirmed against the installed package: current `playwright-stealth` exposes
`Stealth` with `apply_stealth_sync` / `apply_stealth_async` (accepting a Page
*or* a BrowserContext) and no module-level `stealth_sync`, so the 1.x fallback
arm can only ever reach the final `pass`.

## The change

Make `_apply_stealth` return what it did, record it, and fail loudly when asked
to. The full version is in `browser_factory.py` in this folder — it is otherwise
a faithful mirror of the packaged module (same sync API, same
`create_context(playwright, ...)` signature, same `(browser, context, page)`
return), so diffing the two shows only this.

Three edits to the packaged file:

1. Add near the top:

   ```python
   class EvasionError(RuntimeError):
       """Evasion was switched on but could not actually be applied."""
   ```

2. `__init__`: add `strict_evasion: bool = True` and
   `self.last_stealth: str = ""`; add `strict_evasion` to `configure()`.

3. Replace `_apply_stealth` with the version in this folder's
   `browser_factory.py`, and in `create_context` capture its return:

   ```python
   if self.evasion_enabled:
       self.last_stealth = self._apply_stealth(context)
   ```

## Callers

`tasks/runner.py:120`, `core/engine.py:149` and `auto_checkout.py:389` are
unaffected — the signature and return value do not change. They gain
`factory.last_stealth`, worth logging next to `last_proxy` / `last_fingerprint`.

With `strict_evasion=True` a launch that cannot be patched now raises instead
of proceeding. If you would rather have the old behaviour anywhere, pass
`strict_evasion=False` there and read `last_stealth`, which will start with
`NOT APPLIED -`.
