# shellcheck shell=sh
# Runs a command in the container with a staged file as its stdin.
#
# Variables set by aws-excom:
#   CMD        Command to run, interpreted by 'sh'
#   INPUT_URL  Presigned URL of the file to pass to CMD on stdin

set -eu
: "${CMD:?}" "${INPUT_URL:?}"

if ! command -v curl >/dev/null; then
    echo "curl not found in container"
    exit 1
fi

INPUT="${TMPDIR:-/tmp}/aws-excom-input.$$"
trap 'rm -f "$INPUT"' EXIT

# Downloaded in full first so CMD sees all of its input at once. Some commands, like
# Django's 'shell', only read stdin as a script if it's ready when they start.
curl -sSf -o "$INPUT" "$INPUT_URL"

set +e
# Ctrl-C is forwarded to the container and reaches this shell as well as CMD. A
# handler, unlike ignoring it, lets CMD be interrupted while this shell carries on
# to print the exit marker.
trap : INT
# Markers are matched by aws_excom.batch, which keeps only the output between them
echo "AWS_EXCOM_START"
sh -c "$CMD" <"$INPUT"
status=$?
echo "AWS_EXCOM_EXIT=$status"
exit "$status"
