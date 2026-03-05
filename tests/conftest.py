import sys
import os
from unittest.mock import patch, MagicMock

import pytest

# Add the project root to sys.path so tests can import the app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Prevent the background watch thread from starting when app is imported.
# Without this the watch_loop would spin up and try to scan /Books_in etc.
with patch('threading.Thread', return_value=MagicMock()):
    import app as flask_app


@pytest.fixture
def client():
    flask_app.app.config['TESTING'] = True
    with flask_app.app.test_client() as c:
        yield c
