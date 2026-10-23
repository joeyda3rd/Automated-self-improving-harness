"""The supervisor: one long-lived, single-instance loop that drives everything.

    ash daemon [-C PROJECT]            run in the foreground
    ash daemon --ensure [-C PROJECT]   start it in the background unless one is already alive
    ash daemon enable|disable          opt in/out of auto-start (the SessionStart hook calls --ensure)
    ash daemon stop                    ask the running daemon to stop after its current step

Liveness is an exclusive flock on state/daemon.lock: the kernel drops it when the process
dies, so a crash or a container restart can never leave a lock that looks alive. The
daemon writes a heartbeat to state/daemon.json; `ash status` reports both.

Each iteration: build one ready task (if a project is attached), else run an improvement
cycle when one is due and the remaining budget covers a full cycle, else sleep.
Interrupted benchmarks resume from saved runs, so restarting is always safe.
"""
import fcntl
import json
import os
import signal
import subprocess
import sys
import threading
import time

from . import claude, engine, evals, improve
from .config import save_json
from .tasks import TaskStore


def paths(harness):
    return (os.path.join(harness.state, "daemon.lock"), os.path.join(harness.state, "daemon.json"),
            os.path.join(harness.state, "daemon.enabled"))


def acquire(harness):
    """Take the single-instance lock; returns the open file (keep it) or None if another daemon holds it."""
    lock_path = paths(harness)[0]
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    fh = open(lock_path, "a+")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return None
    return fh


def alive(harness):
    fh = acquire(harness)
    if fh is None:
        return True
    fh.close()
    return False


def status(harness):
    """{'alive': bool, ...last heartbeat fields}."""
    info = {}
    try:
        with open(paths(harness)[1]) as fh:
            info = json.load(fh)
    except (OSError, ValueError):
        pass
    info["alive"] = alive(harness)
    info["enabled"] = os.path.exists(paths(harness)[2])
    if info.get("heartbeat"):
        info["heartbeat_age_s"] = round(time.time() - info["heartbeat"])
    return info


class Daemon:
    def __init__(self, harness, project=None, max_iterations=None, idle_sleep=None):
        self.h, self.project, self.max_iterations = harness, project, max_iterations
        self.idle_sleep = harness.get("idle_sleep_seconds", 60) if idle_sleep is None else idle_sleep
        self.stopping = False
        self._beat_lock = threading.Lock()
        self.state = {"pid": os.getpid(), "started": time.time(), "phase": "starting",
                      "project": project.root if project else None, "iterations": 0, "last": None}

    def beat(self, **fields):
        with self._beat_lock:  # the heartbeat thread and the loop both write daemon.json
            self.state.update(fields, heartbeat=time.time())
            save_json(paths(self.h)[1], self.state)

    def improvement_due(self):
        if not evals.gate_set(self.h):
            return False
        left = claude.remaining(self.h)
        if left is not None and left < self.h.get("min_cycle_budget_usd", 12):
            return False
        every = self.h.get("improve_every", 0)
        if self.project and every:
            return engine.builds_since_improvement(self.h) >= every
        return bool(self.h.get("improve_when_idle", True))

    def step(self):
        """One unit of work. Returns what it did."""
        for flag in ("STOP", "PAUSED"):
            if os.path.exists(os.path.join(self.h.state, flag)):
                return f"halted:{flag}"
        if self.project:
            store = TaskStore(self.project)
            engine.intake_inbox(self.project)
            if store.ready():
                self.beat(phase="building")
                engine.run_task(self.h, self.project, store.ready()[0])
                return "built"
        if self.improvement_due():
            self.beat(phase="improving")
            improve.cycle(self.h)
            return "improved"
        return "idle"

    def run(self):
        lock = acquire(self.h)
        if lock is None:
            print("ash daemon: another daemon is already running", file=sys.stderr)
            return 1
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "stopping", True))
        stop_ticker = threading.Event()
        ticker = threading.Thread(target=lambda: [self.beat() for _ in iter(lambda: stop_ticker.wait(30), True)],
                                  daemon=True)
        self.beat(phase="running")
        ticker.start()
        try:
            while not self.stopping:
                try:
                    did = self.step()
                except claude.BudgetExceeded as exc:
                    did = f"halted:budget ({exc})"
                except Exception as exc:  # keep supervising; the error is in the heartbeat
                    did = f"error: {exc!r}"
                self.state["iterations"] += 1
                self.beat(phase="running", last=did)
                print(f"[ash daemon {time.strftime('%H:%M:%S')}] {did}", flush=True)
                if did.startswith("halted"):
                    break
                if self.max_iterations and self.state["iterations"] >= self.max_iterations:
                    break
                if did in ("idle",) or did.startswith("error"):
                    for _ in range(int(self.idle_sleep)):
                        if self.stopping:
                            break
                        time.sleep(1)
        finally:
            stop_ticker.set()
            self.beat(phase="stopped")
            lock.close()
        return 0


def ensure(harness, project_root=None):
    """Start a background daemon unless one is alive. Idempotent; safe to call from hooks."""
    if alive(harness):
        return "already running"
    log = open(os.path.join(harness.state, "daemon.log"), "a")
    cmd = [os.path.join(harness.home, "bin", "ash")]
    if project_root:
        cmd += ["-C", project_root]
    cmd += ["daemon"]
    subprocess.Popen(cmd, stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True,
                     cwd=harness.home)
    return "started"


def request_stop(harness):
    info = status(harness)
    if not info["alive"] or not info.get("pid"):
        return "not running"
    os.kill(info["pid"], signal.SIGTERM)
    return f"asked pid {info['pid']} to stop after its current step"
