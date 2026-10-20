"""
Run one command across several containers, saving each one's output to a file.

Commands are run by 'sh' in the container between two markers: one before, and one
after with the exit status, as 'execute-command' doesn't pass it back. The saved
output is trimmed to what's between them, dropping the session's own lines. A command
file is staged in S3 and passed to the command on stdin by 'scripts/run.sh'.
"""

import os
import re
import shlex
import sys

from collections import Counter
from datetime import datetime
from subprocess import Popen, PIPE, STDOUT

from aws_excom import ignore_user_entered_signals

# Markers are printed by 'build_inline_command' and 'scripts/run.sh'
START_MARKER = b"AWS_EXCOM_START"
EXIT_PATTERN = re.compile(rb"AWS_EXCOM_EXIT=(\d+)")


def build_inline_command(command):
    script = (
        # See 'scripts/run.sh'
        "trap : INT\n"
        f"echo {START_MARKER.decode()}\n"
        f"sh -c {shlex.quote(command)}\n"
        "status=$?\n"
        'echo "AWS_EXCOM_EXIT=$status"\n'
        'exit "$status"'
    )
    return f"sh -c {shlex.quote(script)}"


def find_markers(path):
    """
    Line numbers of the first start marker and the last exit marker after it, and
    the exit status. Each is None if not found.
    """
    start = end = status = None
    with open(path, "rb") as f:
        for number, line in enumerate(f):
            if start is None:
                if line.strip() == START_MARKER:
                    start = number
                continue
            match = EXIT_PATTERN.search(line)
            if match:
                end, status = number, int(match.group(1))
    return start, end, status


def trim_output(raw_path, output_path):
    """
    Save the output between the markers. Returns the exit status, or None if it
    couldn't be determined. Without a start marker the command never ran, so the
    whole output is kept to show why.
    """
    start, end, status = find_markers(raw_path)
    if start is None:
        os.replace(raw_path, output_path)
        return None

    with open(raw_path, "rb") as src, open(output_path, "wb") as dst:
        for number, line in enumerate(src):
            if number <= start:
                continue
            if number == end:
                # Keep any output not ended with a newline before the marker
                dst.write(line[: EXIT_PATTERN.search(line).start()])
                break
            dst.write(line)
    os.remove(raw_path)
    return status


def get_task_id(container):
    return container["taskArn"].split("/")[-1]


def get_timestamp():
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def get_output_paths(output_dir, timestamp, targets):
    """
    Output path for each (cluster, container) target, named by cluster and container.
    Names shared by several targets, eg. a service's tasks, are numbered. Every run's
    files share a directory and are told apart by the timestamp they start with.
    Parts are joined with '_' as names often contain '-'.
    """
    names = [
        f"{cluster['clusterName']}_{container['name']}"
        for cluster, container in targets
    ]
    counts = Counter(names)
    numbers = Counter()
    paths = []
    for name in names:
        if counts[name] > 1:
            numbers[name] += 1
            name = f"{name}_{numbers[name]}"
        paths.append(os.path.join(output_dir, f"{timestamp}_{name}.txt"))
    return paths


def run_and_save(args, output_path):
    """
    Run a command, streaming its output to the terminal and saving the trimmed
    output to a file. Returns the remote exit status, or None if it couldn't be
    determined.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    raw_path = f"{output_path}.raw"
    # Output is written to the underlying buffer, so anything printed must go first
    sys.stdout.flush()
    with open(raw_path, "wb") as f, ignore_user_entered_signals():
        process = Popen(args, stdout=PIPE, stderr=STDOUT)
        for chunk in iter(lambda: process.stdout.read1(65536), b""):
            f.write(chunk)
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
        process.wait()
    return trim_output(raw_path, output_path)
