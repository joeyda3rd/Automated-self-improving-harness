"""Lesson memory: short, deduplicated, capped lists injected into every session."""
import os
import re
import time


def _norm(text):
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def read_lessons(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return [l.rstrip("\n") for l in fh if l.startswith("- ")]
    except OSError:
        return []


def add_lessons(path, lessons, source, cap=60):
    """Append new lessons (skipping near-duplicates) and keep only the newest `cap`."""
    existing = read_lessons(path)
    seen = {_norm(re.sub(r"^- \[[^\]]*\] ", "", l).rsplit(" (from ", 1)[0]) for l in existing}
    added = []
    for text in lessons:
        text = " ".join(text.split())
        if not text or _norm(text) in seen:
            continue
        seen.add(_norm(text))
        added.append(f"- [{time.strftime('%Y-%m-%d')}] {text} (from {source})")
    if added:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join((existing + added)[-cap:]) + "\n")
    return added
