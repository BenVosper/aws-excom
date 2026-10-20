"""
The last run, saved so it can be repeated with '--last'.

Holds the command run in the last interactive session, and the last container
selected by any subcommand along with the profile and region used.
"""

import json
import os
import tempfile

LAST_RUN_FILENAME_PREFIX = ".aws-excom-last-run"
TEMPDIR = tempfile.gettempdir()


def get_last_run_file_paths():
    return [
        os.path.join(TEMPDIR, name)
        for name in filter(
            lambda filename: filename.startswith(LAST_RUN_FILENAME_PREFIX),
            os.listdir(TEMPDIR),
        )
    ]


def cleanup_last_run_files():
    for path in get_last_run_file_paths():
        os.remove(path)


def read_last_run():
    """The saved last run, or an empty dict if there isn't one"""
    last_run_file_paths = get_last_run_file_paths()
    if not last_run_file_paths:
        return {}
    try:
        with open(last_run_file_paths[0]) as f:
            last_run = json.load(f)
    # Older versions saved a plain command, which can't be told apart from a broken
    # file, so both count as no last run
    except (OSError, ValueError):
        return {}
    return last_run if isinstance(last_run, dict) else {}


def write_last_run(**fields):
    """Update the given fields of the saved last run, keeping the others"""
    last_run = {**read_last_run(), **fields}
    cleanup_last_run_files()
    with tempfile.NamedTemporaryFile(
        "w",
        dir=TEMPDIR,
        prefix=LAST_RUN_FILENAME_PREFIX,
        delete=False,
    ) as f:
        json.dump(last_run, f)


def get_last_command():
    return read_last_run().get("command")


def save_last_command(command):
    write_last_run(command=command)


def get_last_target():
    """
    Dict of the last selected container, with its 'cluster_arn', 'container' (just
    'taskArn' and 'name') and the 'profile' and 'region' used. None if there isn't one
    """
    return read_last_run().get("target")


def save_last_target(cluster_arn, container, profile_name=None, region_name=None):
    write_last_run(
        target={
            "cluster_arn": cluster_arn,
            "container": {"taskArn": container["taskArn"], "name": container["name"]},
            "profile": profile_name,
            "region": region_name,
        }
    )
