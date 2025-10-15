"""
Tests for S3ProviderConfig business logic

This file tests the business logic methods in S3ProviderConfig class
"""

from borgitory.services.cloud_providers.storage.s3_provider_config import (
    S3ProviderConfig,
)
from borgitory.services.cloud_providers.storage.s3_storage import S3Provider


class TestS3ProviderConfigStorageClasses:
    """Test storage class related methods"""

    def test_get_storage_classes_aws(self) -> None:
        """Test getting storage classes for AWS"""
        classes = S3ProviderConfig.get_storage_classes(S3Provider.AWS)

        assert isinstance(classes, list)
        assert len(classes) > 0
        assert "STANDARD" in classes
        assert "GLACIER" in classes
        assert "DEEP_ARCHIVE" in classes

    def test_get_storage_classes_cloudflare(self) -> None:
        """Test getting storage classes for Cloudflare"""
        classes = S3ProviderConfig.get_storage_classes(S3Provider.CLOUDFLARE)

        assert isinstance(classes, list)
        assert classes == ["STANDARD"]

    def test_get_storage_classes_digitalocean(self) -> None:
        """Test getting storage classes for DigitalOcean"""
        classes = S3ProviderConfig.get_storage_classes(S3Provider.DIGITALOCEAN)

        assert isinstance(classes, list)
        assert classes == ["STANDARD"]

    def test_get_storage_classes_wasabi(self) -> None:
        """Test getting storage classes for Wasabi"""
        classes = S3ProviderConfig.get_storage_classes(S3Provider.WASABI)

        assert isinstance(classes, list)
        assert classes == ["STANDARD"]

    def test_get_storage_classes_minio(self) -> None:
        """Test getting storage classes for MinIO"""
        classes = S3ProviderConfig.get_storage_classes(S3Provider.MINIO)

        assert isinstance(classes, list)
        assert "STANDARD" in classes
        assert "REDUCED_REDUNDANCY" in classes

    def test_get_storage_classes_gcs(self) -> None:
        """Test getting storage classes for Google Cloud Storage"""
        classes = S3ProviderConfig.get_storage_classes(S3Provider.GCS)

        assert isinstance(classes, list)
        assert "STANDARD" in classes
        assert "NEARLINE" in classes
        assert "COLDLINE" in classes
        assert "ARCHIVE" in classes

    def test_get_storage_classes_unknown_provider(self) -> None:
        """Test getting storage classes for unknown provider returns default"""
        classes = S3ProviderConfig.get_storage_classes(S3Provider.BACKBLAZE)

        assert isinstance(classes, list)
        assert len(classes) > 0

    def test_get_default_storage_class_aws(self) -> None:
        """Test getting default storage class for AWS"""
        default = S3ProviderConfig.get_default_storage_class(S3Provider.AWS)

        assert default == "STANDARD"

    def test_get_default_storage_class_cloudflare(self) -> None:
        """Test getting default storage class for Cloudflare"""
        default = S3ProviderConfig.get_default_storage_class(S3Provider.CLOUDFLARE)

        assert default == "STANDARD"

    def test_all_providers_have_default_storage_class(self) -> None:
        """Test providers with storage classes have a default storage class"""
        for provider in S3Provider:
            default = S3ProviderConfig.get_default_storage_class(provider)
            assert isinstance(default, str)

            storage_classes = S3ProviderConfig.get_storage_classes(provider)
            if provider in S3ProviderConfig.DEFAULT_STORAGE_CLASS:
                assert len(default) > 0
                assert default in storage_classes


class TestS3ProviderConfigRegions:
    """Test region related methods"""

    def test_get_regions_aws(self) -> None:
        """Test getting regions for AWS"""
        regions = S3ProviderConfig.get_regions(S3Provider.AWS)

        assert isinstance(regions, list)
        assert len(regions) > 0
        assert "us-east-1" in regions
        assert "us-west-2" in regions
        assert "eu-west-1" in regions

    def test_get_regions_cloudflare(self) -> None:
        """Test getting regions for Cloudflare"""
        regions = S3ProviderConfig.get_regions(S3Provider.CLOUDFLARE)

        assert isinstance(regions, list)
        assert regions == ["auto"]

    def test_get_regions_digitalocean(self) -> None:
        """Test getting regions for DigitalOcean"""
        regions = S3ProviderConfig.get_regions(S3Provider.DIGITALOCEAN)

        assert isinstance(regions, list)
        assert len(regions) > 0
        assert "nyc3" in regions
        assert "sfo3" in regions

    def test_get_regions_wasabi(self) -> None:
        """Test getting regions for Wasabi"""
        regions = S3ProviderConfig.get_regions(S3Provider.WASABI)

        assert isinstance(regions, list)
        assert len(regions) > 0
        assert "us-east-1" in regions

    def test_get_regions_storj(self) -> None:
        """Test getting regions for Storj"""
        regions = S3ProviderConfig.get_regions(S3Provider.STORJ)

        assert isinstance(regions, list)
        assert regions == ["global"]

    def test_get_regions_provider_without_regions(self) -> None:
        """Test getting regions for provider that doesn't define regions"""
        regions = S3ProviderConfig.get_regions(S3Provider.MINIO)

        assert isinstance(regions, list)
        assert len(regions) == 0

    def test_get_default_region_aws(self) -> None:
        """Test getting default region for AWS"""
        default = S3ProviderConfig.get_default_region(S3Provider.AWS)

        assert default == "us-east-1"

    def test_get_default_region_cloudflare(self) -> None:
        """Test getting default region for Cloudflare"""
        default = S3ProviderConfig.get_default_region(S3Provider.CLOUDFLARE)

        assert default == "auto"

    def test_get_default_region_digitalocean(self) -> None:
        """Test getting default region for DigitalOcean"""
        default = S3ProviderConfig.get_default_region(S3Provider.DIGITALOCEAN)

        assert default == "nyc3"

    def test_get_default_region_unknown_provider(self) -> None:
        """Test getting default region for unknown provider returns fallback"""
        default = S3ProviderConfig.get_default_region(S3Provider.MINIO)

        assert default == "us-east-1"


