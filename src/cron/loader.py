from __future__ import annotations

import importlib
import pkgutil


def discover_and_register_jobs(package: str = "src.cron.jobs") -> None:
    """
    Auto-import every module in `package` so their @cron decorators run
    and register jobs into the global registry.
    """
    pkg = importlib.import_module(package)
    for _, modname, ispkg in pkgutil.iter_modules(pkg.__path__, pkg.__name__ + "."):
        if not ispkg:
            importlib.import_module(modname)
