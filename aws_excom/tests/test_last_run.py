import pytest

from aws_excom import last_run
from aws_excom.last_run import (
    get_last_command,
    get_last_run_file_paths,
    get_last_target,
    save_last_command,
    save_last_target,
)

CONTAINER = {"taskArn": "arn:task", "name": "gunicorn", "lastStatus": "RUNNING"}


@pytest.fixture(autouse=True)
def tempdir(tmp_path, monkeypatch):
    monkeypatch.setattr(last_run, "TEMPDIR", str(tmp_path))
    return tmp_path


def test_nothing_saved():
    assert get_last_command() is None
    assert get_last_target() is None


def test_command_and_target_are_kept_separately():
    save_last_command("aws ecs execute-command ...")
    save_last_target("arn:cluster", CONTAINER, "prod", None)
    assert get_last_command() == "aws ecs execute-command ..."

    save_last_target("arn:other-cluster", CONTAINER)
    assert get_last_command() == "aws ecs execute-command ..."
    assert get_last_target() == {
        "cluster_arn": "arn:other-cluster",
        "container": {"taskArn": "arn:task", "name": "gunicorn"},
        "profile": None,
        "region": None,
    }
    assert len(get_last_run_file_paths()) == 1


def test_file_from_older_version(tempdir):
    (tempdir / ".aws-excom-last-runabc").write_text("aws ecs execute-command ...")
    assert get_last_command() is None
    assert get_last_target() is None

    save_last_command("aws ecs execute-command --new")
    assert get_last_command() == "aws ecs execute-command --new"
    assert len(get_last_run_file_paths()) == 1
