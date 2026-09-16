# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

"""Playbooks: blocks chained together into a piece of work that can be run."""

from manta_playbooks.control import (
    RunInfo,
    RunStatus,
    WorkPoolMissingError,
    deploy,
    run_status,
    start_run,
)
from manta_playbooks.deploy import (
    ProcessPixiRenderer,
    Renderer,
    deployment_plan,
    ensure_process_pool,
    provision_catalogue,
)
from manta_playbooks.execution import (
    ORCHESTRATOR_FLOW,
    build_flow,
    catalogue_parameter,
    dispatch_block,
    orchestrator_path,
    run_playbook,
)
from manta_playbooks.graph import (
    GraphEdge,
    GraphNode,
    PlaybookGraph,
    graph_to_mermaid,
    playbook_graph,
)
from manta_playbooks.playbook import (
    BlockStep,
    NestedPlaybookStep,
    OutputRef,
    Playbook,
    StepHandle,
    When,
)
from manta_playbooks.validation import (
    PlaybookIssue,
    PlaybookValidationError,
    validate_report,
)
from manta_playbooks.yaml_io import (
    FilePlaybookLoader,
    PlaybookDoc,
    PlaybookLoader,
    PlaybookLoadError,
    StepDoc,
    WhenDoc,
    load_config,
    load_playbook,
    playbook_from_doc,
    playbook_to_doc,
)

__all__ = [
    "ORCHESTRATOR_FLOW",
    "BlockStep",
    "FilePlaybookLoader",
    "GraphEdge",
    "GraphNode",
    "NestedPlaybookStep",
    "OutputRef",
    "Playbook",
    "PlaybookDoc",
    "PlaybookGraph",
    "PlaybookIssue",
    "PlaybookLoadError",
    "PlaybookLoader",
    "PlaybookValidationError",
    "ProcessPixiRenderer",
    "Renderer",
    "RunInfo",
    "RunStatus",
    "StepDoc",
    "StepHandle",
    "When",
    "WhenDoc",
    "WorkPoolMissingError",
    "build_flow",
    "catalogue_parameter",
    "deploy",
    "deployment_plan",
    "dispatch_block",
    "ensure_process_pool",
    "graph_to_mermaid",
    "load_config",
    "load_playbook",
    "orchestrator_path",
    "playbook_from_doc",
    "playbook_graph",
    "playbook_to_doc",
    "provision_catalogue",
    "run_playbook",
    "run_status",
    "start_run",
    "validate_report",
]
