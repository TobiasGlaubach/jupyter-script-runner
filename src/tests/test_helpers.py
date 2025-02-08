import os, inspect, sys
current_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parent_dir = os.path.dirname(current_dir)
if __name__ == '__main__':
    # print(parent_dir)
    sys.path.insert(0, parent_dir)

import pytest
from unittest.mock import patch
from JupyRunner.core.helpers import get_db_url, get_jupyter_url


mock_config = {
        'globals': {
            'dbserver_uri': 'http://test.com:7990',
            'default_port_db': '7990',
            'default_port_jupyter': '7991'
        }
    }

def test_get_db_url():
    with patch('JupyRunner.core.helpers.get_primary_ip', return_value='test.com'):
        assert get_db_url(with_port=True, with_http=True, use_cache=True, config=mock_config) == 'http://test.com:7990'
        assert get_db_url(with_port=False, with_http=True, use_cache=True, config=mock_config) == 'http://test.com'
        assert get_db_url(with_port=True, with_http=False, use_cache=True, config=mock_config) == 'test.com:7990'
        assert get_db_url(with_port=False, with_http=False, use_cache=True, config=mock_config) == 'test.com'

def test_get_jupyter_url():
    with patch('JupyRunner.core.helpers.get_primary_ip', return_value='test.com'):
        assert get_jupyter_url(use_cache=True, config=mock_config) == 'http://test.com:7991/lab?'

if __name__ == '__main__':
    pytest.main([__file__])
    # print(get_db_url(config=mock_config))
