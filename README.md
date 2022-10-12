## `aws-excom`

An interactive wrapper around `aws ecs execute-command`.

### Installation

Requires [AWS CLI](https://aws.amazon.com/cli/) and 
[AWS CLI Session Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html)
to be installed on the system and configured with appropriate credentials.

Then, to install the script:
```shell
pip install aws-excom
```

### Usage

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
