---
description: Investigate and fix one or more production errors using read-only Sentry data
agent: build
---

Load and follow the `sentry` skill. Use the project-scoped Sentry MCP to
investigate the request below. Correlate with local code and read-only production
diagnostics as needed. Unless the request is explicitly investigation-only, fix
an actionable application-code root cause using the mandatory test-first
`regression` workflow, then verify and report the result.

The request may contain multiple Sentry links. Extract and deduplicate every
link, treat each as a required investigation target, and follow the skill's
multi-target workflow. Do not stop after investigating the first link. If the
request is empty, select the newest unresolved production issue that is
actionable and has meaningful impact.

Sentry request:

$ARGUMENTS
