import boto3

from aws_excom import grouper

MAX_DESCRIBE_CLUSTERS = 100
MAX_DESCRIBE_TASKS = 100


def get_boto_session(profile_name=None, region_name=None):
    return boto3.session.Session(profile_name=profile_name, region_name=region_name)


def get_ecs_client(session):
    return session.client("ecs")


def get_cluster_arns(ecs_client):
    cluster_arns = []
    response = ecs_client.list_clusters()
    cluster_arns.extend(response["clusterArns"])
    next_token = response.get("nextToken", None)
    while next_token:
        response = ecs_client.list_clusters(nextToken=next_token)
        cluster_arns.extend(response["clusterArns"])
        next_token = response.get("nextToken", None)
    return cluster_arns


def get_clusters_data(ecs_client, cluster_arns, order_by="clusterName"):
    clusters = []
    for arns in grouper(cluster_arns, MAX_DESCRIBE_CLUSTERS):
        arns = [*filter(lambda arn: arn is not None, arns)]
        response = ecs_client.describe_clusters(clusters=arns)
        clusters.extend(response["clusters"])

    return sorted(clusters, key=lambda cluster: cluster[order_by].lower())


def get_task_arns(ecs_client, cluster_arn):
    task_arns = []
    response = ecs_client.list_tasks(cluster=cluster_arn)
    task_arns.extend(response["taskArns"])
    next_token = response.get("nextToken", None)
    while next_token:
        response = ecs_client.list_tasks(cluster=cluster_arn, nextToken=next_token)
        task_arns.extend(response["clusterArns"])
        next_token = response.get("nextToken", None)
    return task_arns


def get_tasks_data(ecs_client, cluster_arn, task_arns):
    tasks = []
    for arns in grouper(task_arns, MAX_DESCRIBE_TASKS):
        arns = [*filter(lambda arn: arn is not None, arns)]
        response = ecs_client.describe_tasks(cluster=cluster_arn, tasks=arns)
        tasks.extend(response["tasks"])

    return tasks


def get_containers_data(tasks_data, order_by="name"):
    containers = []
    for task in tasks_data:
        for container in task["containers"]:
            container["taskLaunchType"] = task["launchType"]
            task_definition_arn = task["taskDefinitionArn"]
            task_definition_revision = task_definition_arn.split(":")[-1]
            container["taskDefinitionRevision"] = task_definition_revision
            containers.append(container)

    return sorted(containers, key=lambda container: container[order_by].lower())
