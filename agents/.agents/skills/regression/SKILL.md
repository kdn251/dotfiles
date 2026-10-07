---
name: regression
description: Use when fixing a regression, recurring bug, previously working behavior, or bug that needs a reproducing test and root-cause fix. Enforces a test-first red-green workflow before production logic changes.
---

# Regression Fix

Use this workflow for regressions and recurring bugs. Do not skip or reorder the
failing-test and implementation steps.

## Workflow

1. Reproduce and identify the root cause.
   - Establish the expected behavior and the actual behavior.
   - Trace the behavior through the relevant code before editing it.
   - Identify the specific incorrect assumption, branch, state transition, or
     integration boundary responsible for the regression.
   - Distinguish the root cause from downstream symptoms.

2. Add the regression test first.
   - Add the smallest deterministic test that reproduces the reported behavior.
   - Prefer a unit test at the layer containing the bug. Use an integration test
     only when the behavior cannot be proven meaningfully at unit level.
   - Exercise the public behavior rather than duplicating implementation details.
   - Run the new test before changing production logic.
   - Confirm it fails for the expected behavioral reason. A syntax error, broken
     fixture, unrelated exception, or incorrect expectation is not a valid red
     test.
   - If a useful reproducing test is not feasible, stop and explain the blocker
     before changing production logic.

3. Fix the root cause.
   - Make the smallest correct production change.
   - Do not weaken the test, change its expected behavior, or add a special case
     that only satisfies the fixture.
   - Preserve unrelated behavior and existing user changes.

4. Prove the fix.
   - Rerun the exact regression test and confirm it passes.
   - Run the relevant surrounding test file or suite to detect collateral
     regressions.
   - Run lint or type checks when the changed area warrants them.

## Completion Report

Report:

- The root cause.
- The regression test added and how it failed before the fix.
- The production change.
- The focused and broader verification results.

Never claim regression coverage unless the new test was observed failing before
the production fix and passing afterward.
