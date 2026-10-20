# shellcheck shell=sh
# Downloads a file from S3 into the container, using a presigned URL.
#
# Variables set by aws-excom:
#   DEST  Path to save the file to in the container
#   URL   Presigned 'GetObject' URL of the file

set -eu
: "${DEST:?}" "${URL:?}"

if ! command -v curl >/dev/null; then
    echo "curl not found in container"
    exit 1
fi

if [ -d "$DEST" ]; then
    echo "Is a directory: $DEST"
    exit 1
fi

dir=$(dirname "$DEST")
if [ ! -d "$dir" ]; then
    echo "No such directory: $dir"
    exit 1
fi

# Downloaded beside DEST first, so a failed download never leaves it half-written
TMP="$DEST.aws-excom-part.$$"
trap 'rm -f "$TMP"' EXIT
curl -sSf -o "$TMP" "$URL"
# Copied rather than moved, so an existing file keeps its permissions and owner
cat "$TMP" >"$DEST"

size=$(stat -c %s "$DEST" 2>/dev/null || wc -c <"$DEST")
# Marker is matched by aws_excom.transfer.SIZE_PATTERN
echo "AWS_EXCOM_SIZE=$size"
