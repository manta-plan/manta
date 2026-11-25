<!--
SPDX-FileCopyrightText: datarecord contributors
SPDX-FileCopyrightText: 2026 Manta contributors

SPDX-License-Identifier: CC-BY-4.0

Adapted from AGENTS.md in datarecord by datarecord contributors,
https://github.com/energy-models/datarecord/blob/8955d765657ce3802307d1aa3936063c59f19e32/AGENTS.md
Licensed under CC BY 4.0: https://creativecommons.org/licenses/by/4.0/
This file is modified from the original.
-->

# Agent Development Guide for Manta

For the general contribution workflow, project conventions and architecture overview, follow [`CONTRIBUTING.md`](CONTRIBUTING.md).

## AI-assisted contributions

Before writing any PR, issue, or comment, read and follow [AI-assisted contributions](CONTRIBUTING.md#ai-assisted-contributions).
Mark everything you generate, leave a placeholder for the human's own intent instead of writing it, and never reply in a discussion on the human's behalf.

A PR body starts from the [PR template](.github/pull_request_template.md).
Fill in its sections and keep its headings, checkboxes, and comments, rather than replacing it with a structure of your own.

## Comments

**No explanatory inline comments** — logic that needs explaining becomes a helper whose docstring carries the sentence:

```python
# no
dead = _dead_labels(held, axis, dim)  # None, not empty, so _living adds no join

# yes — the sentence lives in _dead_labels's docstring
dead = _dead_labels(held, axis, dim)
```

What stays inline, because it belongs where the eye lands rather than in a docstring nobody opens:

- **A justification of a line that reads as a mistake** — a swallowed exception, a magic literal, a deliberate no-op, a slower construct chosen over the obvious fast one.
  `files.py`'s note on why an HTTP 403 counts as a missing object, and `protocols.py`'s on why `__contains__` is overridden, are the model: they answer "why not the obvious thing", which no reader can recover from the code.
  Keep them as short as the reason allows — a couple of lines where the reason genuinely takes that, not a paragraph.
- **A case label** where parametrizing the test would distort it.
- **Pragmas with their reason** (`# type: ignore[…]`, `# noqa: …`, `# fmt: skip`), `#:` attribute docs, and section banners.

**Put the claim in the message that prints** — the assertion message in a test, the error text in the code.
A comment is read by whoever already found the line, a message by whoever hit it:

```python
# no
assert names == ["Manchester Wind", "Norway Gas"]  # member order, not sorted

# yes
assert names == ["Manchester Wind", "Norway Gas"], "members keep record order"
```

## Running the tests and other long runs

Redirect tests and other long runs to a file and grep the file instead.
Start it in the background with its output in a log, and do the next piece of work while it goes or simply wait for it to finish.
Do not watch it: no polling, no repeated `tail` of the log, no `sleep` loop.
Read the log once, after the run has exited.

## Issues

Label from the existing set — `gh label list` shows them and their descriptions; pick from those rather than inventing new ones.

Findings, issue bodies and your own earlier analysis are **claims to check** — re-read the code, fix what is still valid, name what you skipped.
A body invalidated by a rewrite is closed and re-filed, not annotated.

## Working with the user

- **"Discuss", "should we", "is it worth" are questions.** Answer, then stop.
- **Do not widen scope.** Name the adjacent thing in a sentence instead.
- **Recommend, do not survey.**
