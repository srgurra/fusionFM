from __future__ import annotations

import importlib
import inspect


class Plugin:
    name = None

    def setup(self, app):
        return None

    async def startup(self, app):
        return None

    async def shutdown(self, app):
        return None


def load_plugin(plugin):
    if isinstance(plugin, str):
        plugin = _load_from_path(plugin)

    if inspect.isclass(plugin):
        plugin = plugin()

    if not hasattr(plugin, "setup"):
        raise TypeError("Plugin must define a setup(app) method")

    return plugin


def _load_from_path(path):
    if ":" in path:
        module_name, attr_name = path.split(":", 1)
    else:
        module_name, attr_name = path, "plugin"

    module = importlib.import_module(module_name)

    try:
        return getattr(module, attr_name)
    except AttributeError as exc:
        raise ImportError(f"Plugin '{path}' could not be loaded") from exc
