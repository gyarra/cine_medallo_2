import pytest
from unittest.mock import MagicMock, patch

from movies_app.services.supabase_storage_service import (
    SupabaseStorageService,
    SupabaseStorageError,
)


class TestSupabaseStorageService:
    @pytest.fixture
    def mock_boto3_client(self):
        with patch("movies_app.services.supabase_storage_service.boto3.client") as mock_client:
            yield mock_client.return_value

    @pytest.fixture
    def storage_service(self, mock_boto3_client):
        return SupabaseStorageService(
            bucket_url="https://example.supabase.co/storage/v1/s3",
            access_key_id="test-access-key",
            secret_access_key="test-secret-key",
            bucket_name="movie-images",
        )

    def test_upload_image_returns_public_url(self, storage_service, mock_boto3_client):
        image_bytes = b"fake image data"
        path = "posters/12345.jpg"

        result = storage_service.upload_image(image_bytes, path, "image/jpeg")

        mock_boto3_client.put_object.assert_called_once_with(
            Bucket="movie-images",
            Key=path,
            Body=image_bytes,
            ContentType="image/jpeg",
        )
        assert result == "https://example.supabase.co/storage/v1/s3/movie-images/posters/12345.jpg"

    def test_upload_image_raises_on_client_error(self, storage_service, mock_boto3_client):
        from botocore.exceptions import ClientError

        mock_boto3_client.put_object.side_effect = ClientError(
            {"Error": {"Code": "500", "Message": "Internal error"}},
            "PutObject",
        )

        with pytest.raises(SupabaseStorageError) as exc_info:
            storage_service.upload_image(b"data", "test.jpg", "image/jpeg")

        assert "Failed to upload image" in str(exc_info.value)

    def test_image_exists_returns_true_when_exists(self, storage_service, mock_boto3_client):
        mock_boto3_client.head_object.return_value = {"ContentLength": 1234}

        result = storage_service.image_exists("posters/12345.jpg")

        assert result is True
        mock_boto3_client.head_object.assert_called_once_with(
            Bucket="movie-images",
            Key="posters/12345.jpg",
        )

    def test_image_exists_returns_false_when_not_found(self, storage_service, mock_boto3_client):
        from botocore.exceptions import ClientError

        mock_boto3_client.head_object.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not found"}},
            "HeadObject",
        )

        result = storage_service.image_exists("posters/nonexistent.jpg")

        assert result is False

    def test_get_existing_url_returns_url_when_exists(self, storage_service, mock_boto3_client):
        mock_boto3_client.head_object.return_value = {"ContentLength": 1234}

        result = storage_service.get_existing_url("posters/12345.jpg")

        assert result == "https://example.supabase.co/storage/v1/s3/movie-images/posters/12345.jpg"

    def test_get_existing_url_returns_none_when_not_exists(self, storage_service, mock_boto3_client):
        from botocore.exceptions import ClientError

        mock_boto3_client.head_object.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not found"}},
            "HeadObject",
        )

        result = storage_service.get_existing_url("posters/nonexistent.jpg")

        assert result is None

    def test_download_and_upload_from_url_success(self, storage_service, mock_boto3_client):
        with patch("movies_app.services.supabase_storage_service.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = b"downloaded image data"
            mock_response.headers = {"Content-Type": "image/jpeg"}
            mock_get.return_value = mock_response

            result = storage_service.download_and_upload_from_url(
                "https://image.tmdb.org/t/p/original/abc.jpg",
                "posters/12345.jpg",
            )

            mock_get.assert_called_once_with(
                "https://image.tmdb.org/t/p/original/abc.jpg",
                timeout=30,
            )
            mock_boto3_client.put_object.assert_called_once()
            assert "movie-images/posters/12345.jpg" in result

    def test_download_and_upload_raises_on_download_error(self, storage_service, mock_boto3_client):
        import requests

        with patch("movies_app.services.supabase_storage_service.requests.get") as mock_get:
            mock_get.side_effect = requests.RequestException("Connection failed")

            with pytest.raises(SupabaseStorageError) as exc_info:
                storage_service.download_and_upload_from_url(
                    "https://example.com/image.jpg",
                    "test.jpg",
                )

            assert "Failed to download image" in str(exc_info.value)

    def test_delete_image_success(self, storage_service, mock_boto3_client):
        storage_service.delete_image("posters/12345.jpg")

        mock_boto3_client.delete_object.assert_called_once_with(
            Bucket="movie-images",
            Key="posters/12345.jpg",
        )
