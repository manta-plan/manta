# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""The written-down shape of a playbook: inputs and steps.

Every model refuses keys it does not know. That is also what keeps a step to exactly
one of `block` or `playbook`: the first key found picks the kind of step, which then
refuses the other. Read with field names or aliases, and write with `by_alias=True` so
that `if` and `with` keep their names.
"""

from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    StringConstraints,
    Tag,
    model_validator,
)

from playbook.playbooks.expressions import check_expression, check_expressions_in

Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z_]\w*$")]
Expr = Annotated[str, AfterValidator(check_expression)]
With = Annotated[dict[str, Any], AfterValidator(check_expressions_in)]
Number = int | float


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class _Input(Strict):
    model_config = ConfigDict(strict=True)

    description: str | None = None

    @property
    def required(self) -> bool:
        return "default" not in self.model_fields_set


class StringInput(_Input):
    type: Literal["string"]
    default: str | None = None


class NumberInput(_Input):
    type: Literal["number"]
    default: Number | None = None


class BooleanInput(_Input):
    type: Literal["boolean"]
    default: bool | None = None


class ChoiceInput(_Input):
    type: Literal["choice"]
    options: list[str | Number] = Field(min_length=1)
    default: str | Number | None = None

    @model_validator(mode="after")
    def _default_is_an_option(self) -> "ChoiceInput":
        if self.default is not None and self.default not in self.options:
            raise ValueError(f"default {self.default!r} is not one of {self.options}")
        return self


InputSpec = Annotated[
    StringInput | NumberInput | BooleanInput | ChoiceInput,
    Field(discriminator="type"),
]


class _StepDoc(Strict):
    id: Identifier
    if_: Expr | None = Field(None, alias="if")


class BlockStepDoc(_StepDoc):
    block: str
    with_: With = Field(default_factory=dict, alias="with")


class PlaybookStepDoc(_StepDoc):
    playbook: "str | PlaybookDoc"
    with_: With = Field(default_factory=dict, alias="with")
    inputs: Literal["inherit"] | None = None


_STEP_KINDS = {"block": BlockStepDoc, "playbook": PlaybookStepDoc}


def _step_kind(value: object) -> str | None:
    if isinstance(value, dict):
        return next((kind for kind in _STEP_KINDS if kind in value), None)
    return next((kind for kind, cls in _STEP_KINDS.items() if isinstance(value, cls)), None)


StepDoc = Annotated[
    Annotated[BlockStepDoc, Tag("block")] | Annotated[PlaybookStepDoc, Tag("playbook")],
    Discriminator(
        _step_kind,
        custom_error_type="step_kind",
        custom_error_message="A step needs one of `block` or `playbook`",
    ),
]


class InitialDataDoc(Strict):
    """What the data already looks like before the playbook starts.

    This is what the playbook's author states about the starting record. We aim to drop
    it once the backend can read the record itself: the dimensions check needs to know
    whether a dimension is populated in the record, and the record's manifest only shows
    that the dimension is recorded.
    """

    dims: list[str] = Field(default_factory=list)


class PlaybookDoc(Strict):
    """A whole playbook, as written down."""

    name: str
    initial_data: InitialDataDoc = Field(default_factory=InitialDataDoc)
    inputs: dict[Identifier, InputSpec] = Field(default_factory=dict)
    steps: list[StepDoc] = Field(min_length=1)


PlaybookStepDoc.model_rebuild()
