"""
This module provides a clean, maintainable interface for managing
Graphiant network configurations using composition and proper separation of concerns.
"""

from typing import Optional, Dict
from .config_utils import ConfigUtils
from .interface_manager import InterfaceManager
from .bgp_manager import BGPManager
from .global_config_manager import GlobalConfigManager
from .site_manager import SiteManager
from .data_exchange_manager import DataExchangeManager
from .device_config_manager import DeviceConfigManager
from .vrrp_interface_manager import VRRPInterfaceManager
from .lag_interface_manager import LagInterfaceManager
from .site_to_site_vpn_manager import SiteToSiteVpnManager
from .logger import setup_logger
from .exceptions import GraphiantPlaybookError

LOG = setup_logger()


class GraphiantConfig:
    """
    Main interface for Graphiant Playbooks.

    This class provides a clean, maintainable interface for managing
    Graphiant network configurations. It uses composition to delegate
    specific responsibilities to specialized manager classes.

    The class follows the Single Responsibility Principle by delegating
    different types of configurations to appropriate managers:
    - InterfaceManager: Interface and circuit configurations
    - BGPManager: BGP peering configurations
    - GlobalConfigManager: Global configuration objects
    - SiteManager: Site management operations
    """

    def __init__(self, base_url: Optional[str] = None, username: Optional[str] = None,
                 password: Optional[str] = None, **kwargs):
        """
        Initialize the GraphiantConfig class with connection parameters.

        Args:
            base_url: Base URL for the Graphiant API
            username: Username for authentication
            password: Password for authentication
            **kwargs: Additional parameters passed to ConfigUtils
        """
        try:
            # Initialize the base utilities
            self.config_utils = ConfigUtils(
                base_url=base_url,
                username=username,
                password=password,
                **kwargs
            )

            # Initialize specialized managers
            self.interfaces = InterfaceManager(self.config_utils)
            self.bgp = BGPManager(self.config_utils)
            self.global_config = GlobalConfigManager(self.config_utils)
            self.sites = SiteManager(self.config_utils)
            self.data_exchange = DataExchangeManager(self.config_utils)
            self.device_config = DeviceConfigManager(self.config_utils)
            self.vrrp_interfaces = VRRPInterfaceManager(self.config_utils)
            self.lag_interfaces = LagInterfaceManager(self.config_utils)
            self.site_to_site_vpn = SiteToSiteVpnManager(self.config_utils)

            LOG.info("GraphiantConfig class initialized successfully with all managers")

        except Exception as e:
            LOG.error("Failed to initialize GraphiantConfig class: %s", str(e))
            raise GraphiantPlaybookError(f"GraphiantConfig initialization failed: {str(e)}")

    def get_manager_status(self) -> Dict[str, bool]:
        """
        Get the status of all managers.

        Returns:
            Dictionary indicating which managers are properly initialized
        """
        return {
            'interfaces': hasattr(self, 'interfaces') and self.interfaces is not None,
            'bgp': hasattr(self, 'bgp') and self.bgp is not None,
            'global_config': hasattr(self, 'global_config') and self.global_config is not None,
            'sites': hasattr(self, 'sites') and self.sites is not None,
            'data_exchange': hasattr(self, 'data_exchange') and self.data_exchange is not None,
            'device_config': hasattr(self, 'device_config') and self.device_config is not None,
            'vrrp_interfaces': hasattr(self, 'vrrp_interfaces') and self.vrrp_interfaces is not None,
            'config_utils': hasattr(self, 'config_utils') and self.config_utils is not None,
            'lag_interfaces': hasattr(self, 'lag_interfaces') and self.lag_interfaces is not None,
            'site_to_site_vpn': hasattr(self, 'site_to_site_vpn') and self.site_to_site_vpn is not None,
        }
