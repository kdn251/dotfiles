---
name: fix
description: Use for /fix or an explicit request to fix a bug with before-and-after browser recordings, test-first regression coverage, boole video links, and a pull request.
---

# Fix with browser evidence

Deliver a reproduced bug, a root-cause fix protected by unit tests, two recordings
of the same end-user flow, and a reviewable PR linking both recordings. Follow
these steps in order. A recording supplements assertions; it does not replace them.

## 1. Establish the baseline and browser flow

- Read the bug report and repository instructions. State the expected and actual
  behavior. Ask only for missing information that blocks reproduction.
- Inspect Git status before changes. Follow the repository's branch policy: start
  from updated main unless directed otherwise, preserve unrelated work, and put
  the completed fix on a descriptive branch before committing and pushing.
  Do not displace another active worktree or reset user changes to obtain main.
- Prefer the local app on boole. Inspect the existing server, checkout, origin,
  and account access before starting another server. Reuse the running server
  when appropriate and ensure it serves the checkout being tested.
- Use Playwright with a real browser. Check for an existing installation and
  cached browser before installing anything. Reuse repository tooling; if none
  exists, bootstrap in the approved external temporary directory. Keep the
  regression scenario in the repository when adding durable browser coverage.
- Define the exact steps, initial account/data state, viewport, and observable
  failure. Capture these in one reusable browser scenario for both runs.
- Use fixture accounts and isolated data where available. Control external
  responses only at necessary boundaries, preserving the real UI and relevant
  application logic. Record any simulation in the evidence and PR. Do not fake
  the broken UI or its corrected result to manufacture evidence.
- Do not send real posts or run other live side effects merely to demonstrate
  a fix without the user's explicit authorization. Keep sessions, credentials,
  and private user data out of published artifacts.

## 2. Reproduce and record BEFORE changing production logic

- Start viewport video recording before the relevant browser interaction.
  Follow the user flow through the actual page, including relevant clicks,
  typing, uploads, navigation, and waiting for background work.
- Observe the reported failure and save `before.webm` in a unique run directory.
  Preserve the failing state briefly so the viewer can see it. Capture an
  assertion failure for the expected correct behavior where practical.
- Save a small evidence manifest: baseline Git SHA and any uncommitted changes,
  app URL, viewport, scenario/fixture identifiers, steps, expected result,
  observed result, simulations, and recording filename. Do not include secrets.
- Close the browser context and await recording finalization, including when
  the expected assertion fails. Preserve the assertion outcome rather than
  treating any exception as proof of the bug.
- Verify the video is nonempty, decodable, and actually shows the failure.
  Inspect representative frames or playback, not only the file's existence.
- If reproduction or recording is blocked, report the concrete blocker. Do not
  change production logic first and later invent a before recording. Never
  claim reproduction based only on a suspected code path or unrelated error.

## 3. Add a failing unit regression test, then fix the cause

- Load and follow the `regression` skill for the red-green discipline.
- Trace the observed behavior to its root cause. Add a deterministic unit test
  at the responsible layer before changing production logic. Assert public
  behavior and the expected correct result, not implementation details.
- Run the new test and observe it fail for the bug's behavioral reason. Broken
  setup, syntax errors, and unrelated exceptions do not count as a red result.
- If a unit test cannot meaningfully cover the defect, explain why and establish
  meaningful integration/browser regression coverage before proceeding; do not
  add a token unit test or silently claim the unit-test requirement was met.
- Make the smallest robust root-cause fix using existing domain workflows.
  Do not weaken expectations, bypass behavior, or special-case the fixture.
- Run the exact new test again, then relevant surrounding tests and required
  lint/type checks. For sync, posting, and scheduling, follow the repository's
  core-flow and adapter verification requirements.
- Preserve useful browser coverage for UI or asynchronous behavior that unit
  tests cannot protect. Keep recording waits out of fast unit tests.

## 4. Record the SAME flow after the fix

- Ensure the tested server has loaded the changed code. Restore equivalent
  initial data/session state, viewport, timing controls, and external response
  scenario. Successful setup during the before run must not accidentally
  remove the bug's triggering conditions from the after run.
