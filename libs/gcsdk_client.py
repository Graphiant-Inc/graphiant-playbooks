import graphiant_sdk
import json
from libs.poller import poller
import time
from libs.logger import setup_logger

LOG = setup_logger()

class GcsdkClient():

    def __init__(self, base_url=None, username=None, password=None):
        self.graphiant_sdk = graphiant_sdk
        self.config = self.graphiant_sdk.Configuration()
        self.config.host = base_url
        self.config.username = username
        self.config.password = password
        self.api = self.graphiant_sdk.DefaultApi(graphiant_sdk.ApiClient(self.config))
        auth_login_body = self.graphiant_sdk.AuthLoginBody(username=self.config.username,
                                                           password=self.config.password)
        response = self.api.v1_auth_login_post(body=auth_login_body, _preload_content=False)
        self.token = json.loads(response.data).get("token")
        self.bearer_token = 'Bearer ' + self.token
        LOG.debug(f"GCSDKClient : {self.bearer_token}")

    def get_all_enterprises(self):
        """
        Get all enterprises on GCS.

        Returns:
            list: A list of enterprise information if successful, otherwise an empty list.
        """
        enterprises = self.api.v1_enterprises_get(authorization=self.bearer_token)
        LOG.debug(f"get_all_enterprises : {enterprises}")
        return enterprises

    def get_edges_summary(self, device_id=None):
        """
        Get all edges summary from GCS.

        Args:
            device_id (int, optional): The device ID to filter edges. 
            If not provided, returns all edges.

        Returns:
            list or dict: A list of all edges info if no device_id is provided, 
            or a single edge's information if a device_id is provided.
        """
        response = self.api.v1_edges_summary_get(authorization=self.bearer_token)
        if device_id:
            for edge_info in response.edges_summary:
                if edge_info.device_id == str(device_id):
                    return edge_info
        return response.edges_summary

    @poller(retries=12, wait=10)
    def put_device_config(self, device_id: int, core=None, edge=None):
        """
        Put Devices Config on GCS for Core or Edge

        Args:
            device_id (int): The device ID to push the config.
            core (dict, optional): Core configuration data.
            edge (dict, optional): Edge configuration data.

        Returns:
            response: The response from the API call to push the device config.

        Raises:
            AssertionError: If the device portal status is not 'Ready' after retries
            ApiException/AssertionError: If there is an API exception during the 
            config push after retries
        """
        body = graphiant_sdk.DeviceIdConfigBody(core=core, edge=edge)
        try:
            edge_summary = self.get_edges_summary(device_id=device_id)
            if edge_summary.portal_status == "Ready":
                LOG.info(f"put_device_config : config to be pushed for {device_id}: \n{body}")
                response = \
                self.api.v1_devices_device_id_config_put(authorization=self.bearer_token, 
                                                         device_id=device_id, body=body)
                return response
            else:
                LOG.info(f"put_device_config : Retrying,  {device_id} \
                         Portal Status: {edge_summary.portal_status} (Expected Ready)")
                assert False, f"put_device_config : Retrying,  {device_id} \
                    Portal Status: {edge_summary.portal_status} (Expected Ready)"
        except self.graphiant_sdk.rest.ApiException as e:
            LOG.warning(f"put_device_config : Exception While config push {e}")
            assert False, f"put_device_config : \
                Retrying, Exception while config push to {device_id}"
    
    def post_devices_bringup(self, device_ids):
        """
        Post Devices Bringup On GCS

        Args:
            device_ids (list): List of device IDs to bring up.

        Returns:
            response: The response from the API call to bring up the devices.
        """
        data = {'deviceIds': device_ids}
        LOG.debug(f"post_devices_bringup : {data}")
        response = self.api.v1_devices_bringup_post(authorization=self.bearer_token, body=data)
        return response

    def put_devices_bringup(self, device_ids, status):
        """
        Update the bringup status of the devices specified by their device IDs.

        Args:
            device_ids (list): A list of device IDs whose status needs to be updated.
            status (str): The desired status to be set for the devices:
                        - 'allowed', 'active', 'activate' → 'Allowed'
                        - 'denied', 'deactivate' → 'Denied'
                        - 'removed', 'decommission' → 'Removed'
                        - 'pending', 'staging', 'stage' → 'Pending'
                        - 'maintenance' → 'Maintenance'

        Returns:
            bool: True if the status update was successful, False if ApiException occurs.
        """
        data = {'deviceIds': device_ids, 'status': ''}
        data['status'] = status
        if status.lower() in ['allowed', 'active', 'activate']:
            data['status'] = 'Allowed'
        if status.lower() == ['denied', 'deactivate']:
            data['status'] = 'Denied'
        if status.lower() == ['removed', 'decommission']:
            data['status'] = 'Removed'
        if status.lower() in ['pending', 'staging', 'stage']:
            data['status'] = 'Pending'
        if status.lower() == 'maintenance':
            data['status'] = 'Maintenance'
        try:
            LOG.debug(f"put_devices_bringup : {data}")
            self.api.v1_devices_bringup_put(authorization=self.bearer_token, body=data)
            time.sleep(15)
            return True
        except self.graphiant_sdk.rest.ApiException:
            return False

    @poller(retries=12, wait=10)
    def patch_global_config(self, **kwargs):
        """
        Patch the global configuration on the system.

        Args:
            **kwargs: The global configuration parameters to be patched. 

        Returns:
            The response from the API

        Raises:
            ApiException: If the API call fails.

        """
        body = graphiant_sdk.GlobalConfigBody(**kwargs)
        try:
            LOG.info(f"patch_global_config : config to be pushed : \n{body}")
            response = self.api.v1_global_config_patch(authorization=self.bearer_token, body=body)
            return response
        except self.graphiant_sdk.rest.ApiException as e:
            LOG.warning(f"patch_global_config : Exception While Global config patch {e}")
            assert False, "patch_global_config : Retrying, Exception while Global config patch"
    
    @poller(retries=12, wait=10)
    def post_global_summary(self, **kwargs):
        """
        Posts global summary configuration to the system.
        Args:
            **kwargs: The global summary configuration parameters to be posted. 

        Returns:
            The response from the API

        Raises:
            ApiException: If the API call fails.
        """
        body = graphiant_sdk.GlobalSummaryBody(**kwargs)
        try:
            LOG.info(f"patch_global_config : config to be pushed : \n{body}")
            response = self.api.v1_global_summary_post(authorization=self.bearer_token, body=body)
            return response
        except self.graphiant_sdk.rest.ApiException as e:
            LOG.warning(f"patch_global_config : Exception While Global config patch {e}")
            assert False, "patch_global_config : Retrying, Exception while Global config patch"
