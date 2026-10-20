import uuid
from os import environ

import boto3
import pytest
from botocore.config import Config
from moto import mock_aws
from moto.server import ThreadedMotoServer


@pytest.fixture(scope="function")
def aws_credentials():
    """Mocked AWS Credentials for moto."""
    environ["AWS_ACCESS_KEY_ID"] = "testing"
    environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    environ["AWS_SECURITY_TOKEN"] = "testing"
    environ["AWS_SESSION_TOKEN"] = "testing"
    environ["AWS_DEFAULT_REGION"] = "eu-west-1"
    environ[
        "AWS_SHARED_CREDENTIALS_FILE"
    ] = "aws_excom/tests/assets/dummy_aws_credentials"


@pytest.fixture(scope="function")
def ecs(aws_credentials):
    with mock_aws():
        yield boto3.client("ecs", region_name=environ["AWS_DEFAULT_REGION"])


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
