"""Service for generating human-readable descriptions of cron expressions."""

import re
from cron_descriptor import get_description, FormatException


class CronDescriptionService:
    """Service for converting cron expressions to human-readable descriptions."""

    @staticmethod
    def get_human_description(cron_expression: str) -> dict[str, str | None]:
        """
        Convert a cron expression to a human-readable description.

        Args:
            cron_expression: The cron expression to describe

        Returns:
            Dictionary with 'description' and 'error' keys
        """
        if not cron_expression or not cron_expression.strip():
            return {"description": None, "error": None}

        try:
            description = get_description(cron_expression.strip())
            return {"description": description, "error": None}
        except FormatException as e:
            return {"description": None, "error": f"Invalid cron format: {str(e)}"}
        except Exception:
            return {"description": None, "error": "Invalid cron expression"}

    @staticmethod
    def format_cron_trigger(
        trigger_str: str,
    ) -> str:
        """Convert cron trigger to human readable format"""
        try:
            cron_match = re.search(r"cron\[([^\]]+)\]", trigger_str)
            if not cron_match:
                return trigger_str

            cron_parts = {}
            parts = cron_match.group(1).split(", ")

            for part in parts:
                key, value = part.split("=", 1)
                cron_parts[key] = value.strip("'")

            minute = cron_parts.get("minute", "*")
            hour = cron_parts.get("hour", "*")
            day = cron_parts.get("day", "*")
            month = cron_parts.get("month", "*")
            day_of_week = cron_parts.get("day_of_week", "*")

            cron_expression = f"{minute} {hour} {day} {month} {day_of_week}"

            result = CronDescriptionService.get_human_description(cron_expression)

            if result["description"]:
                return result["description"]
            else:
                return cron_expression

        except (ValueError, KeyError, AttributeError):
            return trigger_str
