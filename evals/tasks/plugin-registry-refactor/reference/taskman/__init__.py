"""taskman: a small task tracker with a CLI, an HTTP-style handler and a batch runner."""
__version__ = "0.9.0"

from . import commands  # noqa: E402,F401  (registers the built-in commands)
