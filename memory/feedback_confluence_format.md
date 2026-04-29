---
name: Confluence page format preference
description: User prefers plain markdown for Confluence pages — no page properties macros, no ADF, no complex formatting
type: feedback
---

When creating Confluence pages, use **markdown format** (`contentFormat: "markdown"`).

- Do not use page properties macros, TOC macros, or other Confluence-specific ADF constructs.
- Do not use ADF JSON or HTML format unless explicitly requested.
- Simple headings, tables, bullet lists, and code spans are sufficient.
- The `atlassian_createConfluencePage` tool accepts `contentFormat: "markdown"` — use this by default.

**Why:** User explicitly said "use markdown for this doc, I don't need page properties or things that go beyond markdown formatting."
