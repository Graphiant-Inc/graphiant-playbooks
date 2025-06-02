import yaml
from concurrent.futures import wait
from concurrent.futures.thread import ThreadPoolExecutor
from libs.logger import setup_logger
from libs.gcsdk_client import GcsdkClient
from pathlib import Path as path

LOG = setup_logger()

class PortalUtils(object):

    def __init__(self, base_url=None, username=None, password=None):
        cwd = path.cwd()
        self.config_path = str(cwd) + "/configs/"
        self.templates = str(cwd) + "/templates/"
        self.logs_path = str(cwd) + "/logs/"
        LOG.info(f"PortalUtils : templates_path : {self.config_path}")
        LOG.info(f"PortalUtils : config_templates : {self.templates}")
        LOG.info(f"PortalUtils : logs_path : {self.logs_path}")
        self.gcsdk = GcsdkClient(base_url=base_url, username=username, password=password)

    def concurrent_task_execution(self, function, config_dict):
        """
        Executes a function concurrently using ThreadPoolExecutor for each key-value in config_dict.
        The value must be a dict of kwargs to pass to the function.

        :param function: Callable function to be executed concurrently
        :param config_dict: Dict with keys as identifiers and values as kwargs for the function
        :return: Dict with keys as original keys and values as Future objects
        """
        output_dict = {}
        with ThreadPoolExecutor(max_workers=150) as executor:
            for key, value in config_dict.items():
                output_dict[key] = executor.submit(function, **value)
            self.wait_checked(list(future for future in output_dict.values()))
        return output_dict

    @staticmethod
    def wait_checked(posible_futures):
        """
        Waits for a set of futures to complete, logging errors for those that fail.

        :param possible_futures: List of futures (may include None)
        """
        futures = [item for item in posible_futures if item is not None]
        LOG.debug(f"Waiting for futures {futures} to complete")
        (_done, not_done) = wait(futures)

        if not_done:
            LOG.warning(f"{len(not_done)} futures did not finish running")

        for future in futures:
            try:
                if future:
                    future.result(timeout=0)
            except Exception as e:
                LOG.error(f"future failed: {e}")

    def update_device_bringup_status(self, device_id, status):
        """
        Update the device bringup status via GCSDK APIs.

        :param device_id: str - The ID of the device to update
        :param status: str - New status to set
        :return: Response from GCSDK
        """
        result = self.gcsdk.put_devices_bringup(device_ids=[device_id], status=status)
        return result

    def update_multiple_devices_bringup_status(self, yaml_file):
        """
        Update the multiple device bringup status concurrently via GCSDK APIs.

        :param yaml_file: Contains list of devices and expected device status
        :return: None
        """
        input_file_path = self.config_path + yaml_file
        input_dict = {}
        with open(input_file_path, "r") as file:
            config_data = yaml.safe_load(file)
            for device_name, config in config_data.items():
                device_id = self.get_device_id(device_name=device_name)
                input_dict[device_id] = {"device_id": device_id, "status": config["status"]}
            self.concurrent_task_execution(self.update_device_bringup_status, input_dict)

    def get_device_id(self, device_name):
        """
        Retrieve the device ID(s) based on the device name.

        If a single match is found, returns the device ID.
        If multiple matches are found, returns a dictionary of {hostname: device_id}.
        If no match is found, returns an empty dict.
        """
        output = self.gcsdk.get_edges_summary()
        output_dict = {}
        for device_info in output:
            if device_name in device_info.hostname:
                output_dict[device_info.hostname] = device_info.device_id
        LOG.debug(f"get_device_id : {output_dict}")
        if len(output_dict) == 1:
            for device_id in output_dict.values():
                return device_id
        return output_dict
    
    def get_enterprise_id(self):
        """
        Retrieve the enterprise ID from the first available device in the edges summary.

        Returns:
            str or None: The enterprise ID, or None if no devices are found.
        """
        output = self.gcsdk.get_edges_summary()
        if not output:
            return None
        try:
            for device_info in output:
                LOG.debug(f"get_enterprise_id : {device_info.enterprise_id}")
                return device_info.enterprise_id
        except Exception:
            return None

    def render_config_file(self, yaml_file):
        """
        Load a YAML configuration file from the config path.

        Args:
            yaml_file (str): The filename of the YAML config.

        Returns:
            dict: Parsed configuration data.

        Logs Warning:
            FileNotFoundError: If the file doesn't exist.
        """
        input_file_path = self.config_path + yaml_file
        try:
            with open(input_file_path, "r") as file:
                config_data = yaml.safe_load(file)
            return config_data
        except FileNotFoundError:
            LOG.warning(f"File not found : {input_file_path}")
    
    def get_global_routing_policy_id(self, policy_name):
        """
        Retrieve the global routing policy ID based on the policy name.

        Args:
            policy_name (str): The name of the routing policy.

        Returns:
            str or None: The ID of the routing policy if found, otherwise None.
        """
        result = self.gcsdk.post_global_summary(routing_policy_type=True)
        for key, value in result.to_dict().items():
            for config in value:
                if config['name'] == policy_name:    
                    return config['id']
        return None