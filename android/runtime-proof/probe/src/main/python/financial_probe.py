"""Compatibility probe. Decimal success alone never qualifies financial engines."""

import importlib
import json
import platform
import time
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext


def run() -> str:
    started = time.perf_counter()
    results = {}
    for name in ["decimal", "sqlite3", "pydantic_core", "pydantic"]:
        try:
            module = importlib.import_module(name)
            results[name] = {"imported": True, "version": getattr(module, "__version__", None)}
        except Exception as exc:
            results[name] = {"imported": False, "error": type(exc).__name__ + ": " + str(exc)}
    with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
        value = str(Decimal(1) / Decimal(3))
    return json.dumps(
        {
            "python": platform.python_version(),
            "machine": platform.machine(),
            "imports": results,
            "decimal_1_over_3": value,
            "elapsed_seconds": time.perf_counter() - started,
            "financial_engine_qualified": False,
        },
        sort_keys=True,
    )
