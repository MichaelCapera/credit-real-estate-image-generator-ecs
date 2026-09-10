import io
import os
import logging
import boto3
from botocore.config import Config

logger = logging.getLogger(__name__)


class S3Service:
    """
    Service responsible for handling direct asset uploads to Amazon S3.
    """

    def __init__(self):
        aws_config = Config(
            max_pool_connections=50, retries={"max_attempts": 3, "mode": "standard"}
        )
        self.s3_client = boto3.client("s3", config=aws_config)
        self.bucket_name = os.getenv("AWS_S3_BUCKET_NAME") or os.getenv(
            "S3_BUCKET_NAME"
        )
        if not self.bucket_name:
            logger.warning(
                "[S3 WARNING] AWS_S3_BUCKET_NAME or S3_BUCKET_NAME environment variable is not set."
            )

    def upload_bytes_to_s3(
        self, img_bytes, file_name: str, subfolder: str = "stories"
    ) -> str:
        """
        Uploads in-memory image stream directly to the target S3 folder structure
        and returns the public URL without closing the original stream.
        """
        if not self.bucket_name:
            logger.error("[S3 ERROR] Bucket name is missing. Cannot upload bytes.")
            return ""

        try:
            s3_key = f"publicity-assets/properties/{subfolder}/{file_name}"

            img_bytes.seek(0)
            upload_stream = io.BytesIO(img_bytes.read())
            img_bytes.seek(
                0
            )

            self.s3_client.upload_fileobj(
                upload_stream,
                self.bucket_name,
                s3_key,
                ExtraArgs={"ContentType": "image/jpeg"},
            )

            region = self.s3_client.meta.region_name or os.getenv(
                "AWS_REGION", "us-east-1"
            )
            public_url = (
                f"https://{self.bucket_name}.s3.{region}.amazonaws.com/{s3_key}"
            )
            logger.info(f"[S3] Asset successfully uploaded to: {public_url}")
            return public_url

        except Exception as e:
            logger.error(f"[S3 EXCEPTION] Failed to upload bytes to S3: {str(e)}")
            return ""
