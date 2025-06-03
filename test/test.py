import configparser
import unittest
from libs.edge import Edge
from libs.logger import setup_logger

LOG = setup_logger()

def read_config():
    config = configparser.ConfigParser()
    config.read('test/test.ini')
    username = config['credentials']['username']
    password = config['credentials']['password']
    host = config['host']['url']
    return host, username, password

class TestGraphiantPlaybooks(unittest.TestCase):

    def test_get_enterprise_id(self):
        base_url, username, password = read_config()
        edge = Edge(base_url=base_url, username=username, password=password)
        try:
            enterprise_id = edge.get_enterprise_id()
            LOG.info(f"Enterprise ID: {enterprise_id}")
        except Exception as e:
            self.fail(f"test_get_enterprise_id failed with exception: {e}")

if __name__ == '__main__':
    unittest.main()
