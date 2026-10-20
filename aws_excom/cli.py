import argparse
import os
import sys
import tempfile
import readline  # Needed for correct 'input' behaviour

from subprocess import run, PIPE

from simple_term_menu import TerminalMenu
from termcolor import colored

from aws_excom import ignore_user_entered_signals
from aws_excom.aws import (
    get_boto_session,
    get_ecs_client,
    get_cluster_arns,
    get_clusters_data,
    get_task_arns,
    get_tasks_data,
    get_containers_data,
)
from aws_excom.batch import (
    build_inline_command,
    get_output_paths,
    get_task_id,
    get_timestamp,
    run_and_save,
)
from aws_excom.exceptions import BOTOCORE_EXCEPTIONS
from aws_excom.transfer import (
    S3Staging,
    S3Transfer,
    TransferError,
    get_s3_client,
    parse_size_output,
)


def add_common_arguments(parser, default=None):
    """
    Options accepted both before and after a subcommand name. Subcommands pass
    'argparse.SUPPRESS' so they don't overwrite values given before the subcommand.
    """
    parser.add_argument(
        "--profile", default=default, help="(Optional) Name of AWS profile to use"
    )
    parser.add_argument(
        "--region", default=default, help="(Optional) Name of AWS region to use"
    )


parser = argparse.ArgumentParser(
    description="Interactive script to call 'aws ecs execute-command'"
)
add_common_arguments(parser)
parser.add_argument(
    "--last", action="store_true", help="Run 'execute-command' with last input"
)
parser.add_argument(
    "--command",
    default=None,
    help="(Optional) Command to execute. Leave blank for an interactive prompt",
)

subparsers = parser.add_subparsers(dest="subcommand", metavar="SUBCOMMAND")

get_parser = subparsers.add_parser(
    "get",
    help="Download a file from a container via S3",
    description="Download a file from a container via S3",
)
add_common_arguments(get_parser, default=argparse.SUPPRESS)
get_parser.add_argument("remote_path", help="Path of the file in the container")
get_parser.add_argument(
    "--bucket",
    default=os.environ.get("AWS_EXCOM_BUCKET"),
    help="S3 bucket to stage the download through. Defaults to $AWS_EXCOM_BUCKET",
)
get_parser.add_argument(
    "--output",
    "-o",
    default=None,
    help="(Optional) Local path to save to. Defaults to the remote filename",
)

