# `aws-excom`

An interactive wrapper around `aws ecs execute-command`.

## Installation

Requires [AWS CLI](https://aws.amazon.com/cli/) and 
[AWS CLI Session Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html)
to be installed on the system and configured with appropriate credentials.

Then, to install the script:
```shell
pip install aws-excom
```

## Usage

```shell
aws-excom
```
Then follow the prompts to start running commands.

After running once, you can run:

```shell
aws-excom --last
```

to skip the interactive part of the script and immediately replay the last command you 
constructed. This may be useful if you accidentally exit a running session.

By default, all AWS commands will use your default profile and region. To override these, pass 
the following arguments:

```shell
aws-excom --profile foo --region us-east-1
```

By default you'll be given an interactive prompt to enter the command to execute. To skip this, 
you may optionally provide a '--command' argument eg.:

```shell
aws-excom --command "python3"
```

This is handy for writing aliases for common commands:

```shell
# File: aws-excom-django-python-shell.sh

#!/bin/sh
aws-excom --command "python3 manage.py shell" "$@"
```

## Downloading files

To pull a file out of a container, use the `get` subcommand with an S3 bucket to stage it 
through:

```shell
aws-excom get /app/logs/big.log --bucket my-bucket [--output big.log]
```

Set `AWS_EXCOM_BUCKET` to avoid passing `--bucket` every time.

The file is uploaded with an S3 multipart upload (up to 5 TB) using URLs presigned with 
your local credentials, so the container needs no AWS credentials or CLI - only `sh`, `dd`, 
`curl` and network access to S3. Each part is buffered to `$TMPDIR` (or `/tmp`) in the 
container, so it needs at least one part's worth (16 MiB for files under ~160 GB) of free 
space. Staged objects are deleted once downloaded. Your local credentials need 
`s3:PutObject`, `s3:GetObject`, `s3:DeleteObject`, `s3:ListMultipartUploadParts`, 
`s3:AbortMultipartUpload` and `s3:GetBucketLocation` on the bucket.

## Uploading files

To put a file into a container, use the `put` subcommand, staged through S3 in the same way:

```shell
aws-excom put fixtures.json /app/fixtures.json --bucket my-bucket
aws-excom put fixtures.json /app/  # Keeps the local filename
```

If the file already exists in the container, you'll be asked before it's overwritten, unless 
you pass `--force`. An overwritten file keeps its permissions and owner.

The container fetches the file from a presigned URL with `curl`, so again needs no AWS 
credentials. It's downloaded beside the destination first, so the destination's filesystem 
needs room for two copies while it's copied into place.

## Running a command on several containers

To run one command across containers in one or more clusters, use the `batch` subcommand:

```shell
aws-excom batch --command "python manage.py migrate foo 0003"
```

You'll be asked to pick one or more clusters, then one or more containers in each 
(Space or Tab to select, Enter to accept). The command is run on each container in turn 
by `sh`, and each container's output is saved to its own file in `batch_outputs/` (or 
`--output-dir`), named with the run's timestamp, cluster and container. Containers with 
the same name in the same cluster are numbered:

```
batch_outputs/
├── 20261020-130523_prod-eu_gunicorn.txt
├── 20261020-130523_prod-us_gunicorn_1.txt
└── 20261020-130523_prod-us_gunicorn_2.txt
```

A summary of exit statuses is printed at the end. `execute-command` doesn't report the 
command's exit status, so the command is run between two markers printed by `aws-excom`: 
`AWS_EXCOM_START` before and `AWS_EXCOM_EXIT=<status>` after. Saved outputs are trimmed to 
what's between them, leaving out the session's own start and exit lines. If the command 
never started (eg. the session failed to connect), the whole output is saved instead.

For anything longer than a one-liner, pass `--command-file`. The file is staged through S3 
(see [Downloading files](#downloading-files) for the bucket setup and requirements) and passed 
to the command on stdin, as if running `<command> < <file>` in the container. Eg. to run a 
Python script:

```shell
aws-excom batch --command "python" --command-file script.py --bucket my-bucket
```

Or to run a script in the Django shell, with models and settings available:

```shell
aws-excom batch --command "python manage.py shell" --command-file analytics.py --bucket my-bucket
```

## Local Development

Before installing the package in development mode, you may find it convenient to create a 
virtual environment in which to install dependencies. The recommended way of doing this is
using Python's built-in `venv` module:

```shell
# Create a directory for your environments if you don't have one already
mkdir ~/.venv  

# Your environment can have any name
python -m venv ~/.venv/my-aws-excom-env  
```

Next you need to activate the environment in your shell:

```shell
source ~/.venv/my-aws-excom-env/bin/activate
```

Now you're ready to install the package and its dependencies:

```shell
cd aws-excom

# -e: Editable mode
pip install -e .
```

You can verify this has worked by running:
```shell
which aws-excom
```

This prints the location of the main script installed by the package, which should be 
inside your virtual environment: `~/.venv/my-aws-excom-env/aws-excom/bin/aws-excom`.

Now, running `aws-excom` in your shell will use the code you have locally. Any changes
you make to source files will be automatically used when you next run the command.

### Other Python Versions

To test the package against different Python versions, first ensure that any required 
versions are installed. They should be accessible using `python3.8` / `python3.7` or
similar.

Now you can simply create a suitable virtual environment using this Python version:

```shell
# Your environment can have any name
python3.8 -m venv ~/.venv/my-py38-aws-excom-env  
```

After activating the environment, you can verify the environment contains the Python
version you've chosen using:

```shell
python --version
```

Inside this environment `aws-excom` will now run using this Python version. 

### Testing

Install the optional development tools for testing and linting:

```shell
pip install -e .[dev]
```

Run the test suite using:

```shell
pytest
```
