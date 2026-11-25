# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""How a problem with a playbook is reported."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

PlaybookIssueKind = Literal["structure", "reference", "inputs", "dims", "config", "environment"]
"""What sort of problem an issue is:

- `structure`: step ids that clash, inherited inputs that clash, or a playbook
  containing itself
- `reference`: an expression reading an input that does not exist, or a nested
  playbook given an input it does not declare
- `inputs`: input values that are unknown, missing, of the wrong type, or not an option
- `dims`: a step needing a dimension the data does not have by the time it runs
- `config`: settings that do not fit what a block accepts
- `environment`: two blocks describing the same environment differently
"""

SettingPath = tuple[str | int, ...]
"""Where a value sits in a block's settings: keys, and indexes into lists."""


class PlaybookIssue(BaseModel):
    """One problem with a playbook, or with the inputs it is about to run with."""

    model_config = ConfigDict(frozen=True)

    kind: PlaybookIssueKind
    message: str

    step_path: tuple[str, ...] = ()
    """Which step this is about, named from the outermost playbook inwards, e.g.
    `("regional", "dispatch")` for a step of the playbook nested as `regional`. Empty
    for a problem with the playbook as a whole."""

    input_path: tuple[str, ...] | None = None
    """Which input value, e.g. `("expansion_mode",)`."""

    setting_path: SettingPath | None = None
    """Where in the step's settings the problem is, e.g. `("optimize_config", "horizon")`."""

    def __str__(self) -> str:
        where = f"step {'/'.join(self.step_path)!r}" if self.step_path else "playbook"
        if self.input_path is not None:
            where += f", input {'.'.join(self.input_path)!r}"
        if self.setting_path is not None:
            where += f", setting {'.'.join(str(part) for part in self.setting_path)!r}"
        return f"[{self.kind}] {where}: {self.message}"


class PlaybookHasIssuesError(Exception):
    """Raised when a playbook cannot run as written, carrying every issue found."""

    def __init__(self, issues: list[PlaybookIssue]) -> None:
        self.issues = issues
        listed = "\n".join(f"  {issue}" for issue in issues)
        super().__init__(f"{len(issues)} issue(s) found:\n{listed}")
