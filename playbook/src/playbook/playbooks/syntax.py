# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""The models of a playbook document: its inputs and its steps.

Each model refuses a key that it does not define. A step therefore has exactly one of
`block` and `playbook`: the key that is present sets the model of the step, and that
model refuses the other key. Each model accepts the field names `if_` and `with_` as
well as the keys `if` and `with`. Dump a model with `by_alias=True` to write the keys.
"""

from typing import TYPE_CHECKING, Annotated, Any, Literal

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
    required: bool = False

    if TYPE_CHECKING:
        default: object

    @model_validator(mode="after")
    def _required_has_no_default(self) -> "_Input":
        if self.required and self.default is not None:
            raise ValueError(
                f"the input is required and has `default` {self.default!r}. "
                f"Remove `default`, or set `required: false`."
            )
        return self


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
            raise ValueError(
                f"`default` is {self.default!r}, which is not one of `options` {self.options}. "
                f"Set `default` to one of them."
            )
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
        custom_error_message="A step has neither `block` nor `playbook`. Add one of them.",
    ),
]


class InitialDataDoc(Strict):
    """What the data already looks like before the playbook starts.

    The author of the playbook states these dimensions. We aim to drop this key once
    the backend can read the data record itself. The dimensions check needs to know
    whether a dimension is populated, and the manifest of the record shows only that
    the dimension is recorded.
    """

    dims: list[str] = Field(default_factory=list)


class PlaybookDoc(Strict):
    """A whole playbook, as written down."""

    name: str
    initial_data: InitialDataDoc = Field(default_factory=InitialDataDoc)
    inputs: dict[Identifier, InputSpec] = Field(
        default_factory=dict, json_schema_extra={"additionalProperties": False}
    )
    steps: list[StepDoc] = Field(min_length=1)


PlaybookStepDoc.model_rebuild()
