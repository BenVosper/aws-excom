# shellcheck shell=sh
# Uploads a file from the container to S3 in parts, using presigned URLs.
#
# Variables set by aws-excom:
#   SRC        Path of the file in the container
#   PART_MIB   Size of each part in MiB
#   PART_URLS  Newline-separated presigned 'UploadPart' URLs, in part order

# No globbing, so the '?' in each URL is left alone when splitting PART_URLS
set -euf
: "${SRC:?}" "${PART_MIB:?}" "${PART_URLS:?}"

if ! command -v curl >/dev/null; then
    echo "curl not found in container"
    exit 1
fi

TMP="${TMPDIR:-/tmp}/aws-excom-part.$$"
trap 'rm -f "$TMP"' EXIT

# shellcheck disable=SC2086 # Splitting PART_URLS into words is intended
set -- $PART_URLS
parts=$#

upload_part() {
    number=$1
    url=$2
    dd if="$SRC" of="$TMP" bs=1048576 \
        skip=$(((number - 1) * PART_MIB)) count="$PART_MIB" 2>/dev/null ||
        return 1
    for attempt in 1 2 3 4 5; do
        curl -sSf -o /dev/null -T "$TMP" "$url" && return 0
        echo "Part $number failed (attempt $attempt), retrying..."
        sleep "$attempt"
    done
    return 1
}

number=1
for url in "$@"; do
    if ! upload_part "$number" "$url"; then
        echo "Upload failed on part $number"
        exit 1
    fi
    echo "Uploaded part $number/$parts"
    number=$((number + 1))
done

echo "Upload complete"
