import boto3
from botocore.exceptions import ClientError
from botocore.config import Config
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
import mimetypes

from ..core.config import settings


class S3Service:
    def __init__(self):
        self._client = None

    @property
    def client(self):
        """Lazy initialization of S3 client"""
        if self._client is None:
            self._client = boto3.client(
                "s3",
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_REGION,
                config=Config(signature_version="s3v4"),
            )
        return self._client

    def generate_file_key(self, folder: str, filename: str, user_id: str) -> str:
        """
        Generate a unique S3 key for the file
        Format: folder/user_id/year/month/uuid_filename
        """
        now = datetime.utcnow()
        file_ext = filename.split(".")[-1] if "." in filename else ""
        unique_id = str(uuid.uuid4())[:8]
        safe_filename = f"{unique_id}_{filename}" if file_ext else f"{unique_id}.jpg"

        return f"{folder}/{user_id}/{now.year}/{now.month:02d}/{safe_filename}"

    def get_presigned_upload_url(
        self,
        file_key: str,
        content_type: str,
        expiry: int = None,
    ) -> Dict[str, Any]:
        """
        Generate a presigned URL for uploading a file directly to S3

        Args:
            file_key: The S3 object key
            content_type: MIME type of the file
            expiry: URL expiration time in seconds (default from settings)

        Returns:
            Dict with upload_url, file_key, file_url, and expires_in
        """
        if expiry is None:
            expiry = settings.S3_PRESIGNED_URL_EXPIRY

        try:
            # Generate presigned PUT URL
            upload_url = self.client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": settings.S3_BUCKET_NAME,
                    "Key": file_key,
                    "ContentType": content_type,
                },
                ExpiresIn=expiry,
                HttpMethod="PUT",
            )

            # Generate the final file URL (using CDN if configured)
            file_url = f"{settings.s3_base_url}/{file_key}"

            return {
                "upload_url": upload_url,
                "file_key": file_key,
                "file_url": file_url,
                "expires_in": expiry,
            }

        except ClientError as e:
            raise Exception(f"Failed to generate presigned URL: {str(e)}")

    def get_presigned_download_url(
        self,
        file_key: str,
        expiry: int = 3600,
        filename: Optional[str] = None,
    ) -> str:
        """
        Generate a presigned URL for downloading a file from S3

        Args:
            file_key: The S3 object key
            expiry: URL expiration time in seconds
            filename: Optional filename for Content-Disposition header

        Returns:
            Presigned download URL
        """
        try:
            params = {
                "Bucket": settings.S3_BUCKET_NAME,
                "Key": file_key,
            }

            if filename:
                params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'

            return self.client.generate_presigned_url(
                "get_object",
                Params=params,
                ExpiresIn=expiry,
            )

        except ClientError as e:
            raise Exception(f"Failed to generate download URL: {str(e)}")

    def delete_file(self, file_key: str) -> bool:
        """
        Delete a file from S3

        Args:
            file_key: The S3 object key

        Returns:
            True if successful
        """
        try:
            self.client.delete_object(
                Bucket=settings.S3_BUCKET_NAME,
                Key=file_key,
            )
            return True

        except ClientError as e:
            raise Exception(f"Failed to delete file: {str(e)}")

    def file_exists(self, file_key: str) -> bool:
        """
        Check if a file exists in S3

        Args:
            file_key: The S3 object key

        Returns:
            True if file exists
        """
        try:
            self.client.head_object(
                Bucket=settings.S3_BUCKET_NAME,
                Key=file_key,
            )
            return True

        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise Exception(f"Failed to check file: {str(e)}")

    def get_file_metadata(self, file_key: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a file in S3

        Args:
            file_key: The S3 object key

        Returns:
            Dict with file metadata or None if not found
        """
        try:
            response = self.client.head_object(
                Bucket=settings.S3_BUCKET_NAME,
                Key=file_key,
            )

            return {
                "content_type": response.get("ContentType"),
                "content_length": response.get("ContentLength"),
                "last_modified": response.get("LastModified"),
                "etag": response.get("ETag"),
            }

        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return None
            raise Exception(f"Failed to get file metadata: {str(e)}")

    def copy_file(self, source_key: str, destination_key: str) -> bool:
        """
        Copy a file within S3

        Args:
            source_key: Source S3 object key
            destination_key: Destination S3 object key

        Returns:
            True if successful
        """
        try:
            self.client.copy_object(
                Bucket=settings.S3_BUCKET_NAME,
                CopySource={"Bucket": settings.S3_BUCKET_NAME, "Key": source_key},
                Key=destination_key,
            )
            return True

        except ClientError as e:
            raise Exception(f"Failed to copy file: {str(e)}")

    @staticmethod
    def get_content_type(filename: str) -> str:
        """Get MIME type from filename"""
        content_type, _ = mimetypes.guess_type(filename)
        return content_type or "application/octet-stream"

    @staticmethod
    def validate_file_type(content_type: str, allowed_types: list) -> bool:
        """Validate if content type is allowed"""
        # Check exact match or prefix match (e.g., "image/" matches "image/jpeg")
        for allowed in allowed_types:
            if content_type == allowed or content_type.startswith(allowed.rstrip("*")):
                return True
        return False


# Singleton instance
s3_service = S3Service()