- Run the same actions against the fixed app and save `after.webm`. Keep the
  scenario unchanged except for assertions needed to distinguish the known
  baseline failure from the corrected outcome. Never substitute an easier flow.
- Assert the expected result and relevant persistent state, not just the absence
  of an exception. For retries, permissions, or background jobs, verify the
  relevant final outcome and absence of duplicate side effects.
- Finalize and inspect the recording. Update the evidence manifest with the
  fixed revision or working-tree state and verification results. If the bug
  remains, continue debugging rather than presenting the clip as successful.

## 5. Publish reviewable recordings on boole

- Reuse an existing artifact viewer/server when available. Inspect its actual
  document root and listening port; do not assume the homepage demo's server
  still exists or that a chosen port is free.
- Put each run under a unique, stable URL, for example
  `http://boole:<artifact-port>/fix/<run-id>/`. Never overwrite an older run.
- Serve only intended review artifacts from a dedicated artifact root, not the
  repository, environment files, browser profiles, or authenticated storage state.
  Keep finalized videos available for the PR review period rather than deleting
  them when a test's temporary directory is cleaned up.
- Provide a simple HTML page with clearly labeled Before and After video players,
  direct download links, reproduction steps, and expected/observed behavior.
  Use relative media links so the viewer works through the same reachable origin.
- Keep the viewer alive independently of a foreground tool timeout. If using
  Herdr, load its control instructions and follow the user's requested topology.
  Do not stop unrelated servers or tabs. Reuse a persistent viewer process.
- Check that the index and both media URLs return success, load metadata in a
  browser, and inspect frames/playback. Use a boole hostname URL in delivery,
  not a localhost URL that would target the user's laptop. Clearly disclose if
  reachability was verified only from boole, not from the user's computer.
- These links are private-network review links, not GitHub video uploads. Note
  that reviewers need access to boole. Do not claim they are publicly accessible.

## 6. Commit, push, and create the PR

- `/fix` explicitly requests a commit, branch push, and PR, but not a merge.
  If this skill was loaded outside `/fix`, confirm the user requested those Git
  actions before executing them.
- Inspect status, diff, and `git log --oneline -10`. Stage only intended source,
  tests, and necessary tooling; do not commit recordings, credentials, or session
  artifacts. Use a concise conventional commit matching repository style.
- Honor hooks. In this repository, rely on the pre-commit hook for the full test
  suite instead of manually running it immediately before committing. Fix
  failures and retry normally; never bypass hooks or push failing verification.
- Before creating the PR, inspect remote tracking, all included commits, and
  the complete diff against the base branch. Use `gh` to create the PR. Include:
  - The bug, root cause, and fix.
  - Exact reproduction steps and any fixture/simulation limitations.
  - The shared viewer URL and separate Before and After recording URLs.
  - The test observed failing before and passing afterward, and other checks.
  - Any intentional adapter wire-shape changes.
- Verify the PR contains working recording links. Return the PR URL, viewer
  URL, Before/After links, and a concise verification summary to the user.
  Report incomplete or blocked deliverables explicitly; do not claim completion
  unless reproduction, tests, recordings, publishing, and PR creation succeeded.

## Keep the feedback loop fast

- Reuse installed browsers, app servers, and the artifact viewer. Do not rebuild
  the delivery infrastructure for each bug.
- Prefer focused 10-30 second clips when the behavior permits. Wait for visible
  states instead of arbitrary long sleeps; allow short pauses for readability.
  Longer jobs may legitimately require longer recordings.
- Share Playwright's native WebM first. Convert to MP4 only if playback requires
  it or the user requests it. Do not block delivery on optional conversion.
- Set explicit navigation/action deadlines and an overall command timeout that
  includes setup, the flow, and video finalization. Use try/finally cleanup so a
  known failing assertion still saves its recording.
- Track setup, reproduction, finalization, and publishing durations. On failure,
  inspect and salvage valid artifacts before repeating an entire browser run.
