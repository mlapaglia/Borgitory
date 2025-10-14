"""
Tests for S3 API endpoints - HTMX response format testing only
Business logic tests are in test_s3_provider_config.py
"""

from httpx import AsyncClient


class TestS3APIHTMXResponses:
    """Test class for S3 API HTMX responses"""

    async def test_get_s3_providers_returns_html(
        self, async_client: AsyncClient
    ) -> None:
        """Test getting S3 providers returns HTML"""
        response = await async_client.get("/api/cloud-sync/s3/providers")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert len(response.text) > 0

    async def test_get_s3_providers_with_current_value(
        self, async_client: AsyncClient
    ) -> None:
        """Test getting S3 providers with current_value parameter"""
        response = await async_client.get(
            "/api/cloud-sync/s3/providers?current_value=AWS"
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        content = response.text
        assert "AWS" in content or "selected" in content

    async def test_get_s3_providers_contains_provider_options(
        self, async_client: AsyncClient
    ) -> None:
        """Test S3 providers response contains provider options"""
        response = await async_client.get("/api/cloud-sync/s3/providers")

        assert response.status_code == 200
        content = response.text

        assert "option" in content.lower()
        assert "value" in content.lower()

    async def test_get_s3_regions_returns_html(self, async_client: AsyncClient) -> None:
        """Test getting S3 regions returns HTML"""
        response = await async_client.get(
            "/api/cloud-sync/s3/regions?provider_config[provider_type]=AWS"
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert len(response.text) > 0

    async def test_get_s3_regions_for_aws(self, async_client: AsyncClient) -> None:
        """Test getting AWS regions contains expected regions"""
        response = await async_client.get(
            "/api/cloud-sync/s3/regions?provider_config[provider_type]=AWS"
        )

        assert response.status_code == 200
        content = response.text

        assert "us-east-1" in content

    async def test_get_s3_regions_with_current_value(
        self, async_client: AsyncClient
    ) -> None:
        """Test getting regions with current_value parameter"""
        response = await async_client.get(
            "/api/cloud-sync/s3/regions?provider_config[provider_type]=AWS&current_value=us-west-2"
        )

        assert response.status_code == 200
        content = response.text
        assert "us-west-2" in content

    async def test_get_s3_regions_for_cloudflare(
        self, async_client: AsyncClient
    ) -> None:
        """Test getting Cloudflare regions returns auto region"""
        response = await async_client.get(
            "/api/cloud-sync/s3/regions?provider_config[provider_type]=Cloudflare"
        )

        assert response.status_code == 200
        content = response.text
        assert "auto" in content

    async def test_get_s3_regions_invalid_provider(
        self, async_client: AsyncClient
    ) -> None:
        """Test getting regions with invalid provider returns graceful response"""
        response = await async_client.get(
            "/api/cloud-sync/s3/regions?provider_config[provider_type]=InvalidProvider"
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    async def test_get_s3_storage_classes_returns_html(
        self, async_client: AsyncClient
    ) -> None:
        """Test getting S3 storage classes returns HTML"""
        response = await async_client.get(
            "/api/cloud-sync/s3/storage-classes?provider_config[provider_type]=AWS"
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert len(response.text) > 0

    async def test_get_s3_storage_classes_for_aws(
        self, async_client: AsyncClient
    ) -> None:
        """Test getting AWS storage classes contains expected classes"""
        response = await async_client.get(
            "/api/cloud-sync/s3/storage-classes?provider_config[provider_type]=AWS"
        )

        assert response.status_code == 200
        content = response.text

        assert "STANDARD" in content

    async def test_get_s3_storage_classes_with_current_value(
        self, async_client: AsyncClient
    ) -> None:
        """Test getting storage classes with current_value parameter"""
        response = await async_client.get(
            "/api/cloud-sync/s3/storage-classes?provider_config[provider_type]=AWS&current_value=GLACIER"
        )

        assert response.status_code == 200
        content = response.text
        assert "GLACIER" in content

    async def test_get_s3_storage_classes_for_digitalocean(
        self, async_client: AsyncClient
    ) -> None:
        """Test getting DigitalOcean storage classes returns STANDARD only"""
        response = await async_client.get(
            "/api/cloud-sync/s3/storage-classes?provider_config[provider_type]=DigitalOcean"
        )

        assert response.status_code == 200
        content = response.text
        assert "STANDARD" in content

    async def test_get_s3_storage_classes_invalid_provider(
        self, async_client: AsyncClient
    ) -> None:
        """Test getting storage classes with invalid provider returns graceful response"""
        response = await async_client.get(
            "/api/cloud-sync/s3/storage-classes?provider_config[provider_type]=InvalidProvider"
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    async def test_get_s3_endpoint_field_returns_html(
        self, async_client: AsyncClient
    ) -> None:
        """Test getting S3 endpoint field returns HTML"""
        response = await async_client.get(
            "/api/cloud-sync/s3/endpoint-field?provider_config[provider_type]=Minio"
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    async def test_get_s3_endpoint_field_for_provider_requiring_endpoint(
        self, async_client: AsyncClient
    ) -> None:
        """Test endpoint field for providers that require custom endpoint"""
        providers_requiring_endpoint = ["Minio", "Ceph", "SeaweedFS", "Rclone", "Other"]

        for provider in providers_requiring_endpoint:
            response = await async_client.get(
                f"/api/cloud-sync/s3/endpoint-field?provider_config[provider_type]={provider}"
            )

            assert response.status_code == 200
            content = response.text
            assert len(content) > 0

    async def test_get_s3_endpoint_field_for_provider_not_requiring_endpoint(
        self, async_client: AsyncClient
    ) -> None:
        """Test endpoint field for providers that don't require custom endpoint"""
        response = await async_client.get(
            "/api/cloud-sync/s3/endpoint-field?provider_config[provider_type]=AWS"
        )

        assert response.status_code == 200

    async def test_get_s3_endpoint_field_with_current_value(
        self, async_client: AsyncClient
    ) -> None:
        """Test getting endpoint field with current_value parameter"""
        response = await async_client.get(
            "/api/cloud-sync/s3/endpoint-field?provider_config[provider_type]=Minio&current_value=http://localhost:9000"
        )

        assert response.status_code == 200
        content = response.text
        assert len(content) > 0

    async def test_get_s3_endpoint_field_invalid_provider(
        self, async_client: AsyncClient
    ) -> None:
        """Test getting endpoint field with invalid provider returns graceful response"""
        response = await async_client.get(
            "/api/cloud-sync/s3/endpoint-field?provider_config[provider_type]=InvalidProvider"
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    async def test_all_s3_endpoints_return_html_with_no_params(
        self, async_client: AsyncClient
    ) -> None:
        """Test all S3 endpoints return HTML even with no parameters"""
        endpoints = [
            "/api/cloud-sync/s3/providers",
            "/api/cloud-sync/s3/regions",
            "/api/cloud-sync/s3/storage-classes",
            "/api/cloud-sync/s3/endpoint-field",
        ]

        for endpoint in endpoints:
            response = await async_client.get(endpoint)
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]
