"""
Graphiant Ansible Collection - Module Utilities

This module provides common utilities for Graphiant Ansible modules.
"""

import sys
import os
from typing import Dict, Any


def _import_graphiant_libs():
    """
    Import Graphiant library modules.

    This function uses two import strategies:
    1. Ansible FQCN import: Required for Ansible modules so Ansible bundles the libs/ directory
    2. Direct import: Fallback for direct Python usage (e.g., test.py, scripts)

    Ansible traces FQCN imports to know what module_utils to bundle. Without FQCN,
    Ansible won't include the libs/ subdirectory in the module payload.

    IMPORTANT: We do NOT modify sys.path for the FQCN import case to avoid
    interfering with Ansible's own imports (which can cause sentinel module errors
    in ansible-core 2.19.x).

    Returns:
        tuple: (GraphiantConfig, GraphiantPlaybookError, ConfigurationError, APIError, DeviceNotFoundError)
        Returns (None, None, None, None, None) if imports fail (for ansible-test validate-modules)
    """
    # Strategy 1: Use Ansible FQCN import (required for Ansible module execution)
    # This tells Ansible to bundle the libs/ directory in the module payload
    # Do NOT modify sys.path here - let Ansible handle it
    try:
        from ansible_collections.graphiant.graphiant_playbooks.plugins.module_utils.libs.graphiant_config import (
            GraphiantConfig
        )
        from ansible_collections.graphiant.graphiant_playbooks.plugins.module_utils.libs.exceptions import (
            GraphiantPlaybookError, ConfigurationError, APIError, DeviceNotFoundError
        )
        return GraphiantConfig, GraphiantPlaybookError, ConfigurationError, APIError, DeviceNotFoundError
    except ImportError:
        pass

    # Strategy 2: Fallback for direct Python usage (e.g., test.py, scripts)
    # Only modify sys.path here, AFTER FQCN import failed
    # Use append instead of insert(0) to avoid interfering with other imports
    module_utils_dir = os.path.dirname(os.path.abspath(__file__))
    if module_utils_dir not in sys.path:
        sys.path.append(module_utils_dir)  # append, not insert(0)

    try:
        from libs.graphiant_config import GraphiantConfig
        from libs.exceptions import GraphiantPlaybookError, ConfigurationError, APIError, DeviceNotFoundError
        return GraphiantConfig, GraphiantPlaybookError, ConfigurationError, APIError, DeviceNotFoundError
    except ImportError:
        # Return None values instead of raising to allow ansible-test validate-modules
        # to introspect the module even when dependencies are not available
        return None, None, None, None, None


# Import the Graphiant library modules lazily
# Use a function to get the imports so ansible-test validate-modules can introspect the module
# even when dependencies are not available
_GRAPHiant_LIBS_CACHE = None


def _get_graphiant_libs():
    """
    Get Graphiant library modules, importing them if necessary.

    This lazy import allows ansible-test validate-modules to introspect the module
    even when dependencies are not available.

    Returns:
        tuple: (GraphiantConfig, GraphiantPlaybookError, ConfigurationError, APIError, DeviceNotFoundError)
    """
    global _GRAPHiant_LIBS_CACHE
    if _GRAPHiant_LIBS_CACHE is None:
        _GRAPHiant_LIBS_CACHE = _import_graphiant_libs()
    return _GRAPHiant_LIBS_CACHE


# For backward compatibility and type hints, import at module level
# _import_graphiant_libs() returns None values if imports fail, allowing
# ansible-test validate-modules to introspect the module even when dependencies are not available
# The actual imports will happen lazily when functions are called via _get_graphiant_libs()
GraphiantConfig, GraphiantPlaybookError, ConfigurationError, APIError, DeviceNotFoundError = _import_graphiant_libs()


class GraphiantConnection:
    """
    Manages connection to Graphiant API and provides common functionality.
    """

    def __init__(self, host: str, username: str, password: str):
        """
        Initialize Graphiant connection.

        Args:
            host: Graphiant API host URL
            username: Username for authentication
            password: Password for authentication
        """
        self.host = host
        self.username = username
        self.password = password
        self._graphiant_config = None

    @property
    def graphiant_config(self):
        """
        Get or create GraphiantConfig instance.

        Returns:
            GraphiantConfig: Graphiant configuration instance
        """
        # Lazy import to support ansible-test validate-modules
        graphiant_libs = _get_graphiant_libs()
        GraphiantConfig = graphiant_libs[0]
        GraphiantPlaybookError = graphiant_libs[1]

        if GraphiantConfig is None:
            raise ImportError(
                "Failed to import Graphiant libraries. "
                "Ensure the collection is properly installed and required dependencies are met."
            )

        if self._graphiant_config is None:
            try:
                self._graphiant_config = GraphiantConfig(
                    base_url=self.host,
                    username=self.username,
                    password=self.password
                )
            except Exception as e:
                raise GraphiantPlaybookError(f"Failed to initialize Graphiant connection: {str(e)}")

        return self._graphiant_config

    def test_connection(self) -> bool:
        """
        Test the connection to Graphiant API.

        Returns:
            bool: True if connection is successful, False otherwise
        """
        try:
            # Try to get manager status to test connection
            status = self.graphiant_config.get_manager_status()
            return all(status.values())
        except Exception:
            return False


def get_graphiant_connection(module_params: Dict[str, Any]) -> GraphiantConnection:
    """
    Create and return a Graphiant connection from module parameters.

    Args:
        module_params: Ansible module parameters

    Returns:
        GraphiantConnection: Initialized connection object
    """
    required_params = ['host', 'username', 'password']
    for param in required_params:
        if param not in module_params:
            raise ValueError(f"Missing required parameter: {param}")

    return GraphiantConnection(
        host=module_params['host'],
        username=module_params['username'],
        password=module_params['password']
    )


def handle_graphiant_exception(exception: Exception, operation: str) -> str:
    """
    Handle Graphiant exceptions and return user-friendly error messages.

    Args:
        exception: The exception that occurred
        operation: Description of the operation that failed

    Returns:
        str: User-friendly error message
    """
    # Lazy import to support ansible-test validate-modules
    graphiant_libs = _get_graphiant_libs()
    GraphiantPlaybookError = graphiant_libs[1]
    ConfigurationError = graphiant_libs[2]
    APIError = graphiant_libs[3]
    DeviceNotFoundError = graphiant_libs[4]

    # If imports are not available, return a generic error message
    if ConfigurationError is None or APIError is None or DeviceNotFoundError is None or GraphiantPlaybookError is None:
        return f"Error during {operation}: {str(exception)}"

    if isinstance(exception, ConfigurationError):
        return f"Configuration error during {operation}: {str(exception)}"
    elif isinstance(exception, APIError):
        return f"API error during {operation}: {str(exception)}"
    elif isinstance(exception, DeviceNotFoundError):
        return f"Device not found during {operation}: {str(exception)}"
    elif isinstance(exception, GraphiantPlaybookError):
        return f"Graphiant playbook error during {operation}: {str(exception)}"
    else:
        return f"Unexpected error during {operation}: {str(exception)}"
