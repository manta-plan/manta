from fastapi import HTTPException

from manta.services.results.playbook_result import (
    ListPlaybooksResult,
    PlaybookDetailResult,
    PlaybookNode,
    PlaybookNodeConfigField,
    PlaybookSummaryResult,
)

# Static catalog, no database required — mirrors the playbook options the
# frontend currently hardcodes in create-run-dialog.tsx. Disconnected from the
# real playbook/runner library (playbook_library.playbooks.library_playbooks()):
# a run created against "pi-digit-statistics" 404s at RunService.create_run,
# since no library playbook has that name. Needs wiring to real data before
# this is actually functional end-to-end.
_PLAYBOOKS: dict[str, PlaybookDetailResult] = {
    playbook.id: playbook
    for playbook in [
        PlaybookDetailResult(
            id="pi-digit-statistics",
            name="Pi Digit Statistics",
            description="Computes digits of pi and their frequency distribution.",
            status="available",
            nodes=[
                PlaybookNode(
                    id="pi-digit-statistics",
                    type="playbook",
                    label="pi digit statistic",
                    config=[
                        PlaybookNodeConfigField(
                            # `key` matches the old pi-digit-stats demo flow's own
                            # parameter name. That flow no longer exists (removed
                            # upstream in favor of the real playbook/runner library),
                            # so this entry is display-only — see the comment above
                            # `_PLAYBOOKS`.
                            key="num_digits",
                            label="num_digits",
                            type="integer",
                            required=True,
                            min=1,
                            default=10_000,
                        )
                    ],
                )
            ],
        ),
        PlaybookDetailResult(
            id="grid-demand-forecast",
            name="Grid Demand Forecast",
            description="Forecasts electricity demand across a grid network.",
            status="coming_soon",
            nodes=[],
        ),
        PlaybookDetailResult(
            id="renewable-dispatch-planning",
            name="Renewable Dispatch Planning",
            description="Plans dispatch schedules for renewable generation assets.",
            status="coming_soon",
            nodes=[],
        ),
    ]
}


class PlaybookService:
    def list_playbooks(self) -> ListPlaybooksResult:
        return ListPlaybooksResult(
            items=[
                PlaybookSummaryResult(**playbook.model_dump(exclude={"nodes"}))
                for playbook in _PLAYBOOKS.values()
            ]
        )

    def get_playbook(self, playbook_id: str) -> PlaybookDetailResult:
        playbook = _PLAYBOOKS.get(playbook_id)
        if playbook is None:
            raise HTTPException(status_code=404, detail=f"Playbook {playbook_id} not found")

        return playbook
