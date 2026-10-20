---
name: verify
description: Run the project's verification (tests, type-check, lint, build) the way the ASH stop gate will, and interpret failures. Use before declaring any task done.
---

# Verify

- The authoritative command is in the environment as `$ASH_VERIFY_CMD` (also shown at session start). Run exactly that: `bash -c "$ASH_VERIFY_CMD"`.
- If it is unset, find the project's own checks (test runner, type-checker, linter, build) and run all that exist.
- Read failures from the top: the first error is usually the cause, later ones are fallout.
- A flaky failure is still a failure: re-run once; if it flips, make the test deterministic rather than retrying until green.
- Never edit a test to match broken behaviour. Changing a test is only correct when the task changes the specified behaviour, and then the task card must say so.
