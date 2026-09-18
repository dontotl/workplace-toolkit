---
name: visit-call-report
description: Use when creating, organizing, saving, or showing a Korean customer visit, call, sales meeting, or team meeting report from notes and prior report history.
---

# Visit/Call Report

Produce a source-backed Korean Markdown report. Work from supplied notes and explicitly chosen history files or a configured report site. There is no default server or hidden network dependency.

1. Identify meeting/customer/topic and the **입력자 이름**. Do not substitute an owner or attendee for the inputter. Ask only when needed to select history and not established.
2. Select history: user-supplied JSON/CSV paths take precedence; otherwise use a report-site URL explicitly configured for this task. Without either, work from the notes and state that history was not available. Do not search parent/home directories or unrelated workspaces.
3. For a configured site, use available approved browser/connector tools, filter by inputter first, then customer/date. Prefer JSON export, CSV fallback. If inaccessible, use only a user-selected local export and disclose its age; never invent a default endpoint.
4. Read [report-standard.md](references/report-standard.md). Check exact meeting match and related initiative before reusing ID, Opportunity or confirmed metadata. Keep conflicting source values visible.
5. Save the user-requested filename, or default to `visit-call-YYYY-MM-DD-customer-topic.md` in the requested workspace, with every source header and detailed support, summary, risk, next action and history sections. Preserve an existing file unless an update is requested.
6. Read the saved file back. Return its link and the matching Markdown body in a fenced md block. Never invent facts or mark planned work completed.

Use approved Enterprise Codex for permitted business data. For local-only data, do not load notes/history into a remote model; use a local agent. Sites and CRM remain read-only unless the user separately requests a write. No accounts, credentials, source exports or private endpoints ship with this skill.

Example: `$visit-call-report Use these meeting notes and ./history.json to draft a report. Inputter: Example Author. Do not access a report site.`
