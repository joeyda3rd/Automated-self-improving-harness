---
name: plan-work
description: Decompose an ASH assignment into small, ordered, independently verifiable build tasks. Use when acting as the ASH planner.
---

# Plan work

1. Read the assignment and survey the repository (structure, stack, existing tests, `.ash/notes.md`).
2. If the repository is empty, the first task is a walking skeleton: project scaffold, one passing test, and a working verification command.
3. Split the work into tasks a single focused session can finish in well under an hour. Each task must have:
   - `title`: imperative, specific.
   - `spec`: what to build, where, and any constraints. Self-contained: the builder sees only this card and the repo.
   - `acceptance`: a list of observable checks (preferably tests that will exist when it is done).
   - `depends_on`: indexes (0-based, into your own list) of tasks that must land first.
   - `priority`: 1 (highest) to 5.
4. Prefer vertical slices that leave the build green after every task. Avoid tasks that only "add tests" or only "refactor" unless the assignment asks for that.
5. If the project's verification command should change (e.g. a new test runner), say so in `verify_cmd`; otherwise leave it empty.
