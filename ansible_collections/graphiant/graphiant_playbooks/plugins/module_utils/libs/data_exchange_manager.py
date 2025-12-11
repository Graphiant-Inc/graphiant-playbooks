"""
Data Exchange Manager for Graphiant Playbooks

This module provides functionality for managing Data Exchange workflows including:
- Create New Services
- Create New Customers
- Match Services to Customers
"""

import os
from typing import Dict, Any, Optional

try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False

from .base_manager import BaseManager
from .logger import setup_logger
from .exceptions import ConfigurationError

# Required dependencies - checked when functions are called
# Don't raise at module level to allow import test to pass

LOG = setup_logger()


class DataExchangeManager(BaseManager):
    """
    Manager for Data Exchange workflows and operations.
    """

    def configure(self, config_yaml_file: str) -> None:
        """
        Configure Data Exchange resources based on the provided YAML file.
        This is the main entry point for Data Exchange configuration.

        Args:
            config_yaml_file: Path to the YAML configuration file
        """
        LOG.info("Configuring Data Exchange resources from %s", config_yaml_file)

        # Create services first
        self.create_services(config_yaml_file)

        # Create customers
        self.create_customers(config_yaml_file)

        # Match services to customers
        self.match_service_to_customers(config_yaml_file)

        LOG.info("Data Exchange configuration completed successfully")

    def deconfigure(self, config_yaml_file: str) -> None:
        """
        Deconfigure Data Exchange resources based on the provided YAML file.
        This is the main entry point for Data Exchange deconfiguration.

        Args:
            config_yaml_file: Path to the YAML configuration file
        """
        LOG.info("Deconfiguring Data Exchange resources from %s", config_yaml_file)

        # Delete customers first (they depend on services)
        self.delete_customers(config_yaml_file)

        # Delete services
        self.delete_services(config_yaml_file)

        LOG.info("Data Exchange deconfiguration completed successfully")

    def create_services(self, config_yaml_file: str) -> None:
        """
        Create new Data Exchange services from YAML configuration.

        Args:
            config_yaml_file (str): Path to the YAML configuration file
        """
        try:
            LOG.info("Creating Data Exchange service from %s", config_yaml_file)
            config_data = self.render_config_file(config_yaml_file)

            if not config_data or 'data_exchange_services' not in config_data:
                LOG.info("No data_exchange_services configuration found in YAML file")
                return

            services = config_data['data_exchange_services']
            if not isinstance(services, list):
                raise ConfigurationError("Configuration error: 'data_exchange_services' must be a list.")

            # Print current enterprise info
            LOG.info("DataExchangeManager: Current enterprise info: %s", self.gsdk.enterprise_info)

            created_count = 0
            skipped_count = 0

            for service_config in services:
                service_name = service_config.get('serviceName')
                LOG.info("--------------------------------")
                LOG.info("create_services: Creating service '%s'", service_name)
                if not service_name:
                    raise ConfigurationError("Configuration error: Each service must have a 'serviceName' field.")

                # Check if service already exists
                existing_service = self.gsdk.get_data_exchange_service_by_name(service_name)
                if existing_service:
                    LOG.info("Service '%s' already exists (ID: %s), skipping creation", service_name, existing_service.id)
                    skipped_count += 1
                    continue

                if 'policy' in service_config:
                    # Resolve LAN segment ID if provided by name
                    if 'serviceLanSegment' in service_config['policy']:
                        lan_segment_name = service_config['policy']['serviceLanSegment']
                        if isinstance(lan_segment_name, str):
                            lan_segment_id = self.gsdk.get_lan_segment_id(lan_segment_name)
                            if lan_segment_id:
                                service_config['policy']['serviceLanSegment'] = lan_segment_id
                            else:
                                raise ConfigurationError(
                                    f"LAN segment '{lan_segment_name}' not found for service '{service_name}'.")

                    # Resolve site or site list IDs if provided by names
                    self._resolve_site_ids(service_config['policy'], service_name)
                    self._resolve_site_list_ids(service_config['policy'], service_name)

                # Create service directly
                LOG.info("Service configuration: %s", service_config)
                LOG.info("create_data_exchange_services: Creating service '%s'", service_name)
                self.gsdk.create_data_exchange_services(service_config)
                LOG.info("Successfully created service '%s'", service_name)
                created_count += 1

            LOG.info("Data Exchange service creation completed: %s created, %s skipped", created_count, skipped_count)

        except ConfigurationError:
            raise
        except Exception as e:
            LOG.error("Failed to create Data Exchange service: %s", e)
            raise ConfigurationError(f"Data Exchange service creation failed: {e}")

    def _resolve_site_ids(self, policy_config: dict, service_name: str) -> None:
        """
        Resolve site names to site IDs in the policy configuration.

        Args:
            policy_config (dict): Policy configuration to update
            service_name (str): Service name for error reporting
        """
        if 'site' in policy_config and isinstance(policy_config['site'], list):
            for site_entry in policy_config['site']:
                if 'sites' in site_entry and isinstance(site_entry['sites'], list):
                    resolved_site_ids = []
                    for site_name in site_entry['sites']:
                        if isinstance(site_name, str):
                            site_id = self.gsdk.get_site_id(site_name)
                            if site_id:
                                resolved_site_ids.append(site_id)
                            else:
                                raise ConfigurationError(f"Site '{site_name}' not found for service '{service_name}'.")
                        else:
                            resolved_site_ids.append(site_name)  # Already an ID
                    site_entry['sites'] = resolved_site_ids

    def _resolve_site_list_ids(self, policy_config: dict, service_name: str) -> None:
        """
        Resolve site list names to site list IDs in the policy configuration.

        Args:
            policy_config (dict): Policy configuration to update
            service_name (str): Service name for error reporting
        """
        if 'site' in policy_config and isinstance(policy_config['site'], list):
            for site_entry in policy_config['site']:
                if 'siteLists' in site_entry and isinstance(site_entry['siteLists'], list):
                    resolved_site_list_ids = []
                    for site_list_name in site_entry['siteLists']:
                        if isinstance(site_list_name, str):
                            site_list_id = self.gsdk.get_site_list_id(site_list_name)
                            if site_list_id:
                                resolved_site_list_ids.append(site_list_id)
                            else:
                                raise ConfigurationError(f"Site list '{site_list_name}' not found "
                                                         f"for service '{service_name}'.")
                        else:
                            resolved_site_list_ids.append(site_list_name)  # Already an ID
                    site_entry['siteLists'] = resolved_site_list_ids

    def get_services_summary(self) -> Dict[str, Any]:
        """
        Get summary of all Data Exchange services.

        Returns:
            dict: Services summary response
        """
        try:
            # Print current enterprise info
            LOG.info("DataExchangeManager: Current enterprise info: %s", self.gsdk.enterprise_info)

            LOG.info("Retrieving Data Exchange services summary")
            response = self.gsdk.get_data_exchange_services_summary()

            # Display services in a nice table format
            if response.info:
                service_table = []
                for service in response.info:
                    # Get publisher/subscriber role
                    role = "Publisher" if getattr(service, 'is_publisher', False) else "Subscriber"

                    # Get matched customers count
                    matched_customers = getattr(service, 'matched_customers', 0)

                    service_table.append([
                        service.id,
                        service.name,
                        service.status,
                        role,
                        matched_customers
                    ])

                LOG.info("Services Summary:\n%s",
                         tabulate(service_table,
                                  headers=['ID', 'Service Name', 'Status', 'Role', 'Matched Customers'],
                                  tablefmt='grid'))

            return response.to_dict()
        except Exception as e:
            LOG.error("Failed to retrieve services summary: %s", e)
            raise ConfigurationError(f"Failed to retrieve services summary: {e}")

    def get_service_by_name(self, service_name: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific Data Exchange service by name.

        Args:
            service_name (str): Name of the service to retrieve

        Returns:
            dict or None: Service details if found, None otherwise
        """
        try:
            LOG.info("Retrieving Data Exchange service '%s'", service_name)
            service = self.gsdk.get_data_exchange_service_by_name(service_name)
            return service
        except Exception as e:
            LOG.error("Failed to retrieve service '%s': %s", service_name, e)
            raise ConfigurationError(f"Failed to retrieve service '{service_name}': {e}")

    def create_customers(self, config_yaml_file: str) -> None:
        """
        Create a new Data Exchange customer from YAML configuration.

        Args:
            config_yaml_file (str): Path to the YAML configuration file
        """
        try:
            LOG.info("Creating Data Exchange customer from %s", config_yaml_file)
            config_data = self.render_config_file(config_yaml_file)

            if not config_data or 'data_exchange_customers' not in config_data:
                LOG.info("No data_exchange_customers configuration found in YAML file")
                return

            customers = config_data['data_exchange_customers']
            if not isinstance(customers, list):
                raise ConfigurationError("Configuration error: 'data_exchange_customers' must be a list.")

            # Print current enterprise info
            LOG.info("DataExchangeManager: Current enterprise info: %s", self.gsdk.enterprise_info)

            created_count = 0
            skipped_count = 0

            for customer_config in customers:
                customer_name = customer_config.get('name')
                LOG.info("--------------------------------")
                LOG.info("create_customers: Creating customer '%s'", customer_name)
                if not customer_name:
                    raise ConfigurationError("Configuration error: Each customer must have a 'name' field.")

                # Check if customer already exists
                existing_customer = self.gsdk.get_data_exchange_customer_by_name(customer_name)
                if existing_customer:
                    LOG.info("Customer '%s' already exists (ID: %s), skipping creation",
                             customer_name, existing_customer.id)
                    skipped_count += 1
                    continue

                # Create customer directly
                LOG.info("Customer configuration: %s", customer_config)
                LOG.info("create_data_exchange_customers: Creating customer '%s'", customer_name)
                self.gsdk.create_data_exchange_customers(customer_config)
                LOG.info("Successfully created customer '%s'", customer_name)
                created_count += 1

            LOG.info("Data Exchange customer creation completed: %s created, %s skipped", created_count, skipped_count)

        except ConfigurationError:
            raise
        except Exception as e:
            LOG.error("Failed to create Data Exchange customer: %s", e)
            raise ConfigurationError(f"Data Exchange customer creation failed: {e}")

    def get_customers_summary(self) -> Dict[str, Any]:
        if not HAS_TABULATE:
            raise ImportError("tabulate is required for this method. Install it with: pip install tabulate")
        """
        Get summary of all Data Exchange customers.

        Returns:
            dict: Customers summary response
        """
        try:
            # Print current enterprise info
            LOG.info("DataExchangeManager: Current enterprise info: %s", self.gsdk.enterprise_info)

            LOG.info("Retrieving Data Exchange customers summary")
            response = self.gsdk.get_data_exchange_customers_summary()

            # Display customers in a nice table format
            if response.customers:
                customer_table = []
                for customer in response.customers:
                    # Get customer type (Non-Graphiant or Graphiant)
                    customer_type = "Non-Graphiant" if customer.type == "non_graphiant_peer" else "Graphiant"

                    # Get matched services count
                    matched_services = getattr(customer, 'matched_services', 0)

                    customer_table.append([
                        customer.id,
                        customer.name,
                        customer_type,
                        customer.status,
                        matched_services
                    ])

                LOG.info("Customers Summary:\n%s",
                         tabulate(customer_table,
                                  headers=['ID', 'Customer Name', 'Customer Type', 'Status', 'Matched Services'],
                                  tablefmt='grid'))

            return response.to_dict()
        except Exception as e:
            LOG.error("Failed to retrieve customers summary: %s", e)
            raise ConfigurationError(f"Failed to retrieve customers summary: {e}")

    def get_customer_by_name(self, customer_name: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific Data Exchange customer by name.

        Args:
            customer_name (str): Name of the customer to retrieve

        Returns:
            dict or None: Customer details if found, None otherwise
        """
        try:
            LOG.info("Retrieving Data Exchange customer '%s'", customer_name)
            customer = self.gsdk.get_data_exchange_customer_by_name(customer_name)
            return customer
        except Exception as e:
            LOG.error("Failed to retrieve customer '%s': %s", customer_name, e)
            raise ConfigurationError(f"Failed to retrieve customer '{customer_name}': {e}")

    def delete_customers(self, config_yaml_file: str) -> None:
        """
        Delete Data Exchange customers from YAML configuration.

        Args:
            config_yaml_file (str): Path to the YAML configuration file
        """
        try:
            LOG.info("Deleting Data Exchange customers from %s", config_yaml_file)
            config_data = self.render_config_file(config_yaml_file)

            if not config_data or 'data_exchange_customers' not in config_data:
                LOG.info("No data_exchange_customers configuration found in YAML file")
                return

            customers = config_data['data_exchange_customers']
            if not isinstance(customers, list):
                raise ConfigurationError("Configuration error: 'data_exchange_customers' must be a list.")

            # Print current enterprise info
            LOG.info("DataExchangeManager: Current enterprise info: %s", self.gsdk.enterprise_info)

            deleted_count = 0
            skipped_count = 0

            for customer_config in customers:
                customer_name = customer_config.get('name')
                LOG.info("--------------------------------")
                LOG.info("delete_customers: Deleting customer '%s'", customer_name)
                if not customer_name:
                    raise ConfigurationError("Configuration error: Each customer must have a 'name' field.")

                # Get customer ID
                customer = self.gsdk.get_data_exchange_customer_by_name(customer_name)
                if not customer:
                    LOG.info("Customer '%s' not found, skipping deletion", customer_name)
                    skipped_count += 1
                    continue

                # Delete customer directly
                LOG.info("delete_data_exchange_customer: Deleting customer '%s'", customer_name)
                self.gsdk.delete_data_exchange_customer(customer.id)
                LOG.info("Successfully deleted customer '%s' (ID: %s)", customer_name, customer.id)
                deleted_count += 1

            LOG.info("Data Exchange customer deletion completed: %s deleted, %s skipped", deleted_count, skipped_count)

        except ConfigurationError:
            raise
        except Exception as e:
            LOG.error("Failed to delete Data Exchange customers: %s", e)
            raise ConfigurationError(f"Data Exchange customer deletion failed: {e}")

    def delete_services(self, config_yaml_file: str) -> None:
        """
        Delete Data Exchange services from YAML configuration.

        Args:
            config_yaml_file (str): Path to the YAML configuration file
        """
        try:
            LOG.info("Deleting Data Exchange services from %s", config_yaml_file)
            config_data = self.render_config_file(config_yaml_file)

            if not config_data or 'data_exchange_services' not in config_data:
                LOG.info("No data_exchange_services configuration found in YAML file")
                return

            services = config_data['data_exchange_services']
            if not isinstance(services, list):
                raise ConfigurationError("Configuration error: 'data_exchange_services' must be a list.")

            # Print current enterprise info
            LOG.info("DataExchangeManager: Current enterprise info: %s", self.gsdk.enterprise_info)

            deleted_count = 0
            skipped_count = 0

            for service_config in services:
                service_name = service_config.get('serviceName')
                LOG.info("--------------------------------")
                LOG.info("delete_services: Deleting service '%s'", service_name)
                if not service_name:
                    raise ConfigurationError("Configuration error: Each service must have a 'serviceName' field.")

                # Get service ID
                service = self.gsdk.get_data_exchange_service_by_name(service_name)
                if not service:
                    LOG.info("Service '%s' not found, skipping deletion", service_name)
                    skipped_count += 1
                    continue

                # Delete service directly
                LOG.info("delete_data_exchange_service: Deleting service '%s'", service_name)
                self.gsdk.delete_data_exchange_service(service.id)
                LOG.info("Successfully deleted service '%s' (ID: %s)", service_name, service.id)
                deleted_count += 1

            LOG.info("Data Exchange service deletion completed: %s deleted, %s skipped", deleted_count, skipped_count)

        except ConfigurationError:
            raise
        except Exception as e:
            LOG.error("Failed to delete Data Exchange services: %s", e)
            raise ConfigurationError(f"Data Exchange service deletion failed: {e}")

    def get_service_details(self, service_id: int) -> Dict[str, Any]:
        """
        Get detailed information about a specific Data Exchange service.

        Args:
            service_id (int): ID of the service to retrieve

        Returns:
            dict: Service details response
        """
        try:
            LOG.info("Retrieving Data Exchange service details for ID: %s", service_id)
            response = self.gsdk.get_data_exchange_service_details(service_id)
            return response
        except Exception as e:
            LOG.error("Failed to retrieve service details for ID %s: %s", service_id, e)
            raise ConfigurationError(f"Failed to retrieve service details for ID {service_id}: {e}")

    def _save_match_service_to_customer_responses(self, match_responses: list, config_yaml_file: str) -> None:
        """
        Save match service to customer responses to JSON files.
        Updates existing entries if they match (customer_name, service_name), otherwise appends new entries.

        Args:
            match_responses (list): List of match response dictionaries
            config_yaml_file (str): Path to the YAML configuration file to determine output directory
        """
        if not match_responses:
            return

        import json
        from datetime import datetime

        # Resolve config file path using the same logic as render_config_file
        # Handle absolute paths
        if os.path.isabs(config_yaml_file):
            resolved_config_file = config_yaml_file
        else:
            # Handle relative paths by concatenating with config_path
            # Security: Normalize path to prevent path traversal attacks
            resolved_config_file = os.path.normpath(os.path.join(self.config_utils.config_path, config_yaml_file))
            # Security: Validate that resolved path is within config_path to prevent path traversal
            config_path_real = os.path.realpath(self.config_utils.config_path)
            resolved_config_file_real = os.path.realpath(resolved_config_file)
            if not resolved_config_file_real.startswith(config_path_real):
                raise ConfigurationError(
                    f"Security: Path traversal detected. Config file path '{config_yaml_file}' "
                    f"resolves outside config directory."
                )

        # Create output directory near the config file (same logic as render_config_file)
        output_dir = os.path.join(os.path.dirname(resolved_config_file), "output")
        os.makedirs(output_dir, exist_ok=True)

        # Generate output filenames based on input config
        base_name = os.path.splitext(os.path.basename(resolved_config_file))[0]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Create two files: one with timestamp, one with _latest suffix
        timestamped_file = os.path.join(output_dir, f"{base_name}_responses_{timestamp}.json")
        latest_file = os.path.join(output_dir, f"{base_name}_responses_latest.json")

        # Read existing latest file if it exists
        existing_responses = []
        if os.path.exists(latest_file):
            try:
                with open(latest_file, 'r') as f:
                    existing_responses = json.load(f)
                LOG.info("Loaded %s existing entries from %s", len(existing_responses), latest_file)
            except (json.JSONDecodeError, IOError) as e:
                LOG.warning("Could not read existing latest file %s: %s. Starting fresh.", latest_file, e)

        # Create a dictionary for efficient lookup: key = (customer_name, service_name)
        # This allows us to update existing entries or add new ones
        response_dict = {}
        for entry in existing_responses:
            key = (entry.get('customer_name'), entry.get('service_name'))
            if key[0] and key[1]:  # Only add if both keys are present
                response_dict[key] = entry

        # Update or add new match responses
        updated_count = 0
        added_count = 0
        for new_response in match_responses:
            key = (new_response.get('customer_name'), new_response.get('service_name'))
            if key[0] and key[1]:
                if key in response_dict:
                    # Update existing entry
                    response_dict[key].update(new_response)
                    updated_count += 1
                    LOG.debug("Updated entry for customer '%s' and service '%s'", key[0], key[1])
                else:
                    # Add new entry
                    response_dict[key] = new_response
                    added_count += 1
                    LOG.debug("Added new entry for customer '%s' and service '%s'", key[0], key[1])

        # Convert back to list for JSON serialization
        merged_responses = list(response_dict.values())

        # Save responses to both JSON files
        with open(timestamped_file, 'w') as f:
            json.dump(merged_responses, f, indent=2)

        with open(latest_file, 'w') as f:
            json.dump(merged_responses, f, indent=2)

        LOG.info("Match responses saved to matches_file_with_timestamp: %s", timestamped_file)
        LOG.info("Latest match responses saved to matches_file: %s", latest_file)
        LOG.info("Updated %s existing entries, added %s new entries. Total entries in matches_file: %s",
                 updated_count, added_count, len(merged_responses))

    def match_service_to_customers(self, config_yaml_file: str) -> None:
        """
        Match Data Exchange services to customers from YAML configuration.

        Args:
            config_yaml_file (str): Path to the YAML configuration file
        """
        try:
            LOG.info("Matching Data Exchange services to customers from %s", config_yaml_file)
            config_data = self.render_config_file(config_yaml_file)

            if not config_data or 'data_exchange_matches' not in config_data:
                LOG.info("No data_exchange_matches configuration found in YAML file")
                raise ConfigurationError("Configuration error: 'data_exchange_matches' key not found in YAML file.")

            matches = config_data['data_exchange_matches']
            if not isinstance(matches, list):
                raise ConfigurationError("Configuration error: 'data_exchange_matches' must be a list.")

            # Print current enterprise info
            LOG.info("DataExchangeManager: Current enterprise info: %s", self.gsdk.enterprise_info)

            matched_count = 0
            skipped_count = 0
            failed_count = 0
            match_responses = []

            for match_config in matches:
                customer_name = match_config.get('customerName')
                service_name = match_config.get('serviceName')
                LOG.info("--------------------------------")
                LOG.info("match_service_to_customers: Matching service '%s' to customer '%s'", service_name, customer_name)
                if not customer_name or not service_name:
                    LOG.error("Configuration error: Each match must have 'customerName' and 'serviceName' fields.")
                    failed_count += 1
                    continue

                # Get customer ID
                customer = self.gsdk.get_data_exchange_customer_by_name(customer_name)
                if not customer:
                    LOG.error("Customer '%s' not found in the enterprise.", customer_name)
                    failed_count += 1
                    continue

                # Get service ID
                service = self.gsdk.get_data_exchange_service_by_name(service_name)
                if not service:
                    LOG.error("Service '%s' not found in the enterprise.", service_name)
                    failed_count += 1
                    continue

                # Check if service is already matched to this customer
                matched_services = self.gsdk.get_matched_services_for_customer(customer.id)
                if matched_services is not None:
                    # Check if this service is already in the matched services list
                    already_matched = False
                    for matched_service in matched_services:
                        if matched_service.name == service_name:
                            LOG.warning("Service '%s' is already matched to customer '%s'. "
                                        "Service ID: %s, Matched Customers: %s. "
                                        "Skipping to avoid 'match already exists' error.",
                                        service_name, customer_name, matched_service.id,
                                        matched_service.matched_customers)
                            already_matched = True
                            skipped_count += 1
                            break

                    if already_matched:
                        continue

                # Use configured service prefixes (user-selected)
                service_prefixes = match_config.get('servicePrefixes', [])
                if not service_prefixes:
                    raise ConfigurationError(
                        f"Configuration error: 'servicePrefixes' must be specified "
                        f"for matching service '{service_name}' to customer '{customer_name}'.")

                # Build match configuration for API call
                match_payload = {
                    "id": customer.id,
                    "service": {
                        "id": service.id,
                        "servicePrefixes": service_prefixes,
                        "nat": match_config.get('nat', [])
                    }
                }

                try:
                    # Perform the match and capture response
                    LOG.info("match_service_to_customer: Matching service '%s' to customer '%s'",
                             service_name, customer_name)
                    response = self.gsdk.match_service_to_customer(match_payload)
                except Exception as e:
                    error_msg = str(e)
                    # Handle "match already exists" errors gracefully till new sdk version 25.11.1 is released.
                    if "match already exists" in error_msg.lower():
                        LOG.info("Service '%s' is already matched to customer '%s', skipping match as it already exists.",
                                 service_name, customer_name)
                        skipped_count += 1
                        continue
                    else:
                        LOG.error("Failed to match service '%s' to customer '%s': %s",
                                  service_name, customer_name, error_msg)
                        failed_count += 1
                        continue

                # Store response data for next workflow
                match_response_data = {
                    "customer_name": customer_name,
                    "service_name": service_name,
                    "customer_id": customer.id,
                    "service_id": service.id,
                    "match_id": response.match_id,
                    "timestamp": response.timestamp if hasattr(response, 'timestamp') else None,
                    "status": "matched"
                }
                match_responses.append(match_response_data)
                LOG.info("Successfully matched service '%s' to customer '%s' with match_id: %s",
                         service_name, customer_name, response.match_id)
                matched_count += 1

            # Save match responses to file for next workflow
            self._save_match_service_to_customer_responses(match_responses, config_yaml_file)

            LOG.info("Data Exchange service matching completed: %s matched, %s skipped, %s failed",
                     matched_count, skipped_count, failed_count)
            if failed_count > 0:
                raise ConfigurationError(f"Data Exchange service to customer matching had {failed_count} failures "
                                         f"out of {matched_count + skipped_count + failed_count} total")
        except Exception as e:
            LOG.error("Failed to match Data Exchange services to customers: %s", e)
            raise ConfigurationError(f"Data Exchange service to customer matching failed: {e}")

    def accept_invitation(self, config_yaml_file: str, matches_file: str = None, dry_run: bool = False) -> None:
        """
        Accept Data Exchange service invitation (Workflow 4).

        Args:
            config_yaml_file (str): Path to YAML configuration file containing acceptance details
            matches_file (str, optional): Path to matches responses JSON file for match ID lookup
            dry_run (bool, optional): If True, skip the actual API call (validation only). Defaults to False.
        """
        try:
            LOG.info("accept_invitation: Loading configuration from %s", config_yaml_file)
            config_data = self.render_config_file(config_yaml_file)

            # All configurations are under 'data_exchange_acceptances' key
            if 'data_exchange_acceptances' not in config_data:
                raise ConfigurationError("Configuration file must contain 'data_exchange_acceptances' key")

            acceptances = config_data['data_exchange_acceptances']

            # Ensure it's always a list
            if not isinstance(acceptances, list):
                raise ConfigurationError("data_exchange_acceptances must be a list of acceptance configurations")

            # Print current enterprise info
            LOG.info("DataExchangeManager: Current enterprise info: %s", self.gsdk.enterprise_info)

            # Log dry-run mode if enabled
            if dry_run:
                LOG.info("accept_invitation: DRY-RUN MODE ENABLED - API calls will be skipped")

            # Validate gateway requirements before processing acceptances
            self._validate_gateway_requirements_for_acceptances(acceptances)

            # Validate VPN profile existence before processing acceptances
            self._validate_vpn_profiles_for_acceptances(acceptances)

            # Process acceptances and log results
            result = self._process_multiple_acceptances(acceptances, matches_file, dry_run)

            # Log summary like other operations
            total_processed = result.get('total_processed', 0)
            total_successful = result.get('total_successful', 0)
            total_failed = total_processed - total_successful

            LOG.info("Data Exchange invitation acceptance completed: %s accepted, %s failed",
                     total_successful, total_failed)

            # Check if there were any failures
            if total_failed > 0:
                if dry_run:
                    LOG.error("[DRY-RUN] accept_invitation: %s out of %s invitation acceptances failed",
                              total_failed, total_processed)
                    raise ConfigurationError(f"[DRY-RUN] Data Exchange invitation acceptance had {total_failed} "
                                             f"failures out of {total_processed} total")
                else:
                    LOG.error("accept_invitation: %s out of %s invitation acceptances failed",
                              total_failed, total_processed)
                    raise ConfigurationError(f"Data Exchange invitation acceptance had {total_failed} failures "
                                             f"out of {total_processed} total")
            return result
        except ConfigurationError:
            raise
        except Exception as e:
            LOG.error("Failed to accept Data Exchange service invitation: %s", e)
            raise ConfigurationError(f"Data Exchange service acceptance failed: {e}")

    def _validate_gateway_requirements_for_acceptances(self, acceptances, min_gateways=2):
        """
        Validate gateway requirements for all acceptances.

        Args:
            acceptances (list): List of acceptance configurations
            min_gateways (int): Minimum number of gateways required per region
        """
        try:
            LOG.info("_validate_gateway_requirements_for_acceptances: Validating gateway requirements for %s acceptances",
                     len(acceptances))

            # Collect unique regions from acceptances
            regions_to_validate = set()
            for acceptance in acceptances:
                if 'siteToSiteVpn' in acceptance and 'region' in acceptance['siteToSiteVpn']:
                    region_name = acceptance['siteToSiteVpn']['region']
                    regions_to_validate.add(region_name)

            # Validate each region
            for region_name in regions_to_validate:
                edges_summary = self.gsdk.get_edges_summary_filter(region=region_name, role='gateway', status='active')
                if not edges_summary:
                    LOG.error("_validate_gateway_requirements_for_acceptances: No active gateways found in region %s",
                              region_name)
                    raise ConfigurationError(f"No active gateways found in region {region_name}")
                else:
                    LOG.info("_validate_gateway_requirements_for_acceptances: Region %s has %s active gateways",
                             region_name, len(edges_summary))
                if len(edges_summary) < min_gateways:
                    LOG.error("_validate_gateway_requirements_for_acceptances: Region %s has only %s gateways, minimum %s required",
                              region_name, len(edges_summary), min_gateways)
                    raise ConfigurationError(f"Region {region_name} has only {len(edges_summary)} gateways,"
                                             f"minimum {min_gateways} required")
                else:
                    LOG.info("_validate_gateway_requirements_for_acceptances: Region %s meets minimum gateway requirements",
                             region_name)
                # Validate tunnel terminator connection count for each gateway
                for edge_summary in edges_summary:
                    LOG.info("_validate_gateway_requirements_for_acceptances: Validating tunnel terminator connection count for gateway %s",
                             edge_summary.hostname)
                    if hasattr(edge_summary, 'tt_conn_count') and edge_summary.tt_conn_count:
                        if edge_summary.tt_conn_count < 2:
                            LOG.error("_validate_gateway_requirements_for_acceptances: Gateway %s has only %s tunnel terminators, minimum 2 required",
                                      edge_summary.hostname, edge_summary.tt_conn_count)
                            raise ConfigurationError(f"Gateway {edge_summary.hostname} has only "
                                                     f"{edge_summary.tt_conn_count} tunnel terminators, "
                                                     f"minimum 2 required")
                    else:
                        LOG.error("_validate_gateway_requirements_for_acceptances: "
                                  "Gateway %s does not have any tunnel terminators connected, "
                                  "minimum 2 required",
                                  edge_summary.hostname)
                        raise ConfigurationError(f"Gateway {edge_summary.hostname} does not have any "
                                                 f"tunnel terminators connected, minimum 2 required")
        except Exception as e:
            LOG.warning("_validate_gateway_requirements_for_acceptances: Gateway validation failed: %s", e)
            raise
            # TODO: Don't fail the entire operation for validation issues ?

    def _validate_vpn_profiles_for_acceptances(self, acceptances):
        """
        Validate VPN profile existence for all acceptances.

        Args:
            acceptances (list): List of acceptance configurations
        """
        try:
            LOG.info("_validate_vpn_profiles_for_acceptances: Validating VPN profiles for %s acceptances",
                     len(acceptances))

            # Collect unique VPN profile names from acceptances
            vpn_profiles_to_validate = set()
            for acceptance in acceptances:
                if 'siteToSiteVpn' in acceptance:
                    site_to_site_vpn = acceptance['siteToSiteVpn']
                    if 'ipsecGatewayDetails' in site_to_site_vpn:
                        ipsec_gateway_details = site_to_site_vpn['ipsecGatewayDetails']
                        if 'vpnProfile' in ipsec_gateway_details:
                            vpn_profile_name = ipsec_gateway_details['vpnProfile']
                            if vpn_profile_name:
                                vpn_profiles_to_validate.add(vpn_profile_name)

            if not vpn_profiles_to_validate:
                LOG.info("_validate_vpn_profiles_for_acceptances: No VPN profiles found in acceptances")
                raise ConfigurationError("No VPN profiles found in acceptances")

            LOG.info("_validate_vpn_profiles_for_acceptances: Validating %s VPN profiles", len(vpn_profiles_to_validate))
            # Get all VPN profiles from portal
            portal_vpn_profiles = self.gsdk.get_global_ipsec_profiles()
            if not portal_vpn_profiles:
                LOG.error("_validate_vpn_profiles_for_acceptances: No VPN profiles found in portal")
                raise ConfigurationError("No VPN profiles found in portal")

            # Validate each VPN profile
            missing_profiles = []
            for vpn_profile_name in vpn_profiles_to_validate:
                if vpn_profile_name not in portal_vpn_profiles:
                    LOG.error("_validate_vpn_profiles_for_acceptances: VPN profile '%s' not found in portal",
                              vpn_profile_name)
                    missing_profiles.append(vpn_profile_name)
                else:
                    LOG.info("_validate_vpn_profiles_for_acceptances: VPN profile '%s' exists in portal",
                             vpn_profile_name)

            if missing_profiles:
                error_msg = (f"The following VPN profiles are not found in the portal: "
                             f"{', '.join(missing_profiles)}")
                LOG.error("_validate_vpn_profiles_for_acceptances: %s", error_msg)
                raise ConfigurationError(error_msg)

            LOG.info("_validate_vpn_profiles_for_acceptances: All VPN profiles existence validated successfully for %s acceptances",
                     len(acceptances))
        except ConfigurationError:
            raise
        except Exception as e:
            LOG.warning("_validate_vpn_profiles_for_acceptances: VPN profile validation failed: %s", e)
            raise

    def _process_multiple_acceptances(self, acceptances_config, matches_file=None, dry_run=False):
        """
        Process multiple invitation acceptances from configuration.

        Args:
            acceptances_config (list): List of acceptance configurations
            matches_file (str, optional): Path to matches responses JSON file for match ID lookup
            dry_run (bool, optional): If True, skip the actual API call (validation only). Defaults to False.

        Returns:
            dict: Combined results from all acceptances
        """
        try:
            results = []
            total_processed = 0
            total_successful = 0

            LOG.info("_process_multiple_acceptances: Processing %s invitation acceptances", len(acceptances_config))

            # Pre-fetch all sites, site_lists, regions, and LAN segments once for faster lookups
            LOG.info("_process_multiple_acceptances: Pre-fetching sites, site_lists, regions, and LAN segments")
            sites = self.gsdk.get_sites_details()
            site_lists = self.gsdk.get_global_site_lists()
            regions = self.gsdk.get_regions()
            lan_segments = self.gsdk.get_global_lan_segments()

            # Create lookup dictionaries (name -> id) for O(1) lookups
            sites_lookup = {site.name: site.id for site in sites} if sites else {}
            site_lists_lookup = {site_list.name: site_list.id for site_list in site_lists} if site_lists else {}
            regions_lookup = {region.name: region.id for region in regions} if regions else {}
            lan_segments_lookup = {segment.name: segment.id for segment in lan_segments} if lan_segments else {}

            LOG.info("_process_multiple_acceptances: Pre-fetched %s sites, %s site_lists, %s regions, and %s LAN segments",
                     len(sites_lookup), len(site_lists_lookup), len(regions_lookup), len(lan_segments_lookup))

            for i, acceptance_config in enumerate(acceptances_config):
                try:
                    LOG.info("--------------------------------")
                    LOG.info("_process_multiple_acceptances: Processing acceptance %s/%s", i + 1, len(acceptances_config))
                    LOG.info("_process_multiple_acceptances: Customer: '%s' Service: '%s'",
                             acceptance_config.get('customerName'), acceptance_config.get('serviceName'))
                    # Resolve names to IDs (returns direct API payload structure)
                    resolved_config = self._resolve_acceptance_names_to_ids(
                        acceptance_config, matches_file,
                        sites_lookup=sites_lookup,
                        site_lists_lookup=site_lists_lookup,
                        regions_lookup=regions_lookup,
                        lan_segments_lookup=lan_segments_lookup
                    )

                    # Extract service ID and match ID from resolved configuration
                    service_id = resolved_config['id']  # Service ID is 'id' in API payload
                    match_id = resolved_config['matchId']  # Match ID is 'matchId' in API payload

                    # Validate required fields in resolved configuration
                    required_fields = ['id', 'siteInformation', 'policy', 'siteToSiteVpn', 'nat']
                    for field in required_fields:
                        if field not in resolved_config or resolved_config[field] is None:
                            raise ConfigurationError(f"Missing required field '{field}' in resolved configuration")

                    # Use the resolved configuration directly as the API payload
                    acceptance_payload = resolved_config

                    LOG.info("_process_multiple_acceptances: Acceptance payload for '%s' and '%s': %s",
                             acceptance_config.get('customerName'), acceptance_config.get('serviceName'), acceptance_payload)

                    # Check for dry-run mode
                    if dry_run:
                        LOG.info("_process_multiple_acceptances: DRY-RUN - Skipping API call for '%s' and '%s' with match_id: %s and service_id: %s",
                                 acceptance_config.get('customerName'), acceptance_config.get('serviceName'), match_id, service_id)
                        result = {
                            'dry_run': True,
                            'message': 'API call skipped in dry-run mode',
                            'payload_validated': True,
                            'match_id': match_id,
                            'service_id': service_id
                        }
                    else:
                        # Call the acceptance API with match_id as path parameter
                        response = self.gsdk.accept_data_exchange_service(match_id, acceptance_payload)
                        result = response.to_dict()

                    results.append({
                        'customer_name': acceptance_config.get('customerName'),
                        'service_name': acceptance_config.get('serviceName'),
                        'result': result,
                        'status': 'success' if not dry_run else 'dry-run'
                    })
                    total_successful += 1

                except Exception as e:
                    LOG.error("_process_multiple_acceptances: Failed to process acceptance %s: %s", i + 1, e)
                    results.append({
                        'customer_name': acceptance_config.get('customerName'),
                        'service_name': acceptance_config.get('serviceName'),
                        'error': str(e),
                        'status': 'failed'
                    })

                total_processed += 1

            LOG.info("_process_multiple_acceptances: Completed %s/%s acceptances successfully",
                     total_successful, total_processed)

            return {
                'total_processed': total_processed,
                'total_successful': total_successful,
                'results': results
            }

        except Exception as e:
            LOG.error("Failed to process multiple acceptances: %s", e)
            raise ConfigurationError(f"Multiple acceptance processing failed: {e}")

    def _fill_missing_tunnel_values(self, acceptance_config, region_id, lan_segment_id):
        """
        Fill in missing tunnel configuration values using Graphiant portal APIs.

        Args:
            acceptance_config (dict): The acceptance configuration
            region_id (int): The region ID for subnet allocation
            lan_segment_id (int): The LAN segment ID for subnet allocation

        Returns:
            dict: Updated acceptance configuration with filled values
        """
        try:
            site_to_site_vpn = acceptance_config.get('siteToSiteVpn', {})
            ipsec_gateway_details = site_to_site_vpn.get('ipsecGatewayDetails', {})

            # Fill in missing tunnel1 values
            tunnel1 = ipsec_gateway_details.get('tunnel1', {})
            if 'insideIpv4Cidr' in tunnel1 and tunnel1['insideIpv4Cidr'] is None:
                ipv4_subnet = self.gsdk.get_ipsec_inside_subnet(region_id, lan_segment_id, 'ipv4')
                if ipv4_subnet:
                    tunnel1['insideIpv4Cidr'] = ipv4_subnet
                    LOG.info("_fill_missing_tunnel_values: Filled tunnel1 insideIpv4Cidr: %s", ipv4_subnet)

            if 'insideIpv6Cidr' in tunnel1 and tunnel1['insideIpv6Cidr'] is None:
                ipv6_subnet = self.gsdk.get_ipsec_inside_subnet(region_id, lan_segment_id, 'ipv6')
                if ipv6_subnet:
                    tunnel1['insideIpv6Cidr'] = ipv6_subnet
                    LOG.info("_fill_missing_tunnel_values: Filled tunnel1 insideIpv6Cidr: %s", ipv6_subnet)

            if tunnel1.get('psk') is None:
                psk = self.gsdk.get_preshared_key()
                if psk:
                    tunnel1['psk'] = psk
                    LOG.info("_fill_missing_tunnel_values: Filled tunnel1 psk")

            # Fill in missing tunnel2 values
            tunnel2 = ipsec_gateway_details.get('tunnel2', {})
            if 'insideIpv4Cidr' in tunnel2 and tunnel2['insideIpv4Cidr'] is None:
                ipv4_subnet = self.gsdk.get_ipsec_inside_subnet(region_id, lan_segment_id, 'ipv4')
                if ipv4_subnet:
                    tunnel2['insideIpv4Cidr'] = ipv4_subnet
                    LOG.info("_fill_missing_tunnel_values: Filled tunnel2 insideIpv4Cidr: %s", ipv4_subnet)

            if 'insideIpv6Cidr' in tunnel2 and tunnel2['insideIpv6Cidr'] is None:
                ipv6_subnet = self.gsdk.get_ipsec_inside_subnet(region_id, lan_segment_id, 'ipv6')
                if ipv6_subnet:
                    tunnel2['insideIpv6Cidr'] = ipv6_subnet
                    LOG.info("_fill_missing_tunnel_values: Filled tunnel2 insideIpv6Cidr: %s", ipv6_subnet)

            if tunnel2.get('psk') is None:
                psk = self.gsdk.get_preshared_key()
                if psk:
                    tunnel2['psk'] = psk
                    LOG.info("_fill_missing_tunnel_values: Filled tunnel2 psk")

            return acceptance_config

        except Exception as e:
            LOG.error("_fill_missing_tunnel_values: Error filling tunnel values: %s", e)
            return acceptance_config

    def _resolve_acceptance_names_to_ids(self, acceptance_config, matches_file=None,
                                         sites_lookup=None, site_lists_lookup=None,
                                         regions_lookup=None, lan_segments_lookup=None):
        """
        Resolve names to IDs for acceptance configuration.

        Args:
            acceptance_config (dict): Acceptance configuration with names
            matches_file (str, optional): Path to matches responses JSON file for match ID lookup
            sites_lookup (dict, optional): Pre-fetched dictionary mapping site names to IDs
            site_lists_lookup (dict, optional): Pre-fetched dictionary mapping site list names to IDs
            regions_lookup (dict, optional): Pre-fetched dictionary mapping region names to IDs
            lan_segments_lookup (dict, optional): Pre-fetched dictionary mapping LAN segment names to IDs

        Returns:
            dict: Resolved configuration with IDs
        """
        try:
            customer_name = acceptance_config.get('customerName')
            service_name = acceptance_config.get('serviceName')

            if not customer_name or not service_name:
                raise ConfigurationError("customer_name and service_name are required in acceptance configuration")

            LOG.info("_resolve_acceptance_names_to_ids: Resolving names for customer '%s' and service '%s'",
                     customer_name, service_name)

            # Get match ID and service ID from customer name and service name combination
            # This is important because a customer can be matched to multiple services
            match_data = self._get_match_id_from_customer_service(customer_name, service_name, matches_file)

            if not match_data:
                raise ConfigurationError(f"No match found for customer '{customer_name}' and service '{service_name}'")

            match_id = match_data.get('match_id')
            service_id = match_data.get('service_id')

            if not match_id or not service_id:
                raise ConfigurationError(f"Invalid match data for customer "
                                         f"'{customer_name}' and service '{service_name}'")

            # Resolve site names to IDs using pre-fetched lookup or API call
            site_names = acceptance_config.get('siteInformation', [{}])[0].get('sites', [])
            site_ids = []
            for site_name in site_names:
                if sites_lookup and site_name in sites_lookup:
                    site_id = sites_lookup[site_name]
                else:
                    site_id = self.gsdk.get_site_id(site_name)
                if site_id:
                    site_ids.append(site_id)
                else:
                    raise ConfigurationError(f"Site '{site_name}' not found")

            # Resolve site list names to IDs using pre-fetched lookup or API call
            site_list_names = acceptance_config.get('siteInformation', [{}])[0].get('siteLists', [])
            site_list_ids = []
            for site_list_name in site_list_names:
                if site_lists_lookup and site_list_name in site_lists_lookup:
                    site_list_id = site_lists_lookup[site_list_name]
                else:
                    site_list_id = self.gsdk.get_site_list_id(site_list_name)
                if site_list_id:
                    site_list_ids.append(site_list_id)
                else:
                    raise ConfigurationError(f"Site list '{site_list_name}' not found")

            # Resolve LAN segment name to ID using pre-fetched lookup or API call
            lan_segment_name = acceptance_config.get('policy', [{}])[0].get('lanSegment')
            lan_segment_id = None
            if lan_segment_name:
                if lan_segments_lookup and lan_segment_name in lan_segments_lookup:
                    lan_segment_id = lan_segments_lookup[lan_segment_name]
                else:
                    lan_segment_id = self.gsdk.get_lan_segment_id(lan_segment_name)
                if not lan_segment_id:
                    raise ConfigurationError(f"LAN segment '{lan_segment_name}' not found")

            # Resolve region name to ID using pre-fetched lookup or API call
            region_name = acceptance_config.get('siteToSiteVpn', {}).get('region')
            region_id = None
            if region_name:
                if regions_lookup and region_name in regions_lookup:
                    region_id = regions_lookup[region_name]
                else:
                    region_id = self.gsdk.get_region_id_by_name(region_name)
                if not region_id:
                    raise ConfigurationError(f"Region '{region_name}' not found")

            # Build resolved acceptance configuration in API payload format
            # Update siteToSiteVpn to include resolved regionId and emails
            site_to_site_vpn = acceptance_config.get('siteToSiteVpn', {}).copy()
            if region_id:
                site_to_site_vpn['regionId'] = region_id
            # Ensure emails are included in siteToSiteVpn
            if 'emails' in acceptance_config.get('siteToSiteVpn', {}):
                site_to_site_vpn['emails'] = acceptance_config.get('siteToSiteVpn', {}).get('emails', [])

            resolved_config = {
                'id': service_id,  # Service ID for API payload
                'siteInformation': [{
                    'sites': site_ids,
                    'siteLists': site_list_ids
                }],
                'nat': acceptance_config.get('nat', []),
                'policy': [{
                    'lanSegment': lan_segment_id,
                    'consumerPrefixes': acceptance_config.get('policy', [{}])[0].get('consumerPrefixes', [])
                }],
                'siteToSiteVpn': site_to_site_vpn,
                'globalObjectOps': acceptance_config.get('globalObjectOps', {}),
                'routingPolicyTable': acceptance_config.get('routingPolicyTable', []),
                'matchId': match_id
            }

            # Fill in missing tunnel values using Graphiant portal APIs
            resolved_config = self._fill_missing_tunnel_values(resolved_config, region_id, lan_segment_id)

            LOG.info("_resolve_acceptance_names_to_ids: Resolved service_id=%s, match_id=%s, region_id=%s",
                     service_id, match_id, region_id)
            return resolved_config

        except Exception as e:
            LOG.error("Failed to resolve names to IDs: %s", e)
            raise ConfigurationError(f"Name resolution failed: {e}")

    def _get_match_id_from_customer_service(self, customer_name, service_name, matches_file=None):
        """
        Get match ID and service ID from customer name and service name.
        Reads from the matches responses JSON file.

        Args:
            customer_name (str): Customer name
            service_name (str): Service name
            matches_file (str, optional): Path to matches responses JSON file

        Returns:
            dict: Dictionary containing match_id and service_id, or None if not found
        """
        try:
            import json
            import os

            # Use provided matches file or default
            if not matches_file:
                # Use the same path resolution logic as render_config_file
                # Use config_path for relative path resolution
                matches_file = os.path.join(
                    self.config_utils.config_path,
                    "de_workflows_configs/output/sample_data_exchange_matches_responses_latest.json"
                )
            else:
                # Apply the same path resolution logic as render_config_file for provided path
                if os.path.isabs(matches_file):
                    # Absolute path - use as is
                    pass
                else:
                    # Relative path - resolve using config_path (same as render_config_file)
                    # Security: Normalize path to prevent path traversal attacks
                    matches_file = os.path.normpath(os.path.join(self.config_utils.config_path, matches_file))
                    # Security: Validate that resolved path is within config_path to prevent path traversal
                    config_path_real = os.path.realpath(self.config_utils.config_path)
                    matches_file_real = os.path.realpath(matches_file)
                    if not matches_file_real.startswith(config_path_real):
                        raise ConfigurationError(
                            "Security: Path traversal detected. Matches file path resolves outside config directory."
                        )

            if os.path.exists(matches_file):
                LOG.info("_get_match_id_from_customer_service: Reading matches from %s", matches_file)
                with open(matches_file, 'r') as f:
                    matches_data = json.load(f)

                # Find matching customer and service
                for match in matches_data:
                    if (match.get('customer_name') == customer_name and
                            match.get('service_name') == service_name):
                        match_id = match.get('match_id')
                        service_id = match.get('service_id')
                        LOG.info("_get_match_id_from_customer_service: Found match_id %s and service_id %s for customer '%s' and service '%s'",
                                 match_id, service_id, customer_name, service_name)
                        return {
                            'match_id': match_id,
                            'service_id': service_id
                        }

                LOG.warning("_get_match_id_from_customer_service: No match found for customer '%s' and service '%s'",
                            customer_name, service_name)
                return None
            else:
                LOG.error("_get_match_id_from_customer_service: Matches file not found at %s", matches_file)
                return None

        except Exception as e:
            LOG.error("_get_match_id_from_customer_service: Error reading matches file: %s", e)
            return None

    def get_service_health(self, service_name, is_provider=False):
        """
        Get service health monitoring information.

        Args:
            service_name (str): The service name
            is_provider (bool): Whether this is a provider view

        Returns:
            dict: Service health data
        """
        try:
            LOG.info("get_service_health: Retrieving health for service %s", service_name)

            # Get service ID from service name
            service_id = self.gsdk.get_data_exchange_service_id_by_name(service_name)
            if not service_id:
                raise ConfigurationError(f"Service '{service_name}' not found")

            LOG.info("get_service_health: Found service ID %s for service '%s'", service_id, service_name)
            response = self.gsdk.get_service_health(service_id, is_provider)

            if response and hasattr(response, 'service_health'):
                health_table = []
                for health in response.service_health:
                    health_table.append([
                        health.customer_name,
                        health.overall_health,
                        health.producer_prefix_health.health,
                        health.customer_prefix_health.health
                    ])

                LOG.info("Service Health:\n%s",
                         tabulate(health_table,
                                  headers=['Customer', 'Overall', 'Producer Prefixes', 'Customer Prefixes'],
                                  tablefmt='grid'))

            return response.to_dict() if response else {}

        except Exception as e:
            LOG.error("Failed to retrieve service health: %s", e)
            raise ConfigurationError(f"Service health retrieval failed: {e}")
