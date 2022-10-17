from os import environ

import boto3
import pytest
from moto import mock_ecs


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
    with mock_ecs():
        yield boto3.client("ecs", region_name=environ["AWS_DEFAULT_REGION"])
