# shellcheck shell=sh
# Prints the size of a file in the container, for aws-excom to parse.
#
# Variables set by aws-excom:
#   SRC  Path of the file in the container

set -eu
: "${SRC:?}"

if [ ! -f "$SRC" ]; then
    # Message is matched by aws_excom.transfer.NO_FILE_MESSAGE
    echo "No such file: $SRC"
    exit 1
fi

size=$(stat -c %s "$SRC" 2>/dev/null || wc -c <"$SRC")
# Marker is matched by aws_excom.transfer.SIZE_PATTERN
echo "AWS_EXCOM_SIZE=$size"
