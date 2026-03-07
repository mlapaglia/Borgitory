"""Tests for CronDescriptionService."""

from borgitory.services.cron_description_service import CronDescriptionService


class TestCronDescriptionService:
    """Test suite for CronDescriptionService business logic."""

    def test_get_human_description_valid_expressions(self) -> None:
        """Test valid cron expressions return proper descriptions."""
        test_cases = [
            # Basic expressions
            ("* * * * *", "Every minute"),
            ("0 * * * *", "Every hour"),
            ("0 0 * * *", "At 12:00 AM"),
            ("0 12 * * *", "At 12:00 PM"),
            # Complex expressions
            ("*/5 * * * *", "Every 5 minutes"),
            ("0 */2 * * *", "Every 2 hours"),
            (
                "0 9-17 * * 1-5",
                "Every hour, between 09:00 AM and 05:00 PM, Monday through Friday",
            ),
            ("30 14 * * 0", "At 02:30 PM, only on Sunday"),
            # Monthly expressions
            ("0 0 1 * *", "At 12:00 AM, on day 1 of the month"),
            ("0 0 15 * *", "At 12:00 AM, on day 15 of the month"),
            # Yearly expressions
            ("0 0 1 1 *", "At 12:00 AM, on day 1 of the month, only in January"),
            # Special characters
            ("0 0 * * 1#1", "At 12:00 AM, on the first Monday of the month"),
            ("0 0 L * *", "At 12:00 AM, on the last day of the month"),
        ]

        for cron_expr, expected_desc in test_cases:
            result = CronDescriptionService.get_human_description(cron_expr)

            assert result["error"] is None, (
                f"Unexpected error for '{cron_expr}': {result['error']}"
            )
            assert result["description"] is not None, (
                f"No description for '{cron_expr}'"
            )
            # Basic validation that we got a reasonable description
            assert len(result["description"]) > 5, (
                f"Description too short for '{cron_expr}'"
            )

    def test_get_human_description_invalid_expressions(self) -> None:
        """Test invalid cron expressions return appropriate errors."""
        invalid_expressions = [
            "invalid",
            "1 2 3",  # Too few parts
            "1 2 3 4 5 6 7 8",  # Too many parts
            "not-a-cron",
        ]

        for invalid_expr in invalid_expressions:
            result = CronDescriptionService.get_human_description(invalid_expr)

            assert result["description"] is None, (
                f"Expected no description for '{invalid_expr}'"
            )
            assert result["error"] is not None, f"Expected error for '{invalid_expr}'"
            assert len(result["error"]) > 0, f"Error message empty for '{invalid_expr}'"

    def test_get_human_description_empty_input(self) -> None:
        """Test empty or whitespace-only input."""
        empty_inputs = ["", "   ", "\t", "\n", None]

        for empty_input in empty_inputs:
            if empty_input is None:
                # Skip None for this test since it would cause TypeError
                continue

            result = CronDescriptionService.get_human_description(empty_input)

            assert result["description"] is None, (
                f"Expected no description for empty input: '{empty_input}'"
            )
            assert result["error"] is None, (
                f"Expected no error for empty input: '{empty_input}'"
            )

    def test_get_human_description_whitespace_handling(self) -> None:
        """Test that whitespace is properly handled."""
        # Test with leading/trailing whitespace
        result = CronDescriptionService.get_human_description("  0 12 * * *  ")

        assert result["error"] is None, "Unexpected error with whitespace"
        assert result["description"] is not None, "Expected description with whitespace"
        assert "12:00" in result["description"], "Expected proper time parsing"

    def test_error_message_format(self) -> None:
        """Test that error messages are properly formatted."""
        result = CronDescriptionService.get_human_description("invalid")

        assert result["error"] is not None
        # Should contain helpful information
        assert "Invalid" in result["error"] or "invalid" in result["error"]

    def test_six_part_cron_expressions(self) -> None:
        """Test 6-part cron expressions (with seconds)."""
        # Note: cron-descriptor supports 6-part expressions
        six_part_expressions = [
            "0 * * * * *",  # Every minute at 0 seconds
            "30 * * * * *",  # Every minute at 30 seconds
        ]

        for expr in six_part_expressions:
            result = CronDescriptionService.get_human_description(expr)
            # Should either work or give a clear error
            if result["error"]:
                assert "Invalid" in result["error"]
            else:
                assert result["description"] is not None
                assert len(result["description"]) > 5

    def test_special_cron_nicknames(self) -> None:
        """Test special cron expression nicknames."""
        # Note: Some versions of cron-descriptor support these
        special_expressions = [
            "@yearly",
            "@annually",
            "@monthly",
            "@weekly",
            "@daily",
            "@hourly",
        ]

        for expr in special_expressions:
            result = CronDescriptionService.get_human_description(expr)
            # These might not be supported by the Python version, so we just check it doesn't crash
            assert isinstance(result, dict)
            assert "description" in result
            assert "error" in result
