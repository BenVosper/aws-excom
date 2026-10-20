import sys
from unittest import mock

import pytest

from aws_excom.cli import main, parser


def test_no_subcommand():
    args = parser.parse_args(["--profile", "p", "--command", "ls"])
    assert args.subcommand is None
    assert args.profile == "p"
    assert args.region is None
    assert args.command == "ls"


@pytest.mark.parametrize(
    "argv",
    [
        ["--profile", "p", "get", "/x", "--region", "r"],
        ["get", "/x", "--profile", "p", "--region", "r"],
    ],
)
def test_common_arguments_either_side_of_subcommand(argv):
    args = parser.parse_args(argv)
    assert args.subcommand == "get"
    assert args.remote_path == "/x"
    assert args.profile == "p"
    assert args.region == "r"


def test_put_force():
    args = parser.parse_args(["put", "local.txt", "/app/", "-f"])
    assert args.force is True
    assert parser.parse_args(["put", "local.txt", "/app/"]).force is False


@pytest.mark.parametrize(
    "argv",
    [
        ["get", "/x", "--last"],
        ["--last", "get", "/x"],
        ["put", "local.txt", "/app/", "--last"],
    ],
)
def test_last_with_subcommand(argv):
    assert parser.parse_args(argv).last is True


def test_last_defaults_to_false_with_subcommand():
    assert parser.parse_args(["get", "/x"]).last is False


def test_last_not_allowed_with_batch(capsys):
    with mock.patch.object(sys, "argv", ["aws-excom", "--last", "batch"]):
        with pytest.raises(SystemExit):
            main()
    assert "'--last' can't be used with 'batch'" in capsys.readouterr().err


def test_batch_no_confirm():
    assert parser.parse_args(["batch", "--no-confirm"]).no_confirm is True
    assert parser.parse_args(["batch"]).no_confirm is False
