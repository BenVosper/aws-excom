import json
from os import environ

import re
import sys

from shutil import rmtree
from subprocess import run

rmtree("./dist", ignore_errors=True)

deploy_output = run(
    "python -m build && python3 -m twine upload --skip-existing dist/*",
    shell=True,
    capture_output=True,
    timeout=60,
)

stderr = deploy_output.stderr.decode()
stdout = deploy_output.stdout.decode()
print(stderr)
print(stdout)

if deploy_output.returncode != 0:
    sys.exit(1)


successful_upload_regex = re.compile(
    r"View at:\n(?P<url>https://pypi\.org/project/aws-excom/(?P<version>.+)/)"
)

match = successful_upload_regex.match(stdout)
if match:
    version = match.group("version")
    url = match.group("url")
    release_data = {"tag_name": version, "name": version, "body": url}
    run(
        f"""curl -X POST \
            -H "Accept: application/vnd.github.v3+json" \
            -H "Authorization: Bearer {environ['RELEASE_TOKEN']}" \
            -d '{json.dumps(release_data)}' \
            https://api.github.com/repos/BenVosper/aws-excom/releases
        """,
        shell=True,
    )
