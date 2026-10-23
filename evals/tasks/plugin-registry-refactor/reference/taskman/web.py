"""HTTP-style entry point: handle(request, store) -> response.

request:  {"method": "GET" | "POST", "path": str, "body": dict or None}
response: {"status": int, "body": dict}

Routes:
  GET  /commands         list the available commands
  POST /commands/<name>  run a command; body {"args": [str, ...]}
"""
from .errors import TaskmanError
from .registry import UnknownCommandError, registry

STATUS = {"usage": 400, "validation": 400, "not_found": 404, "conflict": 409}
PREFIX = "/commands/"


def _error(status, message, kind=None):
    body = {"error": message}
    if kind:
        body["kind"] = kind
    return {"status": status, "body": body}


def handle(request, store):
    method = (request.get("method") or "GET").upper()
    path = request.get("path") or "/"
    if path == "/commands":
        if method != "GET":
            return _error(405, "method not allowed")
        return {"status": 200, "body": {"commands": [
            {"name": c.name, "aliases": list(c.aliases), "usage": c.usage, "summary": c.summary}
            for c in registry.commands()
        ]}}
    if not path.startswith(PREFIX) or len(path) == len(PREFIX):
        return _error(404, f"no route: {method} {path}")
    if method != "POST":
        return _error(405, "method not allowed")
    name = path[len(PREFIX):]
    body = request.get("body")
    if body is None:
        body = {}
    args = body.get("args", []) if isinstance(body, dict) else None
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        return _error(400, "body.args must be a list of strings")
    try:
        cmd = registry.resolve(name)
    except UnknownCommandError:
        return _error(404, f"unknown command: {name}")
    try:
        out = cmd.func(store, args)
    except TaskmanError as e:
        return _error(STATUS.get(e.kind, 500), e.message, e.kind)
    return {"status": 200, "body": {"output": out, "lines": out.splitlines()}}
