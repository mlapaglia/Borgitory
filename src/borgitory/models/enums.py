from enum import StrEnum
from typing import List


class JobType(StrEnum):
    """Job type enumeration with display-friendly names"""

    MANUAL_BACKUP = "Manual Backup"
    SCHEDULED_BACKUP = "Scheduled Backup"
    PRUNE = "Prune"
    CHECK = "Check"
    BACKUP = "Backup"
    LIST = "List"
    VERIFY = "Verify"
    UNKNOWN = "Unknown"

    @classmethod
    def from_command(cls, command: List[str]) -> "JobType":
        """Infer job type from borg command"""
        if not command or len(command) < 2:
            return cls.UNKNOWN

        if "create" in command:
            return cls.BACKUP
        elif "list" in command:
            return cls.LIST
        elif "check" in command:
            return cls.VERIFY
        elif "prune" in command:
            return cls.PRUNE
        else:
            return cls.UNKNOWN

    @classmethod
    def from_job_type_string(cls, job_type: str) -> "JobType":
        """Convert internal job type strings to enum values"""
        type_mapping = {
            "manual_backup": cls.MANUAL_BACKUP,
            "scheduled_backup": cls.SCHEDULED_BACKUP,
            "prune": cls.PRUNE,
            "check": cls.CHECK,
            "backup": cls.BACKUP,
            "list": cls.LIST,
            "verify": cls.VERIFY,
            "unknown": cls.UNKNOWN,
        }
        return type_mapping.get(job_type.lower(), cls.UNKNOWN)
