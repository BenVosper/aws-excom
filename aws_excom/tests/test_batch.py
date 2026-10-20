import os
import shlex
import signal
import subprocess
from subprocess import PIPE
import time

from aws_excom.batch import (
    build_inline_command,
    format_table,
    get_output_paths,
    get_targets_table,
    run_and_save,
    trim_output,
)
from aws_excom.tests.test_transfer import run_as_container
from aws_excom.transfer import S3Staging

SESSION_OUTPUT = (
    b"\r\nStarting session with SessionId: abc\r\n"
    b"AWS_EXCOM_START\r\n"
    b"hello\r\n"
    b"world\r\n"
    b"AWS_EXCOM_EXIT=3\r\n"
    b"\r\n\r\nExiting session with sessionId: abc.\r\n\r\n"
)


def trim(tmp_path, raw):
    raw_path = tmp_path / "out.txt.raw"
    raw_path.write_bytes(raw)
    output_path = tmp_path / "out.txt"
    status = trim_output(str(raw_path), str(output_path))
    assert not raw_path.exists()
    return status, output_path.read_bytes()


def test_trim_output(tmp_path):
    assert trim(tmp_path, SESSION_OUTPUT) == (3, b"hello\r\nworld\r\n")


def test_trim_output_without_trailing_newline(tmp_path):
    raw = b"AWS_EXCOM_START\nhelloAWS_EXCOM_EXIT=0\nExiting\n"
    assert trim(tmp_path, raw) == (0, b"hello")


def test_trim_output_keeps_markers_in_command_output(tmp_path):
    raw = (
        b"AWS_EXCOM_START\nAWS_EXCOM_START\nAWS_EXCOM_EXIT=1\n"
        b"AWS_EXCOM_EXIT=0\nExiting\n"
    )
    assert trim(tmp_path, raw) == (0, b"AWS_EXCOM_START\nAWS_EXCOM_EXIT=1\n")


def test_trim_output_without_start_keeps_everything(tmp_path):
    raw = b"An error occurred (TargetNotConnectedException)\n"
    assert trim(tmp_path, raw) == (None, raw)


def test_trim_output_cut_off(tmp_path):
    raw = b"Starting session\nAWS_EXCOM_START\npartial\n"
    assert trim(tmp_path, raw) == (None, b"partial\n")


def test_get_output_paths():
    def target(cluster_name, container_name):
        return {"clusterName": cluster_name}, {"name": container_name}

    targets = [
        target("prod-eu", "gunicorn"),
        target("prod-us", "gunicorn"),
        target("prod-us", "celery"),
        target("prod-us", "gunicorn"),
    ]
    assert get_output_paths("runs", "20261020-120000", targets) == [
        "runs/20261020-120000_prod-eu_gunicorn.txt",
        "runs/20261020-120000_prod-us_gunicorn_1.txt",
        "runs/20261020-120000_prod-us_celery.txt",
        "runs/20261020-120000_prod-us_gunicorn_2.txt",
    ]


def test_format_table():
    assert format_table(("#", "Name"), [(1, "gunicorn"), (10, "a")]) == [
        "#   Name",
        "1   gunicorn",
        "10  a",
    ]


def test_get_targets_table():
    targets = [
        (
            {"clusterName": "prod-eu"},
            {"name": "gunicorn", "taskArn": "arn:aws:ecs:eu-west-1:1:task/prod-eu/abc"},
        ),
        (
            {"clusterName": "prod-us-east"},
            {"name": "celery", "taskArn": "arn:aws:ecs:us-east-1:1:task/prod-us/def"},
        ),
    ]
    assert get_targets_table(targets) == [
        "#  Cluster       Container  Task ID",
        "1  prod-eu       gunicorn   abc",
        "2  prod-us-east  celery     def",
    ]


def test_inline_command():
    result = run_as_container(build_inline_command('echo "it\'s" | tr a-z A-Z; exit 3'))
    assert result.stdout == "AWS_EXCOM_START\nIT'S\nAWS_EXCOM_EXIT=3\n"
    assert result.returncode == 3


def interrupt_in_container(command):
    """
    Run as 'run_as_container' does, then send SIGINT to the whole process group, as
    Ctrl-C forwarded to the container's terminal does
    """
    process = subprocess.Popen(
        shlex.split(command), stdout=PIPE, text=True, start_new_session=True
    )
    # Wait for the command to start
    assert process.stdout.readline() == "AWS_EXCOM_START\n"
    time.sleep(0.2)
    os.killpg(process.pid, signal.SIGINT)
    output, _ = process.communicate(timeout=10)
    return output, process.returncode


def test_inline_command_interrupted():
    output, returncode = interrupt_in_container(build_inline_command("sleep 30"))
    assert output == "AWS_EXCOM_EXIT=130\n"
    assert returncode == 130


def test_run_and_save(tmp_path):
    output_path = tmp_path / "cluster" / "out.txt"
    # Stands in for the session's own lines around the command
    command = build_inline_command("echo hello; echo error >&2; exit 2")
    args = ["sh", "-c", f"echo noise; {command}; echo noise"]

    assert run_and_save(args, str(output_path)) == 2
    assert output_path.read_bytes() == b"hello\nerror\n"
    assert not (tmp_path / "cluster" / "out.txt.raw").exists()


def test_run_and_save_without_marker(tmp_path):
    output_path = tmp_path / "out.txt"
    assert run_and_save(["sh", "-c", "echo nope"], str(output_path)) is None
    assert output_path.read_bytes() == b"nope\n"


def test_run_script_passes_file_on_stdin(s3_server):
    s3, bucket = s3_server
    staging = S3Staging(s3, bucket)
    input_url = staging.stage("script.py", b"print('hello from stdin')\n")
    command = staging.stage_script("run.sh", CMD="python3 -", INPUT_URL=input_url)

    result = run_as_container(command)
    assert result.stdout == "AWS_EXCOM_START\nhello from stdin\nAWS_EXCOM_EXIT=0\n"
    assert result.returncode == 0

    staging.cleanup()
    assert "Contents" not in s3.list_objects_v2(Bucket=bucket)


def test_run_script_exit_status(s3_server):
    s3, bucket = s3_server
    staging = S3Staging(s3, bucket)
    input_url = staging.stage("input.txt", b"")
    command = staging.stage_script("run.sh", CMD="exit 4", INPUT_URL=input_url)

    result = run_as_container(command)
    assert result.stdout == "AWS_EXCOM_START\nAWS_EXCOM_EXIT=4\n"
    assert result.returncode == 4
    staging.cleanup()


def test_run_script_interrupted(s3_server):
    s3, bucket = s3_server
    staging = S3Staging(s3, bucket)
    input_url = staging.stage("input.txt", b"")
    command = staging.stage_script("run.sh", CMD="sleep 30", INPUT_URL=input_url)

    output, returncode = interrupt_in_container(command)
    assert output == "AWS_EXCOM_EXIT=130\n"
    assert returncode == 130
    staging.cleanup()


def test_cleanup_with_nothing_staged(s3_server):
    s3, bucket = s3_server
    S3Staging(s3, bucket).cleanup()
