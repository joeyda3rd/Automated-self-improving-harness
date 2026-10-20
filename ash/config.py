"""Paths and configuration for the harness and for the project it is building."""
import json
import os
import re
from dataclasses import dataclass, field

HOME = os.environ.get("ASH_HOME") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def append_jsonl(path, record):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def read_jsonl(path):
    out = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass
    except OSError:
        pass
    return out


@dataclass
class Harness:
    """The harness installation: kernel code, the evolvable plugin, and its memory."""
    home: str = HOME
    cfg: dict = field(default_factory=dict)

    @classmethod
    def load(cls, home=None):
        home = os.path.abspath(home or HOME)
        cfg = load_json(os.path.join(home, "harness.json"), {}) or {}
        return cls(home=home, cfg=cfg)

    def get(self, key, default=None):
        value = self.cfg.get(key)
        return default if value is None else value

    @property
    def plugin_dir(self):
        return os.path.join(self.home, "plugin")

    @property
    def state(self):
        return os.path.join(self.home, "state")

    @property
    def runs_dir(self):
        return os.path.join(self.state, "runs")

    @property
    def learnings(self):
        return os.path.join(self.state, "learnings.md")

    @property
    def metrics(self):
        return os.path.join(self.state, "metrics.jsonl")

    @property
    def improvements(self):
        return os.path.join(self.state, "improvements.jsonl")

    @property
    def evals_dir(self):
        return os.path.join(self.home, "evals", "tasks")

    @property
    def claude_bin(self):
        return os.environ.get("ASH_CLAUDE_BIN") or self.get("claude_bin", "claude")


@dataclass
class Project:
    """A software project the harness has been assigned. State lives in <root>/.ash/."""
    root: str

    @property
    def ash(self):
        return os.path.join(self.root, ".ash")

    @property
    def tasks_dir(self):
        return os.path.join(self.ash, "tasks")

    @property
    def inbox(self):
        return os.path.join(self.ash, "inbox")

    @property
    def worktrees(self):
        return os.path.join(self.ash, "worktrees")

    @property
    def config_path(self):
        return os.path.join(self.ash, "project.json")

    @property
    def config(self):
        return load_json(self.config_path, {}) or {}

    def set_config(self, **updates):
        cfg = self.config
        cfg.update({k: v for k, v in updates.items() if v is not None})
        save_json(self.config_path, cfg)

    @property
    def verify_cmd(self):
        return self.config.get("verify_cmd") or ""

    @property
    def base_branch(self):
        return self.config.get("base_branch") or "main"

    @property
    def slug(self):
        return re.sub(r"[^A-Za-z0-9_.-]+", "-", os.path.abspath(self.root)).strip("-")[-80:]

    def lessons_path(self, harness):
        return os.path.join(harness.state, "projects", self.slug, "learnings.md")
