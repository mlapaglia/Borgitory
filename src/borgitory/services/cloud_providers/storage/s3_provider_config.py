"""
S3 Provider-specific configurations including storage classes and regions.

This module defines supported storage classes and regions for each S3-compatible provider.
"""

from typing import Dict, List
from .s3_storage import S3Provider


class S3ProviderConfig:
    """Configuration mappings for S3-compatible providers"""

    STORAGE_CLASSES: Dict[S3Provider, List[str]] = {
        S3Provider.AWS: [
            "STANDARD",
            "REDUCED_REDUNDANCY",
            "STANDARD_IA",
            "ONEZONE_IA",
            "INTELLIGENT_TIERING",
            "GLACIER",
            "DEEP_ARCHIVE",
            "GLACIER_IR",
        ],
        S3Provider.CLOUDFLARE: ["STANDARD"],
        S3Provider.DIGITALOCEAN: ["STANDARD"],
        S3Provider.WASABI: ["STANDARD"],
        S3Provider.STORJ: ["STANDARD"],
        S3Provider.BACKBLAZE: ["STANDARD"],
        S3Provider.MINIO: ["STANDARD", "REDUCED_REDUNDANCY"],
        S3Provider.GCS: ["STANDARD", "NEARLINE", "COLDLINE", "ARCHIVE"],
        S3Provider.IBM_COS: ["STANDARD", "VAULT", "COLD", "FLEX"],
        S3Provider.ALIBABA: ["STANDARD", "IA", "ARCHIVE"],
        S3Provider.TENCENT_COS: ["STANDARD", "STANDARD_IA", "ARCHIVE"],
        S3Provider.HUAWEI_OBS: ["STANDARD", "WARM", "COLD"],
    }

    DEFAULT_STORAGE_CLASS: Dict[S3Provider, str] = {
        S3Provider.AWS: "STANDARD",
        S3Provider.CLOUDFLARE: "STANDARD",
        S3Provider.DIGITALOCEAN: "STANDARD",
        S3Provider.WASABI: "STANDARD",
        S3Provider.STORJ: "STANDARD",
        S3Provider.BACKBLAZE: "STANDARD",
        S3Provider.MINIO: "STANDARD",
        S3Provider.GCS: "STANDARD",
        S3Provider.IBM_COS: "STANDARD",
        S3Provider.ALIBABA: "STANDARD",
        S3Provider.TENCENT_COS: "STANDARD",
        S3Provider.HUAWEI_OBS: "STANDARD",
    }

    AWS_REGIONS = [
        "us-east-1",
        "us-east-2",
        "us-west-1",
        "us-west-2",
        "ca-central-1",
        "eu-west-1",
        "eu-west-2",
        "eu-west-3",
        "eu-central-1",
        "eu-north-1",
        "eu-south-1",
        "ap-east-1",
        "ap-south-1",
        "ap-northeast-1",
        "ap-northeast-2",
        "ap-northeast-3",
        "ap-southeast-1",
        "ap-southeast-2",
        "sa-east-1",
        "me-south-1",
        "af-south-1",
    ]

    REGIONS: Dict[S3Provider, List[str]] = {
        S3Provider.AWS: AWS_REGIONS,
        S3Provider.CLOUDFLARE: ["auto"],
        S3Provider.DIGITALOCEAN: [
            "nyc3",
            "ams3",
            "sgp1",
            "sfo2",
            "sfo3",
            "fra1",
            "blr1",
            "syd1",
        ],
        S3Provider.WASABI: [
            "us-east-1",
            "us-east-2",
            "us-west-1",
            "eu-central-1",
            "ap-northeast-1",
            "ap-northeast-2",
        ],
        S3Provider.LINODE: [
            "us-east-1",
            "us-southeast-1",
            "eu-central-1",
            "ap-south-1",
        ],
        S3Provider.SCALEWAY: ["fr-par", "nl-ams", "pl-waw"],
        S3Provider.ALIBABA: [
            "oss-cn-hangzhou",
            "oss-cn-shanghai",
            "oss-cn-beijing",
            "oss-cn-shenzhen",
            "oss-us-west-1",
            "oss-us-east-1",
            "oss-ap-southeast-1",
            "oss-eu-central-1",
        ],
        S3Provider.TENCENT_COS: [
            "ap-beijing",
            "ap-shanghai",
            "ap-guangzhou",
            "ap-chengdu",
            "ap-singapore",
            "na-siliconvalley",
            "na-ashburn",
        ],
        S3Provider.HUAWEI_OBS: [
            "cn-north-1",
            "cn-north-4",
            "cn-south-1",
            "ap-southeast-1",
            "ap-southeast-2",
            "ap-southeast-3",
        ],
        S3Provider.BACKBLAZE: [
            "us-west-001",
            "us-west-002",
            "us-west-004",
            "eu-central-003",
        ],
        S3Provider.STORJ: ["global"],
        S3Provider.IDRIVE: ["us-east-1"],
    }

    DEFAULT_REGION: Dict[S3Provider, str] = {
        S3Provider.AWS: "us-east-1",
        S3Provider.CLOUDFLARE: "auto",
        S3Provider.DIGITALOCEAN: "nyc3",
        S3Provider.WASABI: "us-east-1",
        S3Provider.LINODE: "us-east-1",
        S3Provider.SCALEWAY: "fr-par",
        S3Provider.ALIBABA: "oss-cn-hangzhou",
        S3Provider.TENCENT_COS: "ap-beijing",
        S3Provider.HUAWEI_OBS: "cn-north-1",
        S3Provider.BACKBLAZE: "us-west-001",
        S3Provider.STORJ: "global",
        S3Provider.IDRIVE: "us-east-1",
    }

    REQUIRES_ENDPOINT: List[S3Provider] = [
        S3Provider.CEPH,
        S3Provider.MINIO,
        S3Provider.SEAWEEDFS,
        S3Provider.RCLONE,
        S3Provider.OTHER,
    ]

    PROVIDER_LABELS: Dict[S3Provider, str] = {
        S3Provider.AWS: "Amazon Web Services (AWS) S3",
        S3Provider.ALIBABA: "Alibaba Cloud Object Storage System (OSS)",
        S3Provider.ARVAN_CLOUD: "Arvan Cloud Object Storage (AOS)",
        S3Provider.BACKBLAZE: "Backblaze B2",
        S3Provider.CEPH: "Ceph Object Storage",
        S3Provider.CHINA_MOBILE: "China Mobile Ecloud Elastic Object Storage (EOS)",
        S3Provider.CLOUDFLARE: "Cloudflare R2 Storage",
        S3Provider.DIGITALOCEAN: "DigitalOcean Spaces",
        S3Provider.DREAMHOST: "Dreamhost DreamObjects",
        S3Provider.EXABA: "Exaba Object Storage",
        S3Provider.FILELU: "FileLu S5 (S3-Compatible Object Storage)",
        S3Provider.FLASHBLADE: "Pure Storage FlashBlade Object Storage",
        S3Provider.GCS: "Google Cloud Storage",
        S3Provider.HETZNER: "Hetzner Object Storage",
        S3Provider.HUAWEI_OBS: "Huawei Object Storage Service",
        S3Provider.IBM_COS: "IBM COS S3",
        S3Provider.IDRIVE: "IDrive e2",
        S3Provider.INTERCOLO: "Intercolo Object Storage",
        S3Provider.IONOS: "IONOS Cloud",
        S3Provider.LYVE_CLOUD: "Seagate Lyve Cloud",
        S3Provider.LEVIIA: "Leviia Object Storage",
        S3Provider.LIARA: "Liara Object Storage",
        S3Provider.LINODE: "Linode Object Storage",
        S3Provider.MAGALU: "Magalu Object Storage",
        S3Provider.MEGA: "MEGA S4 Object Storage",
        S3Provider.MINIO: "Minio Object Storage",
        S3Provider.NETEASE: "Netease Object Storage (NOS)",
        S3Provider.OUTSCALE: "OUTSCALE Object Storage (OOS)",
        S3Provider.OVH_CLOUD: "OVHcloud Object Storage",
        S3Provider.PETABOX: "Petabox Object Storage",
        S3Provider.RABATA: "Rabata Cloud Storage",
        S3Provider.RACKCORP: "RackCorp Object Storage",
        S3Provider.RCLONE: "Rclone S3 Server",
        S3Provider.SCALEWAY: "Scaleway Object Storage",
        S3Provider.SEAWEEDFS: "SeaweedFS S3",
        S3Provider.SELECTEL: "Selectel Object Storage",
        S3Provider.SPECTRA_LOGIC: "Spectra Logic Black Pearl",
        S3Provider.STACKPATH: "StackPath Object Storage",
        S3Provider.STORJ: "Storj (S3 Compatible Gateway)",
        S3Provider.SYNOLOGY: "Synology C2 Object Storage",
        S3Provider.TENCENT_COS: "Tencent Cloud Object Storage (COS)",
        S3Provider.WASABI: "Wasabi Object Storage",
        S3Provider.QINIU: "Qiniu Object Storage (Kodo)",
        S3Provider.ZATA: "Zata (S3 compatible Gateway)",
        S3Provider.OTHER: "Any other S3 compatible provider",
    }

    @classmethod
    def get_storage_classes(cls, provider: S3Provider) -> List[str]:
        """Get supported storage classes for a provider"""
        return cls.STORAGE_CLASSES.get(provider, ["STANDARD"])

    @classmethod
    def get_default_storage_class(cls, provider: S3Provider) -> str:
        """Get default storage class for a provider"""
        return cls.DEFAULT_STORAGE_CLASS.get(provider, "")

    @classmethod
    def get_regions(cls, provider: S3Provider) -> List[str]:
        """Get supported regions for a provider"""
        return cls.REGIONS.get(provider, [])

    @classmethod
    def get_default_region(cls, provider: S3Provider) -> str:
        """Get default region for a provider"""
        return cls.DEFAULT_REGION.get(provider, "us-east-1")

    @classmethod
    def requires_endpoint(cls, provider: S3Provider) -> bool:
        """Check if provider requires custom endpoint"""
        return provider in cls.REQUIRES_ENDPOINT

    @classmethod
    def get_provider_label(cls, provider: S3Provider) -> str:
        """Get display label for a provider"""
        return cls.PROVIDER_LABELS.get(provider, provider.value)
