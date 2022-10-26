import json
import sys

from os import environ
from shutil import rmtree
from subprocess import run

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
run(
    f"""curl -X POST \
        -H "Accept: application/vnd.github.v3+json" \
        -H "Authorization: Bearer {environ['RELEASE_TOKEN']}" \
        -d '{json.dumps(release_data)}' \
        https://api.github.com/repos/BenVosper/aws-excom/releases
    """,
    shell=True,
)
