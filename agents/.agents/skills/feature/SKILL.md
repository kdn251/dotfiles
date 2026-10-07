---
name: feature
description: Use when adding a new Ferryman feature or extending product behavior. Enforces test-first development, reuse of existing domain workflows, minimal implementation, and regression verification.
---

# Feature Development

Use this workflow when adding or extending Ferryman product behavior. Carry the
feature through implementation and verification; do not stop after proposing a
design.

## Workflow

1. Define the behavior.
   - Establish the user-visible goal, acceptance criteria, boundaries, and
     expected failure behavior.
   - Resolve material ambiguity before implementation. Do not invent product
     behavior that affects users, billing, privacy, or platform output.
   - Identify which of Ferryman's sync, create, or schedule flows are affected.

2. Find and reuse existing domain logic.
   - Trace the relevant code paths before editing them.
   - Reuse established platform adapters, normalizers, posting methods,
     scheduling functions, authorization checks, and shared domain rules.
   - Compose or extend an existing domain workflow instead of creating a second
     implementation of substantial behavior such as posting to Instagram,
     normalizing a post, uploading media, enforcing platform limits, or
     scheduling delivery.
   - Do not introduce an abstraction merely to avoid repeating a trivial
     expression, assignment, database query, or one-off operation. Reuse should
     reduce duplicated domain behavior, not create indirection for its own sake.
   - If existing logic is close but not reusable, make the smallest refactor
     needed to create one shared path while preserving current behavior.

3. Add tests before production logic.
   - Add focused tests that express the feature's acceptance criteria and
     important edge cases.
   - Prefer unit tests for isolated rules and integration or adapter tests for
     behavior that crosses meaningful boundaries.
   - Run the new tests before implementing the feature and confirm they fail
     because the behavior does not yet exist. Broken fixtures, syntax errors, or
     unrelated exceptions are not valid red tests.
   - Preserve existing tests. Change existing expectations only when the feature
     intentionally changes established behavior.
   - Changes to sync, create, scheduling, posting, normalization, or supporting
     utilities require tests.
   - When platform support or outbound wire shape changes, update the adapter
     matrix intentionally and cover every required platform/post-type cell.

4. Implement the feature.
   - Make the smallest complete change that satisfies the acceptance criteria.
   - Keep one authoritative path for shared domain behavior.
   - Follow existing architecture, error handling, types, and UI patterns.
   - Avoid speculative compatibility code, unrelated cleanup, and premature
     abstractions.

5. Verify behavior and regressions.
   - Rerun the new focused tests and confirm they pass.
   - Run tests around every reused or modified workflow to ensure existing
     behavior remains intact.
   - Run the relevant broader suite, including adapter tests when egress behavior
     is involved.
   - Run lint, type checks, or a build when warranted by the changed area.

## Completion Report

Always tell the user:

- What behavior was added.
- Which existing domain logic was reused or extended, and how duplication was
  avoided.
- Which tests were added and how they failed before implementation.
- Which focused and broader checks passed after implementation.

Never claim test-first coverage unless the new tests were observed failing
before the production implementation and passing afterward.
