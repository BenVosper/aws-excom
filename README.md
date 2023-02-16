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
