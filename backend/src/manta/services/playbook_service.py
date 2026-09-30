from fastapi import HTTPException

from manta.services.results.playbook_result import (
    ListPlaybooksResult,
    PlaybookDetailResult,
    PlaybookNode,
    PlaybookNodeConfigField,
    PlaybookSummaryResult,
)

# Static catalog, no database required — mirrors the playbook options the
# frontend currently hardcodes in create-run-dialog.tsx. Once more playbooks
# are actually implemented this should move to a proper data source.
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
                            # `key` matches the pi-digit-stats flow's own parameter name
                            # (see workflows/pi_digit_stats.py) — RunService forwards
                            # `config` straight through to `run_deployment`.
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
