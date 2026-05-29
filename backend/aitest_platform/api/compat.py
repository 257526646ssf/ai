from __future__ import annotations

import inspect

from starlette import routing as starlette_routing


def patch_starlette_router_for_fastapi() -> None:
    """Keep local smoke tests running when FastAPI and Starlette are skewed."""

    original_init = starlette_routing.Router.__init__
    if getattr(original_init, "_aitest_platform_patched", False):
        return

    accepted = set(inspect.signature(original_init).parameters)
    lifecycle_keys = {"on_startup", "on_shutdown", "lifespan"}

    def patched_init(self, *args, **kwargs):
        startup_handlers = kwargs.get("on_startup") or []
        shutdown_handlers = kwargs.get("on_shutdown") or []
        for key in lifecycle_keys - accepted:
            kwargs.pop(key, None)
        result = original_init(self, *args, **kwargs)
        if not hasattr(self, "on_startup"):
            self.on_startup = startup_handlers
        if not hasattr(self, "on_shutdown"):
            self.on_shutdown = shutdown_handlers
        return result

    patched_init._aitest_platform_patched = True
    starlette_routing.Router.__init__ = patched_init
