import boto3
import pytest
from botocore.exceptions import ProfileNotFound

from aws_excom.aws import (
    get_cluster_arns,
    get_ecs_client,
    get_boto_session,
    get_clusters_data,
)


def test_boto_session(aws_credentials):
    session = get_boto_session(profile_name="foo")

    assert isinstance(session, boto3.Session)

    with pytest.raises(ProfileNotFound):
        get_boto_session("bar")

    return session


def test_boto_client(aws_credentials):
    session = test_boto_session(aws_credentials)
    client = get_ecs_client(session)

    assert "botocore.client.ECS" in str(client)


def test_get_cluster_arns(ecs):
    ecs.create_cluster(clusterName="foo")

    arns = get_cluster_arns(ecs)

    assert len(arns) == 1

    return arns


def test_get_clusters_data(ecs):
    arns = test_get_cluster_arns(ecs)

    clusters_data = get_clusters_data(ecs, arns)

    assert len(clusters_data) == len(arns)
    assert clusters_data[0]["clusterName"] == "foo"
