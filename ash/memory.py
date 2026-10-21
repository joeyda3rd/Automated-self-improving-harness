"""Lesson memory: short, deduplicated, capped lists injected into every session.

Memory that only grows degrades: bad lessons get copied and compound. So every
lesson has a stable id, each run records which lessons it was given, the
retrospective rates them, and `curate` deletes lessons with a poor track record.
"""
import hashlib
import os
import re
import time

from .config import append_jsonl, read_jsonl

INJECTED_PER_FILE = 30  # must match what the SessionStart hook injects (tail_lines(f, 30))
LINE = re.compile(r"^- (?:\[(L-[0-9a-f]{6})\] )?(?:\[[0-9-]+\] )?(.*?)(?: \(from [^)]*\))?$")


def _norm(text):
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def lesson_id(text):
    return "L-" + hashlib.sha1(_norm(text).encode()).hexdigest()[:6]


def parse(line):
    """(id, text) of a lesson line; old lines without an id get the id of their text."""
    m = LINE.match(line)
    text = m.group(2) if m else line[2:]
    return (m.group(1) if m and m.group(1) else lesson_id(text)), text


def read_lessons(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return [l.rstrip("\n") for l in fh if l.startswith("- ")]
    except OSError:
        return []


def _write(path, lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + ("\n" if lines else ""))


def add_lessons(path, lessons, source, cap=60):
    """Append new lessons (skipping near-duplicates) and keep only the newest `cap`."""
    existing = read_lessons(path)
    seen = {parse(l)[0] for l in existing}
    added = []
    for text in lessons:
        text = " ".join(text.split())
        if not text or lesson_id(text) in seen:
            continue
        seen.add(lesson_id(text))
        added.append(f"- [{lesson_id(text)}] [{time.strftime('%Y-%m-%d')}] {text} (from {source})")
    if added:
        _write(path, (existing + added)[-cap:])
    return added


def injected(paths):
    """Ids of the lessons a session starting now is given."""
    return [parse(l)[0] for p in paths for l in read_lessons(p)[-INJECTED_PER_FILE:]]


def curate(harness, paths, min_uses=6, margin=0.25):
    """Delete lessons whose sessions do clearly worse than average, or that retros call harmful."""
    builds = [r for r in read_jsonl(harness.metrics) if r.get("kind") == "build" and "lessons" in r]
    if builds:
        overall = sum(r["outcome"] == "done" for r in builds) / len(builds)
    stats = {}
    for r in builds:
        for lid in r["lessons"]:
            s = stats.setdefault(lid, [0, 0])
            s[0] += 1
            s[1] += r["outcome"] == "done"
    votes = {}
    for v in read_jsonl(os.path.join(harness.state, "lesson_votes.jsonl")):
        votes.setdefault(v["id"], []).append(v["verdict"])

    def why_bad(lid):
        uses, wins = stats.get(lid, (0, 0))
        if uses >= min_uses and wins / uses < overall - margin:
            return f"sessions given it succeeded {wins}/{uses} vs {overall:.0%} overall"
        harmful, helpful = votes.get(lid, []).count("harmful"), votes.get(lid, []).count("helpful")
        if harmful >= 2 and harmful > helpful:
            return f"rated harmful {harmful}x, helpful {helpful}x by retrospectives"
        return None

    removed = []
    for path in paths:
        keep = []
        for line in read_lessons(path):
            reason = why_bad(parse(line)[0])
            if reason:
                removed.append(line)
                append_jsonl(os.path.join(harness.state, "lessons_pruned.jsonl"),
                             {"ts": time.time(), "lesson": line, "reason": reason})
            else:
                keep.append(line)
        if len(keep) != len(read_lessons(path)):
            _write(path, keep)
    return removed
