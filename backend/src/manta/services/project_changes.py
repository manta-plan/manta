from dataclasses import dataclass


class _Unset:
    """Marks a field that was not sent, as opposed to `None`, which clears it."""


UNSET = _Unset()


@dataclass(frozen=True)
class UpdateProjectChanges:
    name: str | _Unset = UNSET
    description: str | None | _Unset = UNSET
