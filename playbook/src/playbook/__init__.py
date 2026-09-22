# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""The playbook framework: what a block is, and how blocks chain into a playbook.

Two layers, kept apart on purpose:

- `playbook.blocks` - a block, and everything needed to describe one without running
  it. This is what a block library (such as `playbook_library`) is written against.
- `playbook.playbooks` - blocks chained together, and the engine that runs them.

`playbook.blocks` never imports `playbook.playbooks`, so a library author only ever
depends on the half they need. Neither layer imports anything to do with
orchestration: running a block is a plain method call, and what schedules that call
lives outside this package entirely.
"""
