"""Fixtures for the browser tests: the real app, served on a free port."""

import threading

import pytest
from werkzeug.serving import make_server

from app import create_app


@pytest.fixture(scope="session")
def base_url():
    """Start the app with the real ledger.json and give the browser its address."""
    server = make_server("127.0.0.1", 0, create_app())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    thread.join()
