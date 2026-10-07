---
name: push
description: Stage, commit, push, and create a PR with conventional commits. Safe by default — creates a branch if on main.
disable-model-invocation: true
---

Push the current changes safely. Follow these steps in order:

## 1. Check branch

Run `git branch --show-current`. If on `main`, create and switch to a new descriptive branch (e.g., `feat/update-claude-md`, `fix/token-refresh`). If already on a feature branch, stay on it.

## 2. Stage changes

Run `git status` and `git diff` to review all changes. Stage only the files related to the current work. Do not stage unrelated files.

## 3. Commit

If the user provided arguments (`$ARGUMENTS`), use that as the commit message verbatim.

If no arguments were provided, auto-generate a commit message by analyzing the staged diff. Use conventional commit format:

- `feat:` — new feature
- `fix:` — bug fix
- `chore:` — maintenance, deps, config
- `refactor:` — code restructuring
- `docs:` — documentation only
- `test:` — adding or updating tests

Keep the message short (under 72 chars) and descriptive. Focus on *what* changed, not *how*.

## 4. Push

Push to remote with `git push -u origin <branch-name>`.

## 5. Create PR

Create a pull request using `gh pr create`. Use the commit message as the PR title. Write a brief summary in the PR body describing what changed and why.

Format:
```
gh pr create --title "<title>" --body "$(cat <<'EOF'
## Summary
<1-3 bullet points>

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Return the PR URL when done.
