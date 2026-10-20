import os
import shlex
import subprocess

import pytest

from aws_excom.transfer import (
    MIB,
    MAX_PARTS,
    S3Put,
    S3Transfer,
    TransferError,
    get_part_count,
    get_part_size_mib,
    parse_existing_size_output,
    parse_size_output,
)


def test_part_size_respects_minimum_and_part_limit():
    assert get_part_size_mib(0) == 16
    assert get_part_size_mib(100 * MIB) == 16

    huge = 5 * 1024 * 1024 * MIB  # 5 TiB
    part_size_mib = get_part_size_mib(huge)
    assert get_part_count(huge, part_size_mib) <= MAX_PARTS


def test_part_count():
    assert get_part_count(0, 16) == 1
    assert get_part_count(16 * MIB, 16) == 1
    assert get_part_count(16 * MIB + 1, 16) == 2


def test_parse_size_output():
    output = (
        "\r\nStarting session with SessionId: abc\r\nAWS_EXCOM_SIZE=1234\r\n\r\nExiting"
    )
    assert parse_size_output(output) == 1234

    with pytest.raises(TransferError):
        parse_size_output("No such file: /nope")


def run_as_container(command):
    """'execute-command' runs the command without a shell, so split it the same way"""
    return subprocess.run(
        shlex.split(command), capture_output=True, text=True, check=False
    )


@pytest.fixture
def remote_file(tmp_path):
    # Awkward name to check quoting survives the trip
    path = tmp_path / "it's a file.bin"
    path.write_bytes(os.urandom(40 * MIB + 123))
    return path


def test_size_script(s3_server, remote_file):
    s3, bucket = s3_server
    transfer = S3Transfer(s3, bucket, str(remote_file))

    result = run_as_container(transfer.get_size_command())
    assert parse_size_output(result.stdout) == remote_file.stat().st_size

    transfer.cleanup()
    assert "Contents" not in s3.list_objects_v2(Bucket=bucket)


def test_size_script_missing_file(s3_server, tmp_path):
    s3, bucket = s3_server
    transfer = S3Transfer(s3, bucket, str(tmp_path / "nope"))

    result = run_as_container(transfer.get_size_command())
    assert "No such file" in result.stdout
    with pytest.raises(TransferError):
        parse_size_output(result.stdout)
    transfer.cleanup()


def test_round_trip(s3_server, remote_file, tmp_path):
    s3, bucket = s3_server
    transfer = S3Transfer(s3, bucket, str(remote_file))
    command = transfer.prepare(remote_file.stat().st_size)
    assert transfer.part_count == 3

    result = run_as_container(command)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Upload complete" in result.stdout

    transfer.complete()
    local_path = tmp_path / "downloaded.bin"
    transfer.download(str(local_path))
    transfer.cleanup()

    assert local_path.read_bytes() == remote_file.read_bytes()
    assert "Contents" not in s3.list_objects_v2(Bucket=bucket)


def test_incomplete_upload_is_aborted(s3_server, remote_file):
    s3, bucket = s3_server
    transfer = S3Transfer(s3, bucket, str(remote_file))
    transfer.prepare(remote_file.stat().st_size)

    # Container never ran the script
    with pytest.raises(TransferError):
        transfer.complete()
    transfer.cleanup()

    assert "Uploads" not in s3.list_multipart_uploads(Bucket=bucket)
    assert "Contents" not in s3.list_objects_v2(Bucket=bucket)


def test_parse_existing_size_output():
    assert parse_existing_size_output("AWS_EXCOM_SIZE=12\r\n") == 12
    assert parse_existing_size_output("No such file: /app/x\r\n") is None

    # Session failed, so it's unknown whether the file exists
    with pytest.raises(TransferError):
        parse_existing_size_output("An error occurred (TargetNotConnectedException)")


def put(s3_server, local_path, remote_path):
    """Put a file as 'aws-excom put' does, returning the output of 'put.sh'"""
    s3, bucket = s3_server
    transfer = S3Put(s3, bucket, str(local_path), str(remote_path))
    transfer.upload()
    result = run_as_container(transfer.get_put_command())
    try:
        transfer.check(result.stdout)
    finally:
        transfer.cleanup()
    assert "Contents" not in s3.list_objects_v2(Bucket=bucket)
    return result.stdout


def test_put_round_trip(s3_server, remote_file, tmp_path):
    destination = tmp_path / "destination" / "it's put.bin"
    destination.parent.mkdir()

    put(s3_server, remote_file, destination)

    assert destination.read_bytes() == remote_file.read_bytes()
    assert [path.name for path in destination.parent.iterdir()] == ["it's put.bin"]


def test_put_size_check_of_existing_file(s3_server, remote_file):
    s3, bucket = s3_server
    transfer = S3Put(s3, bucket, "local.bin", str(remote_file))

    result = run_as_container(transfer.get_size_command())
    assert parse_existing_size_output(result.stdout) == remote_file.stat().st_size
    transfer.cleanup()


def test_put_overwrite_keeps_permissions(s3_server, tmp_path):
    local_path = tmp_path / "new.sh"
    local_path.write_text("echo new\n")
    destination = tmp_path / "existing.sh"
    destination.write_text("echo old, and longer\n")
    destination.chmod(0o750)

    put(s3_server, local_path, destination)

    assert destination.read_text() == "echo new\n"
    assert destination.stat().st_mode & 0o777 == 0o750


@pytest.mark.parametrize(
    "remote_path, message",
    [
        ("{tmp}", "Is a directory: {tmp}"),
        ("{tmp}/nope/file.txt", "No such directory: {tmp}/nope"),
    ],
)
def test_put_bad_destination(s3_server, tmp_path, remote_path, message):
    local_path = tmp_path / "file.txt"
    local_path.write_text("hello")
    remote_path = remote_path.format(tmp=tmp_path)

    with pytest.raises(TransferError, match=message.format(tmp=tmp_path)):
        put(s3_server, local_path, remote_path)


def test_put_size_mismatch(s3_server, tmp_path):
    s3, bucket = s3_server
    local_path = tmp_path / "file.txt"
    local_path.write_text("hello")
    transfer = S3Put(s3, bucket, str(local_path), "/app/file.txt")

    with pytest.raises(TransferError, match="Expected 5 bytes"):
        transfer.check("AWS_EXCOM_SIZE=3\r\n")
