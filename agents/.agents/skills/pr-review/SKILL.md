---
name: pr-review
description: Review a PR or current branch diff for bugs, security issues, and quality. Runs in isolated context to avoid bias.
context: fork
---

Review code changes with a critical eye. You are an independent reviewer — assume nothing about the code's correctness.

## 1. Get the diff

- If `$ARGUMENTS` is provided (a PR number like `9` or `#9`, or a URL), fetch the diff with `gh pr diff $ARGUMENTS`
- If no arguments, review the current branch against main: `git diff main...HEAD`

Also read the full files that were changed for surrounding context — don't review the diff in isolation.

## 2. Analyze

Review the changes for:

- **Bugs** — logic errors, off-by-one, null/undefined risks, race conditions, unhandled edge cases
- **Security** — injection, auth bypasses, hardcoded secrets, missing input validation, token handling
- **Quality** — dead code, missing error handling, unclear naming, untested code paths
- **Consistency** — does the new code follow existing patterns in the codebase?

Do NOT nitpick style, formatting, or trivial naming preferences. Focus on things that could break in production.

## 3. Output

Structure your review as:

### Critical (must fix before merging)
List anything that would cause bugs, security issues, or data loss. If none, say "None found."

### Suggestions (worth considering)
Improvements that aren't blocking but would make the code better.

### Looks good
Briefly note what's solid — this helps the author know what to keep doing.

Keep the review concise and actionable.
