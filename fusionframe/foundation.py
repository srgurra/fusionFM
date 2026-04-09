from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class AppSettings:
    title: str = "fusionframe App"
    version: str = "0.1.0"
    debug: bool = False
    docs_enabled: bool = True
    docs_url: str = "/docs"
    openapi_url: str = "/openapi.json"
    max_body_size: int = 1024 * 1024 * 10

    @classmethod
    def from_env(cls):
        return cls(
            title=os.getenv("FUSIONFRAME_TITLE", cls.title),
            version=os.getenv("FUSIONFRAME_VERSION", cls.version),
            debug=os.getenv("FUSIONFRAME_DEBUG", "").lower() in {"1", "true", "yes"},
            docs_enabled=os.getenv("FUSIONFRAME_DOCS_ENABLED", "true").lower()
            in {"1", "true", "yes"},
            docs_url=os.getenv("FUSIONFRAME_DOCS_URL", cls.docs_url),
            openapi_url=os.getenv("FUSIONFRAME_OPENAPI_URL", cls.openapi_url),
            max_body_size=int(
                os.getenv("FUSIONFRAME_MAX_BODY_SIZE", str(cls.max_body_size))
            ),
        )


@dataclass
class AppState:
    _values: dict = field(default_factory=dict)

    def __getitem__(self, key):
        return self._values[key]

    def __setitem__(self, key, value):
        self._values[key] = value

    def get(self, key, default=None):
        return self._values.get(key, default)

    def setdefault(self, key, default=None):
        return self._values.setdefault(key, default)

    def update(self, values):
        self._values.update(values)

    def items(self):
        return self._values.items()

    def __contains__(self, key):
        return key in self._values

    def __getattr__(self, name):
        try:
            return self._values[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        if name == "_values":
            object.__setattr__(self, name, value)
            return
        self._values[name] = value


def deprecated(*, reason="", since=None):
    def decorator(func):
        func.__fusionframe_deprecated__ = True
        func.__fusionframe_deprecation_reason__ = reason
        func.__fusionframe_deprecation_since__ = since
        return func

    return decorator
