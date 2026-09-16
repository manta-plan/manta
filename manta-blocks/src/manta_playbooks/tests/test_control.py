# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

"""The front door: deploying a playbook, starting it, and asking how it is doing."""

import pytest

from manta_blocks import catalogue
from manta_blocks.tests.fakes import FakeNeedsUpstream, FakePassthrough
from manta_playbooks import control
from manta_playbooks.execution import catalogue_parameter, run_playbook
from manta_playbooks.playbook import Playbook
from manta_playbooks.validation import PlaybookValidationError
from manta_playbooks.yaml_io import playbook_to_doc


def _playbook() -> Playbook:
    pb = Playbook(name="control-test")
    a = pb.add("a", FakePassthrough)
    pb.add("b", FakeNeedsUpstream, inputs={"source": a.output})
    return pb


CONFIG = {"a": {"label": "a"}, "b": {}}


def test_a_playbook_that_could_not_run_is_never_deployed(monkeypatch):
    def _fail_if_called(*args, **kwargs):
        raise AssertionError("nothing should have been deployed")

    monkeypatch.setattr(control.ProcessPixiRenderer, "apply", _fail_if_called)

    pb = Playbook(name="broken")
    pb.add("a", FakePassthrough)
    pb.add("a", FakePassthrough)  # duplicate step name

    with pytest.raises(PlaybookValidationError):
        control.deploy(pb, {})


def test_a_missing_work_pool_is_explained_with_the_commands_to_fix_it(monkeypatch):
    def _no_such_pool(self, plan):
        raise RuntimeError('Work pool "manta-default" not found.')

    monkeypatch.setattr(control.ProcessPixiRenderer, "apply", _no_such_pool)

    with pytest.raises(control.WorkPoolMissingError) as exc:
        control.deploy(_playbook(), CONFIG)

    message = str(exc.value)
    assert "work-pool create" in message
    assert "worker start" in message
    assert "manta-default" in message


def test_an_unrelated_deployment_failure_is_passed_along_unchanged(monkeypatch):
    def _boom(self, plan):
        raise RuntimeError("the API is down")

    monkeypatch.setattr(control.ProcessPixiRenderer, "apply", _boom)

    with pytest.raises(RuntimeError, match="the API is down"):
        control.deploy(_playbook(), CONFIG)


def test_starting_a_run_sends_the_playbook_as_the_document_it_was_edited_as(
    monkeypatch, initial_record
):
    captured = {}

    class _Run:
        id = "11111111-1111-1111-1111-111111111111"
        name = "eager-otter"

    def _fake_run_deployment(name, parameters, timeout):
        captured.update(name=name, parameters=parameters, timeout=timeout)
        return _Run()

    monkeypatch.setattr(control, "run_deployment", _fake_run_deployment)
    monkeypatch.setattr(control, "current_env", lambda: "default")

    doc = playbook_to_doc(_playbook())
    info = control.start_run(doc, CONFIG, initial_record, deploy_first=False)

    assert captured["name"] == "run_playbook/default"
    assert captured["parameters"]["playbook"]["name"] == "control-test"
    assert captured["parameters"]["config"] == CONFIG
    assert captured["parameters"]["record"] == {"url": "root"}
    # The call returns as soon as the run is accepted, rather than waiting for it.
    assert captured["timeout"] == 0
    assert info.flow_run_id == _Run.id
    assert info.name == "eager-otter"


def test_starting_a_run_deploys_first_unless_told_not_to(monkeypatch, initial_record):
    deployed = []
    monkeypatch.setattr(
        control, "deploy", lambda *args, **kwargs: deployed.append(True)
    )
    monkeypatch.setattr(
        control,
        "run_deployment",
        lambda **kwargs: type("R", (), {"id": "x", "name": "n"})(),
    )
    monkeypatch.setattr(control, "current_env", lambda: "default")

    doc = playbook_to_doc(_playbook())
    control.start_run(doc, CONFIG, initial_record)
    assert deployed == [True]


def test_the_catalogue_travels_as_an_opaque_string(monkeypatch, initial_record):
    # Prefect resolves `{"$ref": ...}` dicts inside flow parameters as its own
    # block-document references, and a catalogue's JSON schemas are full of
    # `$ref`s — so the catalogue must cross as a string, never a dict.
    captured = {}
    monkeypatch.setattr(
        control,
        "run_deployment",
        lambda name, parameters, timeout: (
            captured.update(parameters=parameters),
            type("R", (), {"id": "x", "name": "n"})(),
        )[1],
    )
    monkeypatch.setattr(control, "current_env", lambda: "default")

    known = catalogue()
    doc = playbook_to_doc(_playbook())
    control.start_run(doc, CONFIG, initial_record, deploy_first=False, catalogue=known)

    sent = captured["parameters"]["catalogue"]
    assert isinstance(sent, str)
    assert "$ref" in sent  # the fakes' schemas really do contain refs


@pytest.mark.slow
def test_a_playbook_document_can_be_run_from_end_to_end(monkeypatch, initial_record):
    # This is what a deployment runs when someone presses Run: the playbook arrives
    # as a document, not as a playbook object.
    monkeypatch.setenv("MANTA_ENV", "default")

    doc = playbook_to_doc(_playbook())
    result = run_playbook(
        playbook=doc.model_dump(mode="json"),
        config=CONFIG,
        record=initial_record.to_dict(),
    )

    assert result == {"url": "root+a+needs(root+a)"}


@pytest.mark.slow
def test_a_playbook_document_runs_with_a_catalogue_given_as_a_string(
    monkeypatch, initial_record
):
    monkeypatch.setenv("MANTA_ENV", "default")

    doc = playbook_to_doc(_playbook())
    result = run_playbook(
        playbook=doc.model_dump(mode="json"),
        config=CONFIG,
        record=initial_record.to_dict(),
        catalogue=catalogue_parameter(catalogue()),
    )

    assert result == {"url": "root+a+needs(root+a)"}
