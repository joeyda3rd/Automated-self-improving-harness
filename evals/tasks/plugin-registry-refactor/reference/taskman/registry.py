"""Command registry shared by every entry point."""
import itertools
from dataclasses import dataclass


class CommandConflictError(ValueError):
    pass


class UnknownCommandError(LookupError):
    pass


@dataclass(frozen=True)
class Command:
    name: str
    func: object
    usage: str
    summary: str
    aliases: tuple = ()
    order: int = 100


class Registry:
    def __init__(self):
        self._commands = {}   # name -> (seq, Command)
        self._lookup = {}     # name or alias -> name
        self._seq = itertools.count()

    def register(self, name, func, *, usage, summary, aliases=(), order=100):
        aliases = tuple(aliases)
        words = (name,) + aliases
        if len(set(words)) != len(words):
            raise CommandConflictError(f"duplicate name or alias in {words}")
        for w in words:
            if w in self._lookup:
                raise CommandConflictError(f"command name or alias already registered: {w}")
        cmd = Command(name, func, usage, summary, aliases, order)
        self._commands[name] = (next(self._seq), cmd)
        for w in words:
            self._lookup[w] = name
        return cmd

    def command(self, name, *, usage, summary, aliases=(), order=100):
        def decorate(func):
            self.register(name, func, usage=usage, summary=summary, aliases=aliases, order=order)
            return func
        return decorate

    def unregister(self, name):
        if name not in self._commands:
            raise UnknownCommandError(name)
        _, cmd = self._commands.pop(name)
        for w in (cmd.name,) + cmd.aliases:
            del self._lookup[w]

    def resolve(self, name):
        try:
            return self._commands[self._lookup[name]][1]
        except (KeyError, TypeError):
            raise UnknownCommandError(name) from None

    def commands(self):
        return [cmd for _, cmd in sorted(self._commands.values(), key=lambda sc: (sc[1].order, sc[0]))]

    def __contains__(self, name):
        try:
            return name in self._lookup
        except TypeError:
            return False


registry = Registry()
