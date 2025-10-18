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
        S3Provider.FILELU: [
            "global",
            "us-east",
            "eu-central",
            "ap-southeast",
            "me-central",
        ],
        S3Provider.HETZNER: ["hel1", "fsn1", "nbg1"],
        S3Provider.HUAWEI_OBS: [
            "af-south-1",
            "ap-southeast-2",
            "ap-southeast-3",
            "cn-east-3",
            "cn-east-2",
            "cn-north-1",
            "cn-north-4",
            "cn-south-1",
            "ap-southeast-1",
            "sa-argentina-1",
            "sa-peru-1",
            "na-mexico-1",
            "sa-chile-1",
            "sa-brazil-1",
            "ru-northwest-2",
        ],
        S3Provider.QINIU: [
            "cn-east-1",
            "cn-east-2",
            "cn-north-1",
            "cn-south-1",
            "us-north-1",
            "ap-southeast-1",
            "ap-northeast-1",
        ],
        S3Provider.OVH_CLOUD: [
            "gra",
            "rbx",
            "sbg",
            "eu-west-par",
            "de",
            "uk",
            "waw",
            "bhs",
            "ca-east-tor",
            "sgp",
            "ap-southeast-syd",
            "ap-south-mum",
            "us-east-va",
            "us-west-or",
            "rbx-archive",
        ],
        S3Provider.SCALEWAY: [
            "nl-ams",
            "fr-par",
            "pl-waw",
        ],
        S3Provider.SELECTEL: ["ru-1"],
        S3Provider.SYNOLOGY: ["eu-001", "eu-002", "us-001", "us-002", "tw-001"],
        S3Provider.ZATA: ["us-east-1"],
        # Providers without specific regions in rclone (empty list means text field)
        S3Provider.ALIBABA: [],
        S3Provider.ARVAN_CLOUD: [],
        S3Provider.BACKBLAZE: [],
        S3Provider.CEPH: [],
        S3Provider.CHINA_MOBILE: [],
        S3Provider.DIGITALOCEAN: [],
        S3Provider.DREAMHOST: [],
        S3Provider.EXABA: [],
        S3Provider.FLASHBLADE: [],
        S3Provider.GCS: [],
        S3Provider.IBM_COS: [],
        S3Provider.IDRIVE: [],
        S3Provider.IONOS: [],
        S3Provider.LEVIIA: [],
        S3Provider.LIARA: [],
        S3Provider.LINODE: [],
        S3Provider.LYVE_CLOUD: [],
        S3Provider.MAGALU: [],
        S3Provider.MEGA: [],
        S3Provider.MINIO: [],
        S3Provider.NETEASE: [],
        S3Provider.OTHER: [],
        S3Provider.OUTSCALE: [],
        S3Provider.PETABOX: [],
        S3Provider.RABATA: [],
        S3Provider.RACKCORP: [],
        S3Provider.RCLONE: [],
        S3Provider.SEAWEEDFS: [],
        S3Provider.SPECTRA_LOGIC: [],
        S3Provider.STACKPATH: [],
        S3Provider.STORJ: [],
        S3Provider.TENCENT_COS: [],
        S3Provider.WASABI: [],
    }

    DEFAULT_REGION: Dict[S3Provider, str] = {
        S3Provider.AWS: "us-east-1",
        S3Provider.CLOUDFLARE: "auto",
        S3Provider.FILELU: "global",
        S3Provider.HETZNER: "hel1",
        S3Provider.HUAWEI_OBS: "af-south-1",
        S3Provider.QINIU: "cn-east-1",
        S3Provider.OVH_CLOUD: "gra",
        S3Provider.SCALEWAY: "nl-ams",
        S3Provider.SELECTEL: "ru-1",
        S3Provider.SYNOLOGY: "eu-001",
        S3Provider.ZATA: "us-east-1",
        # Providers without specific regions in rclone use empty string
        S3Provider.ALIBABA: "",
        S3Provider.ARVAN_CLOUD: "",
        S3Provider.BACKBLAZE: "",
        S3Provider.CEPH: "",
        S3Provider.CHINA_MOBILE: "",
        S3Provider.DIGITALOCEAN: "",
        S3Provider.DREAMHOST: "",
        S3Provider.EXABA: "",
        S3Provider.FLASHBLADE: "",
        S3Provider.GCS: "",
        S3Provider.IBM_COS: "",
        S3Provider.IDRIVE: "",
        S3Provider.IONOS: "",
        S3Provider.LEVIIA: "",
        S3Provider.LIARA: "",
        S3Provider.LINODE: "",
        S3Provider.LYVE_CLOUD: "",
        S3Provider.MAGALU: "",
        S3Provider.MEGA: "",
        S3Provider.MINIO: "",
        S3Provider.NETEASE: "",
        S3Provider.OTHER: "",
        S3Provider.OUTSCALE: "",
        S3Provider.PETABOX: "",
        S3Provider.RABATA: "",
        S3Provider.RACKCORP: "",
        S3Provider.RCLONE: "",
        S3Provider.SEAWEEDFS: "",
        S3Provider.SPECTRA_LOGIC: "",
        S3Provider.STACKPATH: "",
        S3Provider.STORJ: "",
        S3Provider.TENCENT_COS: "",
        S3Provider.WASABI: "",
    }

    # Endpoint configurations - matching rclone's endpoint examples
    ENDPOINT_DEFAULTS: Dict[S3Provider, str] = {
        S3Provider.ALIBABA: "",  # Uses region-based endpoints like oss-cn-hangzhou.aliyuncs.com
        S3Provider.ARVAN_CLOUD: "",  # s3.ir-thr-at1.arvanstorage.ir, etc.
        S3Provider.BACKBLAZE: "",  # s3.us-west-001.backblazeb2.com, etc.
        S3Provider.CHINA_MOBILE: "",  # eos-wuxi-1.cmecloud.cn, etc.
        S3Provider.CLOUDFLARE: "",  # https://<accountid>.r2.cloudflarestorage.com
        S3Provider.DIGITALOCEAN: "",  # https://nyc3.digitaloceanspaces.com, etc.
        S3Provider.DREAMHOST: "",  # objects-us-east-1.dream.io
        S3Provider.FILELU: "s5lu.com",  # Immutable endpoint
        S3Provider.GCS: "https://storage.googleapis.com",  # Immutable endpoint
        S3Provider.HETZNER: "",  # hel1.your-objectstorage.com, etc.
        S3Provider.HUAWEI_OBS: "",  # obs.af-south-1.myhuaweicloud.com, etc.
        S3Provider.IBM_COS: "",  # s3.us.cloud-object-storage.appdomain.cloud, etc.
        S3Provider.IDRIVE: "",  # s3.us-east-1.idrivee2-*.com
        S3Provider.INTERCOLO: "de-fra.i3storage.com",  # Immutable endpoint
        S3Provider.IONOS: "",  # s3-eu-central-1.ionoscloud.com, etc.
        S3Provider.LEVIIA: "s3.leviia.com",  # Immutable endpoint
        S3Provider.LIARA: "",  # storage.iran.liara.space
        S3Provider.LINODE: "",  # nl-ams-1.linodeobjects.com, etc.
        S3Provider.LYVE_CLOUD: "",  # s3.us-west-1.{account_name}.lyve.seagate.com
        S3Provider.MAGALU: "",  # br-se1.magaluobjects.com, etc.
        S3Provider.MEGA: "",  # s3.eu-central-1.s4.mega.io, etc.
        S3Provider.NETEASE: "",  # Uses region-based
        S3Provider.OUTSCALE: "",  # oos.eu-west-2.outscale.com, etc.
        S3Provider.OVH_CLOUD: "",  # s3.gra.io.cloud.ovh.net, etc.
        S3Provider.PETABOX: "s3.petabox.io",  # Immutable endpoint
        S3Provider.QINIU: "",  # s3-cn-east-1.qiniucs.com, etc.
        S3Provider.RABATA: "",  # s3.us-east-1.rabata.io, etc.
        S3Provider.RACKCORP: "",  # s3.rackcorp.com, etc.
        S3Provider.SCALEWAY: "",  # s3.nl-ams.scw.cloud, etc.
        S3Provider.SELECTEL: "s3.ru-1.storage.selcloud.ru",  # Immutable endpoint
        S3Provider.SPECTRA_LOGIC: "",  # Custom
        S3Provider.STACKPATH: "",  # s3.us-east-2.stackpathstorage.com, etc.
        S3Provider.STORJ: "gateway.storjshare.io",  # Immutable endpoint
        S3Provider.SYNOLOGY: "",  # eu-001.s3.synologyc2.net, etc.
        S3Provider.TENCENT_COS: "",  # cos.ap-beijing.myqcloud.com, etc.
        S3Provider.WASABI: "",  # s3.wasabisys.com, etc.
        S3Provider.ZATA: "idr01.zata.ai",  # Immutable endpoint
        S3Provider.EXABA: "",  # Custom
        S3Provider.FLASHBLADE: "",  # Custom
        # Providers without endpoints
        S3Provider.AWS: "",  # Uses default AWS endpoints
        S3Provider.CEPH: "",
        S3Provider.MINIO: "",
        S3Provider.SEAWEEDFS: "",
        S3Provider.RCLONE: "",
        S3Provider.OTHER: "",
    }

    IMMUTABLE_ENDPOINTS: List[S3Provider] = [
        S3Provider.GCS,  # https://storage.googleapis.com
        S3Provider.STORJ,  # gateway.storjshare.io
        S3Provider.FILELU,  # s5lu.com
        S3Provider.INTERCOLO,  # de-fra.i3storage.com
        S3Provider.LEVIIA,  # s3.leviia.com
        S3Provider.PETABOX,  # s3.petabox.io
        S3Provider.SELECTEL,  # s3.ru-1.storage.selcloud.ru
        S3Provider.ZATA,  # idr01.zata.ai
    ]

    REQUIRES_ENDPOINT: List[S3Provider] = [
        S3Provider.CEPH,  # Custom endpoint required
        S3Provider.MINIO,  # Custom endpoint required
        S3Provider.SEAWEEDFS,  # Custom endpoint required
        S3Provider.RCLONE,  # Custom endpoint required
        S3Provider.OTHER,  # Custom endpoint required
        S3Provider.LYVE_CLOUD,  # Required when using S3 clone
        S3Provider.IDRIVE,  # Required when using IBM COS On Premise
        S3Provider.IBM_COS,  # Specify if using IBM COS On Premise
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
    def get_default_endpoint(cls, provider: S3Provider) -> str:
        """Get default endpoint for a provider"""
        return cls.ENDPOINT_DEFAULTS.get(provider, "")

    @classmethod
    def has_immutable_endpoint(cls, provider: S3Provider) -> bool:
        """Check if provider has an immutable endpoint"""
        return provider in cls.IMMUTABLE_ENDPOINTS

    @classmethod
    def get_provider_label(cls, provider: S3Provider) -> str:
        """Get display label for a provider"""
        return cls.PROVIDER_LABELS.get(provider, provider.value)
