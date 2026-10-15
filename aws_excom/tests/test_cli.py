import pytest

from aws_excom.cli import parser


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
