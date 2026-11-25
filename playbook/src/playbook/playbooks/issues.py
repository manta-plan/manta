# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""The issue that reports one problem with a playbook, and the error that lists every issue."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

PlaybookIssueKind = Literal["structure", "reference", "inputs", "dims", "config", "environment"]
"""The kind of problem that an issue reports:

- `structure`: two steps have the same id, an inherited input has a name that is
  taken, or a playbook contains itself
- `reference`: an expression reads an input that does not exist, or a step sets an
  input that its nested playbook does not declare
- `inputs`: an input value is unknown, missing, null where it cannot be, of the wrong
  type, or not an option, or an expression cannot be evaluated with the input values
- `dims`: a step requires a dimension that the data does not have when the step runs
- `config`: a setting does not fit what its block accepts, or a setting a run gives
  cannot be applied (see `settings`)
- `environment`: two blocks describe the same environment differently
"""

SettingPath = tuple[str | int, ...]
"""The position of a value in the settings of a block: keys, and indexes into lists."""


class PlaybookIssue(BaseModel):
    """One problem with a playbook, or with the input values of a run."""

    model_config = ConfigDict(frozen=True)

    kind: PlaybookIssueKind
    message: str

    step_path: tuple[str, ...] = ()
    """The step with the problem, as ids from the outermost playbook inwards, e.g.
    `("regional", "dispatch")` for a step of the playbook nested as `regional`. Empty
    for a problem with the playbook as a whole."""

    input_path: tuple[str, ...] | None = None
    """The input with the problem, e.g. `("expansion_mode",)`."""

    setting_path: SettingPath | None = None
    """The setting of the step with the problem, e.g. `("optimize_config", "horizon")`."""

    def __str__(self) -> str:
        where = f"step {'/'.join(self.step_path)!r}" if self.step_path else "playbook"
        if self.input_path is not None:
            where += f", input {'.'.join(self.input_path)!r}"
        if self.setting_path:
            where += f", setting {'.'.join(str(part) for part in self.setting_path)!r}"
        return f"[{self.kind}] {where}: {self.message}"


class PlaybookHasIssuesError(Exception):
    """Raised when a playbook cannot run as written, carrying every issue found."""

    def __init__(self, issues: list[PlaybookIssue]) -> None:
        self.issues = issues
        listed = "\n".join(f"  {issue}" for issue in issues)
        super().__init__(f"{len(issues)} issue(s) found:\n{listed}")
