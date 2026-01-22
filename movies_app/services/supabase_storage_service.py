import logging

import boto3
import requests
from botocore.config import Config
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class SupabaseStorageError(Exception):
    pass


class SupabaseStorageService:
    """
    Service for uploading and managing images in Supabase S3-compatible storage.
    """

    def __init__(
        self,
        bucket_url: str,
        access_key_id: str,
        secret_access_key: str,
        bucket_name: str,
    ):
        self.bucket_url = bucket_url.rstrip("/")
        self.bucket_name = bucket_name
        self._client = boto3.client(
            "s3",
            endpoint_url=bucket_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=Config(signature_version="s3v4"),
        )

    def upload_image(self, image_bytes: bytes, path: str, content_type: str) -> str:
        """
        Upload image bytes to Supabase storage.

        Args:
            image_bytes: The raw image data
            path: Destination path in the bucket (e.g., "posters/12345.jpg")
            content_type: MIME type (e.g., "image/jpeg")

        Returns:
            Public URL of the uploaded image

        Raises:
            SupabaseStorageError: If upload fails
        """
        try:
            self._client.put_object(
                Bucket=self.bucket_name,
                Key=path,
                Body=image_bytes,
                ContentType=content_type,
            )
            return self._get_public_url(path)
        except ClientError as e:
            raise SupabaseStorageError(f"Failed to upload image to {path}: {e}") from e

    def download_and_upload_from_url(self, source_url: str, dest_path: str) -> str:
        """
        Download an image from a URL and upload it to Supabase storage.

        Args:
            source_url: URL to download the image from (e.g., TMDB image URL)
            dest_path: Destination path in the bucket

        Returns:
            Public URL of the uploaded image

        Raises:
            SupabaseStorageError: If download or upload fails
        """
        try:
            response = requests.get(source_url, timeout=30)
            response.raise_for_status()
        except requests.RequestException as e:
            raise SupabaseStorageError(f"Failed to download image from {source_url}: {e}") from e

        content_type = response.headers.get("Content-Type", "image/jpeg")
        return self.upload_image(response.content, dest_path, content_type)

    def image_exists(self, path: str) -> bool:
        """Check if an image already exists in storage."""
        try:
            self._client.head_object(Bucket=self.bucket_name, Key=path)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise SupabaseStorageError(f"Failed to check if image exists at {path}: {e}") from e

    def delete_image(self, path: str) -> None:
        """Delete an image from storage."""
        try:
            self._client.delete_object(Bucket=self.bucket_name, Key=path)
        except ClientError as e:
            raise SupabaseStorageError(f"Failed to delete image at {path}: {e}") from e

    def _get_public_url(self, path: str) -> str:
        """Construct the public URL for an uploaded image."""
        # The bucket_url uses the S3 endpoint (/storage/v1/s3) but public URLs
        # need the object endpoint (/storage/v1/object/public)
        public_url = self.bucket_url.replace("/storage/v1/s3", "/storage/v1/object/public")
        return f"{public_url}/{self.bucket_name}/{path}"

    def get_existing_url(self, path: str) -> str | None:
        """
        Get public URL if image exists, None otherwise.

        Useful for checking if we already have an image before downloading.
        """
        if self.image_exists(path):
            return self._get_public_url(path)
        return None
