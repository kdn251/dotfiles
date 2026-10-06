---
description: Reproduce and record a bug, fix it with regression tests, and open a PR with before-and-after videos
agent: build
---

Load and follow the `fix` skill. Treat the following as the bug report. Carry the
work through browser reproduction and a before recording, a regression test
observed failing, the root-cause fix, passing verification, and an after recording
of the same browser flow. Publish both recordings at working boole URLs and
commit, push a fix branch, and create a PR linking the recordings and test results.
This invocation explicitly requests those Git and PR actions. Do not merge the PR.

Bug report:

$ARGUMENTS
