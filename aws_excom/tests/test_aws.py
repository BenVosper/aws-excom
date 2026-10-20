import boto3
import pytest
from botocore.exceptions import ProfileNotFound
from botocore.stub import Stubber

from aws_excom.aws import (
    get_cluster_arns,
    get_ecs_client,
    get_boto_session,
    get_clusters_data,
    get_task_arns,
)


def test_boto_session(aws_credentials):
    session = get_boto_session(profile_name="foo")

    assert isinstance(session, boto3.Session)

    with pytest.raises(ProfileNotFound):
        get_boto_session("bar")


def test_boto_client(aws_credentials):
    session = get_boto_session(profile_name="foo")
    client = get_ecs_client(session)

    assert "botocore.client.ECS" in str(client)


def test_get_cluster_arns(ecs):
    ecs.create_cluster(clusterName="foo")

    arns = get_cluster_arns(ecs)

    assert len(arns) == 1


def test_get_clusters_data(ecs):
    ecs.create_cluster(clusterName="foo")
    arns = get_cluster_arns(ecs)

    clusters_data = get_clusters_data(ecs, arns)

    assert len(clusters_data) == len(arns)
    assert clusters_data[0]["clusterName"] == "foo"


def test_get_task_arns_paginates(aws_credentials):
    client = boto3.client("ecs", region_name="eu-west-1")
    with Stubber(client) as stubber:
        stubber.add_response(
            "list_tasks",
            {"taskArns": ["task-1"], "nextToken": "token"},
            {"cluster": "cluster"},
        )
        stubber.add_response(
            "list_tasks",
            {"taskArns": ["task-2"]},
            {"cluster": "cluster", "nextToken": "token"},
        )

        assert get_task_arns(client, "cluster") == ["task-1", "task-2"]
