# --- FILE: src/core/instance.py ---
"""
The identifier of the current API process (host name, process number and a random tail) for coordination via Redis.

It signs the leader of the game clock loop (key timeouts:leader, src/services/game_state.py) and the event broadcast
between processes (src/services/connection_manager.py). It is created anew at every process start.
"""

import os
import socket
import uuid

WORKER_ID: str = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
