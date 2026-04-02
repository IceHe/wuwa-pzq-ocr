from importlib import import_module

__all__ = ["create_app"]


def __getattr__(name: str):
    if name == "create_app":
        return import_module(".app", __name__).create_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
