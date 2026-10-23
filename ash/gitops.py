"""The git plumbing the orchestrator owns: worktrees per task, commits, integration."""
import os
import shutil
import subprocess


class GitError(RuntimeError):
    pass


def git(cwd, *args, check=True):
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout.strip()


def is_repo(path):
    return subprocess.run(["git", "rev-parse", "--git-dir"], cwd=path,
                          capture_output=True).returncode == 0


def ensure_repo(path, base_branch="main"):
    """Make `path` a git repository with at least one commit on `base_branch`."""
    os.makedirs(path, exist_ok=True)
    if not is_repo(path):
        git(path, "init", "-q", "-b", base_branch)
    if not git(path, "rev-parse", "--verify", "-q", "HEAD", check=False):
        git(path, "add", "-A")
        git(path, "-c", "user.name=ASH", "-c", "user.email=ash@localhost",
            "commit", "-q", "--allow-empty", "-m", "ASH: initial commit")


def current_branch(path):
    return git(path, "rev-parse", "--abbrev-ref", "HEAD")


def head(path):
    return git(path, "rev-parse", "HEAD")


def add_worktree(repo, path, branch, base):
    remove_worktree(repo, path, branch)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    git(repo, "worktree", "add", "-q", "-b", branch, path, base)


def remove_worktree(repo, path, branch=None):
    if os.path.exists(path):
        git(repo, "worktree", "remove", "--force", path, check=False)
        shutil.rmtree(path, ignore_errors=True)
    git(repo, "worktree", "prune", check=False)
    if branch:
        git(repo, "branch", "-D", branch, check=False)


# Build artefacts never belong in a commit, even in projects without a .gitignore.
ARTIFACTS = ["__pycache__", "*.pyc", "*.pyo", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules",
             ".venv", "venv", "*.egg-info", ".tox", ".coverage", "htmlcov", ".DS_Store"]
DEFAULT_GITIGNORE = "\n".join(ARTIFACTS + ["dist/", "build/"]) + "\n"


def commit_all(path, message):
    """Commit everything in the worktree except build artefacts. Returns False when nothing to commit."""
    git(path, "add", "-A", "--", ".", *[f":(exclude,glob)**/{a}" for a in ARTIFACTS],
        *[f":(exclude,glob)**/{a}/**" for a in ARTIFACTS if "*" not in a])
    if not git(path, "diff", "--cached", "--name-only"):
        return False  # nothing staged (possibly only artefacts changed)
    git(path, "-c", "user.name=ASH", "-c", "user.email=ash@localhost", "commit", "-q", "-m", message)
    return True


def changed_files(path, base):
    """Files that differ between `base` and the working tree, committed or not."""
    git(path, "add", "-A")
    out = git(path, "diff", "--name-only", "--cached", base)
    return [f for f in out.splitlines() if f]


def merge(repo, branch, message):
    """Merge `branch` into the repo's checked-out branch. Returns False (and aborts) on conflict."""
    proc = subprocess.run(["git", "-c", "user.name=ASH", "-c", "user.email=ash@localhost",
                           "merge", "--no-ff", "-q", "-m", message, branch],
                          cwd=repo, capture_output=True, text=True)
    if proc.returncode != 0:
        git(repo, "merge", "--abort", check=False)
        return False
    return True
