import argparse
import os
import sys
import tempfile
import readline  # Needed for correct 'input' behaviour

from subprocess import run

from simple_term_menu import TerminalMenu
from termcolor import colored

from aws_excom.aws import (
    get_boto_session,
    get_ecs_client,
    get_cluster_arns,
    get_clusters_data,
    get_task_arns,
    get_tasks_data,
    get_containers_data,
)

parser = argparse.ArgumentParser(
    description="Interactive script to call 'aws ecs execute-command'"
)
parser.add_argument(
    "--last", action="store_true", help="Run 'execute-command' with last input"
)
parser.add_argument(
    "--profile", default=None, help="(Optional) Name of AWS profile to use"
)
parser.add_argument(
    "--region", default=None, help="(Optional) Name of AWS region to use"
)


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


def get_last_run_command():
    last_run_file_paths = get_last_run_file_paths()
    last_run_command = None
    if last_run_file_paths:
        with open(last_run_file_paths[0]) as f:
            last_run_command = f.read()
    return last_run_command


def cleanup_last_run_files():
    for path in get_last_run_file_paths():
        os.remove(path)


def write_last_run_file(command):
    with tempfile.NamedTemporaryFile(
        "w",
        dir=TEMPDIR,
        prefix=LAST_RUN_FILENAME_PREFIX,
        delete=False,
    ) as f:
        f.write(command)


def get_container_display_names(containers):
    names = [container["name"] for container in containers]
    launch_types = [container["taskLaunchType"] for container in containers]
    statuses = [container["lastStatus"] for container in containers]
    revisions = [container["taskDefinitionRevision"] for container in containers]

    longest_name_len = len(max(names, key=len))
    longest_launch_type_len = len(max(launch_types, key=len))
    longest_status_len = len(max(statuses, key=len))

    names = [name.ljust(longest_name_len) for name in names]
    launch_types = [
        launch_type.ljust(longest_launch_type_len) for launch_type in launch_types
    ]
    statuses = [status.ljust(longest_status_len) for status in statuses]

    return (
        f"{name}    {launch_type}    {status}     {revision}"
        for name, launch_type, status, revision in zip(
            names, launch_types, statuses, revisions
        )
    )


def get_bold_text(text):
    return colored(text, attrs=["bold"])


def build_aws_cli_command(profile_name=None, region_name=None):
    session = get_boto_session(profile_name, region_name)
    client = get_ecs_client(session)
    cluster_arns = get_cluster_arns(client)
    clusters = get_clusters_data(client, cluster_arns)

    cluster_names = [cluster["clusterName"] for cluster in clusters]

    print(
        get_bold_text(
            "Select a cluster... (Arrow keys to move, Enter to select, / to search)"
        )
    )
    terminal_menu = TerminalMenu(cluster_names)
    selected_index = terminal_menu.show()
    if selected_index is None:
        sys.exit()
    selected_cluster_name = cluster_names[selected_index]
    selected_cluster_data = clusters[selected_index]
    selected_cluster_arn = selected_cluster_data["clusterArn"]
    print(f"Cluster: {selected_cluster_name}")

    task_arns = get_task_arns(client, selected_cluster_data["clusterArn"])
    tasks = get_tasks_data(client, selected_cluster_arn, task_arns)
    containers = get_containers_data(tasks)
    container_names = [*get_container_display_names(containers)]

    print(
        get_bold_text(
            "Select a container... (Arrow keys to move, Enter to select, / to search)"
        )
    )
    terminal_menu = TerminalMenu(container_names)
    selected_index = terminal_menu.show()
    if selected_index is None:
        sys.exit()
    selected_container_name = container_names[selected_index]
    selected_container_data = containers[selected_index]
    print(f"Container: {selected_container_name}")

    prompt = get_bold_text("Type command to execute... (Default: 'bash') ")
    command = input(prompt) or "bash"
    print(f"Command: '{command}'")

    aws_ecs_command = (
        f"aws ecs execute-command "
        f"--task {selected_container_data['taskArn']} "
        f"--cluster {selected_cluster_arn} "
        f"--interactive "
        f"--command '{command}' "
    )
    if profile_name:
        aws_ecs_command += f"--profile {profile_name} "
    if region_name:
        aws_ecs_command += f"--region {region_name} "
    return aws_ecs_command


def main():
    args = parser.parse_args()
    profile = args.profile
    region = args.region

    last_run_command = get_last_run_command()

    if args.last:
        if not last_run_command:
            print("No last run found. Try again with default arguments")
            sys.exit(0)
        aws_cli_command = last_run_command
    else:
        aws_cli_command = build_aws_cli_command(profile, region)

    cleanup_last_run_files()
    write_last_run_file(aws_cli_command)

    print("Starting session. Ctrl-D to exit.")
    run(
        aws_cli_command,
        shell=True,
        check=False,
    )
