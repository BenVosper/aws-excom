"""
Pull files out of a running container via S3 multipart upload.

The container never needs AWS credentials or the AWS CLI - only 'sh', 'dd' and
'curl'. All signing happens locally.

Scripts run in the container live in 'scripts/'. Each is staged in S3 with its inputs
prepended and fetched by a one-line 'curl | sh', so the command passed to
'execute-command' stays short however many parts there are.

1. Run 'size.sh' in the container to get the file's size.
2. Create a multipart upload and presign one 'UploadPart' URL per part.
3. Run 'upload.sh' in the container. It slices the file with 'dd' and PUTs each slice.
4. Check the parts landed, complete the upload, download the object and clean up.
"""

import math
import os
import pathlib
import re
import shlex
import uuid

from botocore.config import Config

MIB = 1024 * 1024
MIN_PART_SIZE_MIB = 16
MAX_PARTS = 10000
URL_EXPIRY_SECONDS = 6 * 60 * 60
KEY_PREFIX = "aws-excom"

SCRIPTS_DIR = pathlib.Path(__file__).parent / "scripts"
SIZE_PATTERN = re.compile(r"AWS_EXCOM_SIZE=(\d+)")


class TransferError(Exception):
    pass


def get_s3_client(session, bucket):
    """
    Client in the bucket's own region, so presigned URLs point straight at it rather
    than relying on a redirect, which curl won't follow for an upload.
    """
    location = session.client("s3").get_bucket_location(Bucket=bucket)
    region = location["LocationConstraint"] or "us-east-1"
    return session.client(
        "s3",
        region_name=region,
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
    )


def get_part_size_mib(file_size):
    """Smallest whole-MiB part size (>= the minimum) that fits within S3's part limit"""
    return max(MIN_PART_SIZE_MIB, math.ceil(file_size / MAX_PARTS / MIB))


def get_part_count(file_size, part_size_mib):
    return max(1, math.ceil(file_size / (part_size_mib * MIB)))


def parse_size_output(output):
    match = SIZE_PATTERN.search(output)
    if not match:
        raise TransferError(f"Couldn't determine remote file size. Output:\n{output}")
    return int(match.group(1))


def render_script(name, **variables):
    """Script from 'scripts/' with the given variables assigned at the top"""
    assignments = "".join(
        f"{key}={shlex.quote(str(value))}\n" for key, value in variables.items()
    )
    return assignments + (SCRIPTS_DIR / name).read_text()


def build_bootstrap_command(script_url):
    script = f"curl -sSf {shlex.quote(script_url)} | sh"
    return f"sh -c {shlex.quote(script)}"


class S3Transfer:
    """Owns the S3 side of a single file transfer, including cleanup"""

    def __init__(self, s3_client, bucket, remote_path):
        self.s3 = s3_client
        self.bucket = bucket
        prefix = f"{KEY_PREFIX}/{uuid.uuid4()}"
        self.key = f"{prefix}/{os.path.basename(remote_path) or 'file'}"
        self.prefix = prefix
        self.staged_keys = [self.key]
        self.remote_path = remote_path
        self.upload_id = None
        self.part_count = None

    def stage_script(self, name, **variables):
        """Put a script in S3 and return the command that runs it in the container"""
        key = f"{self.prefix}/{name}"
        script = render_script(name, **variables)
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=script.encode())
        self.staged_keys.append(key)
        script_url = self.s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=URL_EXPIRY_SECONDS,
        )
        return build_bootstrap_command(script_url)

    def get_size_command(self):
        return self.stage_script("size.sh", SRC=self.remote_path)

    def prepare(self, file_size):
        """Start the multipart upload and return the command to run in the container"""
        part_size_mib = get_part_size_mib(file_size)
        self.part_count = get_part_count(file_size, part_size_mib)

        response = self.s3.create_multipart_upload(Bucket=self.bucket, Key=self.key)
        self.upload_id = response["UploadId"]

        part_urls = [
            self.s3.generate_presigned_url(
                "upload_part",
                Params={
                    "Bucket": self.bucket,
                    "Key": self.key,
                    "UploadId": self.upload_id,
                    "PartNumber": number,
                },
                ExpiresIn=URL_EXPIRY_SECONDS,
            )
            for number in range(1, self.part_count + 1)
        ]
        return self.stage_script(
            "upload.sh",
            SRC=self.remote_path,
            PART_MIB=part_size_mib,
            PART_URLS="\n".join(part_urls),
        )

    def get_uploaded_parts(self):
        parts = []
        paginator = self.s3.get_paginator("list_parts")
        for page in paginator.paginate(
            Bucket=self.bucket, Key=self.key, UploadId=self.upload_id
        ):
            parts.extend(page.get("Parts", []))
        return parts

    def complete(self):
        parts = self.get_uploaded_parts()
        if len(parts) != self.part_count:
            raise TransferError(
                f"Only {len(parts)} of {self.part_count} parts were uploaded"
            )
        self.s3.complete_multipart_upload(
            Bucket=self.bucket,
            Key=self.key,
            UploadId=self.upload_id,
            MultipartUpload={
                "Parts": [
                    {"PartNumber": part["PartNumber"], "ETag": part["ETag"]}
                    for part in parts
                ]
            },
        )
        self.upload_id = None

    def download(self, local_path):
        self.s3.download_file(self.bucket, self.key, local_path)

    def cleanup(self):
        if self.upload_id:
            self.s3.abort_multipart_upload(
                Bucket=self.bucket, Key=self.key, UploadId=self.upload_id
            )
        self.s3.delete_objects(
            Bucket=self.bucket,
            Delete={"Objects": [{"Key": key} for key in self.staged_keys]},
        )
