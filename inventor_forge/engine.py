"""Forge: runs registered tools on the COM apartment and turns failures into readable errors."""
from __future__ import annotations

import inspect
import traceback
from typing import Any

from .com import Apartment, InventorError, com_error_text
from .registry import TOOLS, load_all
from .session import Session


class Forge:
    def __init__(self, visible: bool = True):
        load_all()
        self.apartment = Apartment()
        self.session = Session(visible=visible)
        self.tools = TOOLS

    def call(self, name: str, args: dict | None = None, timeout: float | None = 1800) -> dict:
        t = self.tools.get(name)
        if t is None:
            raise InventorError(f"unknown tool {name!r}")
        args = dict(args or {})
        params = list(inspect.signature(t.fn).parameters)[1:]
        unknown = [k for k in args if k not in params]
        if unknown:
            raise InventorError(f"{name}: unknown argument(s) {unknown}; expected {params}")

        def run():
            try:
                out = t.fn(self.session, **args)
            except InventorError:
                raise
            except TypeError as e:
                if "argument" in str(e):
                    raise InventorError(f"{name}: {e}") from e
                raise
            except Exception as e:
                if type(e).__name__ == "com_error":
                    raise InventorError(f"{name}: Inventor rejected the operation — {com_error_text(e)}") from e
                raise
            return out if isinstance(out, dict) else {"result": out}

        return self.apartment.run(run, timeout=timeout)

    def safe_call(self, name: str, args: dict | None = None) -> dict:
        """Never raises: {"ok": False, "error": ...} on failure."""
        try:
            return {"ok": True, **self.call(name, args)}
        except InventorError as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"{type(e).__name__}: {e}",
                    "trace": traceback.format_exc(limit=4)[-1500:]}
