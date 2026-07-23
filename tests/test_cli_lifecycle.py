"""End-to-end CLI lifecycle regression tests."""

import json

import pytest
from typer.testing import CliRunner

from prompt_vcs.cli import app
from prompt_vcs.manager import LOCKFILE_NAME


runner = CliRunner()


@pytest.mark.parametrize("split", [False, True], ids=["single-file", "multi-file"])
def test_cli_prompt_lifecycle(tmp_path, split):
    """A prompt can traverse the complete supported CLI lifecycle."""
    init_args = ["init", str(tmp_path)]
    if split:
        init_args.append("--split")
    assert runner.invoke(app, init_args).exit_code == 0

    project_args = ["--project", str(tmp_path)]
    add_v1 = runner.invoke(
        app,
        ["add", "greeting", "Hello {name}!", *project_args],
    )
    assert add_v1.exit_code == 0, add_v1.output

    add_v2 = runner.invoke(
        app,
        [
            "add",
            "greeting",
            "Dear {name}, welcome!",
            "--version",
            "v2",
            *project_args,
        ],
    )
    assert add_v2.exit_code == 0, add_v2.output

    listed = runner.invoke(app, ["list", "--format", "json", *project_args])
    assert listed.exit_code == 0, listed.output
    entries = json.loads(listed.output)
    greeting = next(entry for entry in entries if entry["id"] == "greeting")
    assert "v2" in greeting["versions"]

    switched = runner.invoke(app, ["switch", "greeting", "v2", *project_args])
    assert switched.exit_code == 0, switched.output
    lockfile = json.loads((tmp_path / LOCKFILE_NAME).read_text(encoding="utf-8"))
    assert lockfile == {"greeting": "v2"}

    exported = runner.invoke(app, ["export", "--format", "json", *project_args])
    assert exported.exit_code == 0, exported.output
    exported_prompts = json.loads(exported.output)
    assert exported_prompts[0]["id"] == "greeting"
    assert exported_prompts[0]["template"].strip() == "Dear {name}, welcome!"

    unlocked = runner.invoke(app, ["unlock", "greeting", *project_args])
    assert unlocked.exit_code == 0, unlocked.output
    lockfile = json.loads((tmp_path / LOCKFILE_NAME).read_text(encoding="utf-8"))
    assert "greeting" not in lockfile

    deleted = runner.invoke(app, ["delete", "greeting", "--yes", *project_args])
    assert deleted.exit_code == 0, deleted.output

    listed_after_delete = runner.invoke(
        app,
        ["list", "--format", "json", *project_args],
    )
    assert listed_after_delete.exit_code == 0, listed_after_delete.output
    assert json.loads(listed_after_delete.output) == []
