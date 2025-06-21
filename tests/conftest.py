import pytest
import threading
import asyncio
import time
from backend.server import main as server_main

@pytest.fixture(scope="session", autouse=True)
def start_server():
    """Start the Hokm WebSocket server before any tests run."""
    thread = threading.Thread(target=lambda: asyncio.run(server_main()), daemon=True)
    thread.start()
    # Wait for server to initialize
    time.sleep(1)
    yield
