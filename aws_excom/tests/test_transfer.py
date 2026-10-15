import os
import shlex
import subprocess
import uuid

import boto3
import pytest
from botocore.config import Config
from moto.server import ThreadedMotoServer

from aws_excom.transfer import (
    MIB,
    MAX_PARTS,
    S3Transfer,
    TransferError,
    get_part_count,
    get_part_size_mib,
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


@pytest.fixture
def s3_server(aws_credentials):
    server = ThreadedMotoServer(port=0)
    server.start()
    host, port = server.get_host_and_port()
    client = boto3.client(
        "s3",
        endpoint_url=f"http://{host}:{port}",
        region_name="eu-west-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    bucket = f"test-bucket-{uuid.uuid4()}"
    client.create_bucket(
        Bucket=bucket,
        CreateBucketConfiguration={"LocationConstraint": "eu-west-1"},
    )
    yield client, bucket
    server.stop()


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
