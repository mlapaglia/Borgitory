"""
Template path resolution utilities for both development and packaged environments.
"""

import os
import logging
from importlib import resources

logger = logging.getLogger(__name__)


def get_template_directory() -> str:
    """
    Get the correct template directory path for both development and packaged environments.

    Returns:
        str: Path to the templates directory
    """
    # Configure template path using package resources
    try:
        # Use importlib.resources to get the package directory
        package_root = resources.files("borgitory")
        template_path = str(package_root / "templates")

        logger.debug(f"Trying importlib.resources template path: {template_path}")

        # Verify the path exists
        if not os.path.exists(template_path):
            logger.warning(f"Template path not found: {template_path}")
            raise FileNotFoundError("Template path not found in package")

        logger.debug("Successfully resolved template path using importlib.resources")
        return template_path

    except (ImportError, AttributeError, TypeError, FileNotFoundError) as e:
        logger.warning(f"importlib.resources failed for templates: {e}")
        # Fallback for development or if resources not available
        if os.path.exists("src/borgitory/templates"):
            template_path = "src/borgitory/templates"
            logger.debug("Using development template path (src/borgitory/)")
            return template_path
        elif os.path.exists("templates"):
            template_path = "templates"
            logger.debug("Using current directory template path")
            return template_path
        else:
            # Last resort - try to find borgitory package in site-packages
            try:
                import borgitory

                package_dir = os.path.dirname(borgitory.__file__)
                template_path = os.path.join(package_dir, "templates")
                logger.debug(
                    f"Using package directory fallback for templates: {package_dir}"
                )
                return template_path
            except Exception as fallback_error:
                logger.error(
                    f"All template path resolution methods failed: {fallback_error}"
                )
                return "templates"


def get_static_directory() -> str:
    """
    Get the correct static files directory path for both development and packaged environments.

    Returns:
        str: Path to the static directory
    """
    # Configure static path using package resources
    try:
        # Use importlib.resources to get the package directory
        package_root = resources.files("borgitory")
        static_path = str(package_root / "static")

        logger.debug(f"Trying importlib.resources static path: {static_path}")

        # Verify the path exists
        if not os.path.exists(static_path):
            logger.warning(f"Static path not found: {static_path}")
            raise FileNotFoundError("Static path not found in package")

        logger.debug("Successfully resolved static path using importlib.resources")
        return static_path

    except (ImportError, AttributeError, TypeError, FileNotFoundError) as e:
        logger.warning(f"importlib.resources failed for static: {e}")
        # Fallback for development or if resources not available
        if os.path.exists("src/borgitory/static"):
            static_path = "src/borgitory/static"
            logger.debug("Using development static path (src/borgitory/)")
            return static_path
        elif os.path.exists("static"):
            static_path = "static"
            logger.debug("Using current directory static path")
            return static_path
        else:
            # Last resort - try to find borgitory package in site-packages
            try:
                import borgitory

                package_dir = os.path.dirname(borgitory.__file__)
                static_path = os.path.join(package_dir, "static")
                logger.debug(
                    f"Using package directory fallback for static: {package_dir}"
                )
                return static_path
            except Exception as fallback_error:
                logger.error(
                    f"All static path resolution methods failed: {fallback_error}"
                )
                return "static"