batch_parser = subparsers.add_parser(
    "batch",
    help="Run a command on several containers, saving the outputs",
    description=(
        "Run a command on one or more containers in one or more clusters, one at a "
        "time, saving each container's output to a file. Commands are run by 'sh'."
    ),
)
add_common_arguments(batch_parser, default=argparse.SUPPRESS)
batch_parser.add_argument(
    "--command",
    # Kept apart from the top-level '--command' so 'main' can tell them apart
    dest="batch_command",
    metavar="COMMAND",
    default=None,
    help=(
        "(Optional) Command to run. With '--command-file', the file is passed to it "
        "on stdin. Leave blank for an interactive prompt"
    ),
)
batch_parser.add_argument(
    "--command-file",
    default=None,
    help=(
        "(Optional) Local file to pass to the command on stdin, eg. a script for "
        "'python manage.py shell'. Staged through S3"
    ),
)
batch_parser.add_argument(
    "--bucket",
    default=os.environ.get("AWS_EXCOM_BUCKET"),
    help=("S3 bucket to stage '--command-file' through. Defaults to $AWS_EXCOM_BUCKET"),
)
batch_parser.add_argument(
    "--output-dir",
    default="batch_outputs",
    help="(Optional) Directory to save outputs under. Defaults to 'batch_outputs'",
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
    if not containers:
        raise AssertionError("Must provide one or more containers")

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


def show_menu(title, entries, multi_select=False):
    """Indices of the selected entries. Exits if the menu is quit"""
    if multi_select:
        keys = "Space or Tab to select, Enter to accept"
    else:
        keys = "Enter to select"
    print(get_bold_text(f"{title} (Arrow keys to move, {keys}, / to search)"))
    terminal_menu = TerminalMenu(entries, multi_select=multi_select)
    selected = terminal_menu.show()
    if selected is None:
        sys.exit()
    return list(selected) if multi_select else [selected]


def select_clusters(client, multi_select=False):
    cluster_arns = get_cluster_arns(client)
    clusters = get_clusters_data(client, cluster_arns)
    cluster_names = [cluster["clusterName"] for cluster in clusters]

    title = "Select clusters..." if multi_select else "Select a cluster..."
    selected_indices = show_menu(title, cluster_names, multi_select)
    for index in selected_indices:
        print(f"Cluster: {cluster_names[index]}")
    return [clusters[index] for index in selected_indices]


def select_containers(client, cluster, multi_select=False):
    """Selected containers in the cluster, or an empty list if it has none"""
    task_arns = get_task_arns(client, cluster["clusterArn"])
    tasks = get_tasks_data(client, cluster["clusterArn"], task_arns)
    containers = get_containers_data(tasks)
    if not containers:
        return []
    container_names = [*get_container_display_names(containers)]

    title = "Select containers" if multi_select else "Select a container"
    title += f" in '{cluster['clusterName']}'..."
    selected_indices = show_menu(title, container_names, multi_select)
    for index in selected_indices:
        print(f"Container: {container_names[index]}")
    return [containers[index] for index in selected_indices]


def select_container(session):
    client = get_ecs_client(session)
    [cluster] = select_clusters(client)
    containers = select_containers(client, cluster)
    if not containers:
        print("No containers found. Exiting...")
        sys.exit()
    return cluster["clusterArn"], containers[0]


def build_aws_cli_command(profile_name=None, region_name=None, command_to_execute=None):
    session = get_boto_session(profile_name, region_name)
    selected_cluster_arn, selected_container_data = select_container(session)

    command = command_to_execute
    if not command:
        prompt = get_bold_text("Type command to execute... (Default: 'bash') ")
        command = input(prompt) or "bash"

    print(f"Command: '{command}'\n")

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


def build_execute_command_args(
    cluster_arn, container, command, profile_name=None, region_name=None
):
    args = [
        "aws",
        "ecs",
        "execute-command",
        "--cluster",
        cluster_arn,
        "--task",
        container["taskArn"],
        "--container",
        container["name"],
        "--interactive",
        "--command",
        command,
    ]
    if profile_name:
        args += ["--profile", profile_name]
    if region_name:
        args += ["--region", region_name]
    return args


def get_file(remote_path, bucket, local_path, profile_name=None, region_name=None):
    session = get_boto_session(profile_name, region_name)
    s3 = get_s3_client(session, bucket)
    cluster_arn, container = select_container(session)

    def execute(command, **kwargs):
        args = build_execute_command_args(
            cluster_arn, container, command, profile_name, region_name
        )
        with ignore_user_entered_signals():
            return run(args, check=False, **kwargs)

    transfer = S3Transfer(s3, bucket, remote_path)
    local_path = local_path or os.path.basename(remote_path)
    try:
        print(f"Checking size of '{remote_path}'...")
        result = execute(transfer.get_size_command(), stdout=PIPE, text=True)
        file_size = parse_size_output(result.stdout)
        print(f"Size: {file_size:,} bytes")

        command = transfer.prepare(file_size)
        print(
            f"Uploading to s3://{bucket}/{transfer.key} "
            f"in {transfer.part_count} part(s)..."
        )
        execute(command)
        transfer.complete()
        print(f"Downloading to '{local_path}'...")
        transfer.download(local_path)
    finally:
        transfer.cleanup()
    print("Done")


def run_get(args):
    if not args.bucket:
        get_parser.error("requires '--bucket' or $AWS_EXCOM_BUCKET")
    try:
        get_file(args.remote_path, args.bucket, args.output, args.profile, args.region)
    except (TransferError, *BOTOCORE_EXCEPTIONS) as error:
        print(error)
        sys.exit(1)


def run_on_containers(
    command,
    command_file,
    bucket,
    output_dir,
    profile_name=None,
    region_name=None,
):
    session = get_boto_session(profile_name, region_name)
    client = get_ecs_client(session)
    staging = None
    if command_file:
        staging = S3Staging(get_s3_client(session, bucket), bucket)

    targets = []
    for cluster in select_clusters(client, multi_select=True):
        containers = select_containers(client, cluster, multi_select=True)
        if not containers:
            print(f"No containers found in '{cluster['clusterName']}'. Skipping...")
        targets += [(cluster, container) for container in containers]
    if not targets:
        print("No containers selected. Exiting...")
        sys.exit()

    if not command:
        if command_file:
            prompt = f"Type command to pass '{command_file}' to... (Default: 'sh') "
        else:
            prompt = "Type command to run... "
        command = input(get_bold_text(prompt)) or ("sh" if command_file else "")
        if not command:
            print("No command given. Exiting...")
            sys.exit()
    print(f"Command: '{command}'\n")

    timestamp = get_timestamp()

    results = []
    try:
        if staging:
            with open(command_file, "rb") as f:
                input_url = staging.stage(os.path.basename(command_file), f.read())
            remote_command = staging.stage_script(
                "run.sh", CMD=command, INPUT_URL=input_url
            )
        else:
            remote_command = build_inline_command(command)

        output_paths = get_output_paths(output_dir, timestamp, targets)
        for number, ((cluster, container), output_path) in enumerate(
            zip(targets, output_paths), start=1
        ):
            cluster_name = cluster["clusterName"]
            label = f"{cluster_name} / {container['name']} ({get_task_id(container)})"
            print(get_bold_text(f"[{number}/{len(targets)}] {label}"))
            args = build_execute_command_args(
                cluster["clusterArn"],
                container,
                remote_command,
                profile_name,
                region_name,
            )
            status = run_and_save(args, output_path)
            results.append((label, status, output_path))
            print()
    finally:
        if staging:
            staging.cleanup()

    print(get_bold_text("Summary"))
    for label, status, output_path in results:
        status_text = "unknown" if status is None else str(status)
        print(f"{label}: exit {status_text} -> {output_path}")
    return all(status == 0 for _, status, _ in results)


def run_batch(args):
    if args.command_file:
        if not args.bucket:
            batch_parser.error(
                "'--command-file' requires '--bucket' or $AWS_EXCOM_BUCKET"
            )
        if not os.path.isfile(args.command_file):
            batch_parser.error(f"No such file: '{args.command_file}'")
    try:
        succeeded = run_on_containers(
            args.batch_command,
            args.command_file,
            args.bucket,
            args.output_dir,
            args.profile,
            args.region,
        )
    except (TransferError, *BOTOCORE_EXCEPTIONS) as error:
        print(error)
        sys.exit(1)
    if not succeeded:
        sys.exit(1)


SUBCOMMANDS = {
    "get": run_get,
    "batch": run_batch,
}


def run_execute_command(args):
    profile = args.profile
    region = args.region
    command = args.command

    last_run_command = get_last_run_command()

    if args.last:
        if not last_run_command:
            print("No last run found. Try again with default arguments")
            sys.exit(0)
        aws_cli_command = last_run_command
    else:
        try:
            aws_cli_command = build_aws_cli_command(profile, region, command)
        except (*BOTOCORE_EXCEPTIONS,) as error:
            print(error)
            sys.exit(1)

    cleanup_last_run_files()
    write_last_run_file(aws_cli_command)

    print("Starting session. Ctrl-D to exit.")
    with ignore_user_entered_signals():
        run(
            aws_cli_command,
            shell=True,
            check=False,
        )


def main():
    args = parser.parse_args()

    if args.subcommand:
        if args.last or args.command:
            parser.error(
                f"'--last' and '--command' can't be used with '{args.subcommand}'"
            )
        SUBCOMMANDS[args.subcommand](args)
        return

    run_execute_command(args)
