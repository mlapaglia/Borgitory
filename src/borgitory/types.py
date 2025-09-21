"""
Common type definitions for the Borgitory application.

This module provides consistent type aliases used throughout the codebase
to ensure type compatibility and reduce variance issues.
"""

from typing import Dict, Union

# Common type alias for configuration dictionaries
# Used across all services for consistent type handling
ConfigDict = Dict[str, Union[str, int, float, bool, None]]
