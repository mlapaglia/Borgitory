"""Service for generating human-readable descriptions of cron expressions."""

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
        except Exception as e:
            return {"description": None, "error": "Invalid cron expression"}

    @staticmethod
    def validate_cron_expression(cron_expression: str) -> bool:
        """
        Validate if a cron expression is properly formatted.

        Args:
            cron_expression: The cron expression to validate

        Returns:
            True if valid, False otherwise
        """
        if not cron_expression or not cron_expression.strip():
            return False

        try:
            get_description(cron_expression.strip())
            return True
        except Exception:
            return False