class TestS3ProviderConfigEndpoint:
    """Test endpoint requirement methods"""

    def test_requires_endpoint_minio(self) -> None:
        """Test MinIO requires custom endpoint"""
        requires = S3ProviderConfig.requires_endpoint(S3Provider.MINIO)

        assert requires is True

    def test_requires_endpoint_ceph(self) -> None:
        """Test Ceph requires custom endpoint"""
        requires = S3ProviderConfig.requires_endpoint(S3Provider.CEPH)

        assert requires is True

    def test_requires_endpoint_seaweedfs(self) -> None:
        """Test SeaweedFS requires custom endpoint"""
        requires = S3ProviderConfig.requires_endpoint(S3Provider.SEAWEEDFS)

        assert requires is True

    def test_requires_endpoint_rclone(self) -> None:
        """Test Rclone requires custom endpoint"""
        requires = S3ProviderConfig.requires_endpoint(S3Provider.RCLONE)

        assert requires is True

    def test_requires_endpoint_other(self) -> None:
        """Test Other provider requires custom endpoint"""
        requires = S3ProviderConfig.requires_endpoint(S3Provider.OTHER)

        assert requires is True

    def test_requires_endpoint_aws(self) -> None:
        """Test AWS does not require custom endpoint"""
        requires = S3ProviderConfig.requires_endpoint(S3Provider.AWS)

        assert requires is False

    def test_requires_endpoint_cloudflare(self) -> None:
        """Test Cloudflare does not require custom endpoint"""
        requires = S3ProviderConfig.requires_endpoint(S3Provider.CLOUDFLARE)

        assert requires is False

    def test_requires_endpoint_digitalocean(self) -> None:
        """Test DigitalOcean does not require custom endpoint"""
        requires = S3ProviderConfig.requires_endpoint(S3Provider.DIGITALOCEAN)

        assert requires is False


class TestS3ProviderConfigLabels:
    """Test provider label methods"""

    def test_get_provider_label_aws(self) -> None:
        """Test getting label for AWS"""
        label = S3ProviderConfig.get_provider_label(S3Provider.AWS)

        assert label == "Amazon Web Services (AWS) S3"

    def test_get_provider_label_cloudflare(self) -> None:
        """Test getting label for Cloudflare"""
        label = S3ProviderConfig.get_provider_label(S3Provider.CLOUDFLARE)

        assert label == "Cloudflare R2 Storage"

    def test_get_provider_label_digitalocean(self) -> None:
        """Test getting label for DigitalOcean"""
        label = S3ProviderConfig.get_provider_label(S3Provider.DIGITALOCEAN)

        assert label == "DigitalOcean Spaces"

    def test_get_provider_label_minio(self) -> None:
        """Test getting label for MinIO"""
        label = S3ProviderConfig.get_provider_label(S3Provider.MINIO)

        assert label == "Minio Object Storage"

    def test_get_provider_label_backblaze(self) -> None:
        """Test getting label for Backblaze"""
        label = S3ProviderConfig.get_provider_label(S3Provider.BACKBLAZE)

        assert label == "Backblaze B2"

    def test_get_provider_label_storj(self) -> None:
        """Test getting label for Storj"""
        label = S3ProviderConfig.get_provider_label(S3Provider.STORJ)

        assert label == "Storj (S3 Compatible Gateway)"

    def test_get_provider_label_other(self) -> None:
        """Test getting label for Other"""
        label = S3ProviderConfig.get_provider_label(S3Provider.OTHER)

        assert label == "Any other S3 compatible provider"

    def test_all_providers_have_labels(self) -> None:
        """Test all providers have labels defined"""
        for provider in S3Provider:
            label = S3ProviderConfig.get_provider_label(provider)
            assert label is not None
            assert isinstance(label, str)
            assert len(label) > 0


class TestS3ProviderConfigIntegrity:
    """Test integrity and consistency of configuration"""

    def test_all_providers_with_regions_have_default(self) -> None:
        """Test all providers with regions have a default region"""
        for provider in S3Provider:
            regions = S3ProviderConfig.get_regions(provider)
            if len(regions) > 0:
                default = S3ProviderConfig.get_default_region(provider)
                assert default in regions, (
                    f"{provider.value} default region not in regions list"
                )

    def test_all_providers_have_at_least_standard_storage_class(self) -> None:
        """Test all providers support at least STANDARD storage class"""
        for provider in S3Provider:
            classes = S3ProviderConfig.get_storage_classes(provider)
            assert "STANDARD" in classes, (
                f"{provider.value} missing STANDARD storage class"
            )

    def test_storage_classes_are_uppercase(self) -> None:
        """Test all storage classes are uppercase"""
        for provider in S3Provider:
            classes = S3ProviderConfig.get_storage_classes(provider)
            for storage_class in classes:
                assert storage_class == storage_class.upper(), (
                    f"Storage class {storage_class} not uppercase"
                )

    def test_regions_are_valid_strings(self) -> None:
        """Test all regions are valid non-empty strings"""
        for provider in S3Provider:
            regions = S3ProviderConfig.get_regions(provider)
            for region in regions:
                assert isinstance(region, str)
                assert len(region) > 0
                assert region == region.strip()
