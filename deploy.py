import json
import sys

from os import environ
from shutil import rmtree
from subprocess import run
from urllib.error import HTTPError
from urllib.request import Request, urlopen

rmtree("./dist", ignore_errors=True)

deploy_output = run(
    "python -m build && python3 -m twine upload --skip-existing --non-interactive dist/*",
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

stdout_lines = stdout.split("\n")
deployed_new_version = "View at:" in stdout_lines[-3]
if not deployed_new_version:
    sys.exit(0)

new_version_pypi_url = stdout_lines[-2]
new_version = new_version_pypi_url.split("/")[-2]

release_data = {
    "tag_name": new_version,
    "name": new_version,
    "body": new_version_pypi_url,
}
request = Request(
    "https://api.github.com/repos/BenVosper/aws-excom/releases",
    data=json.dumps(release_data).encode(),
    headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {environ['RELEASE_TOKEN']}",
        "X-GitHub-Api-Version": "2022-11-28",
    },
    method="POST",
)
try:
    with urlopen(request, timeout=30) as response:
        print(f"Created GitHub release: {json.load(response)['html_url']}")
except HTTPError as error:
    print(f"Failed to create GitHub release: {error.code} {error.reason}")
    print(error.read().decode())
    sys.exit(1)
