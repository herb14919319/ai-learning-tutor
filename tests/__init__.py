"""Test package bootstrap.

Runs before any test module imports the app, so runtime telemetry is written
to a throwaway file instead of the tracked data/runtime_telemetry.jsonl, and no
test can use real provider or channel credentials.
Run the suite with: python -m unittest discover -s tests -t .
"""

import atexit
import os
import shutil
import socket
import sys
import tempfile


_TELEMETRY_DIR = tempfile.mkdtemp(prefix="ai-tutor-test-telemetry-")
os.environ["RUNTIME_TELEMETRY_PATH"] = os.path.join(_TELEMETRY_DIR, "runtime_telemetry.jsonl")
atexit.register(shutil.rmtree, _TELEMETRY_DIR, ignore_errors=True)

# Never reach a real model provider, Meta or LINE from tests. main.load_dotenv()
# does not override variables that are already set, so blanking them here keeps
# local .env credentials out of the suite. Tests that need a key patch it in.
for _name in (
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "DEEPSEEK_API_KEY",
    "MESSENGER_PAGE_ACCESS_TOKEN",
    "LINE_CHANNEL_ACCESS_TOKEN",
):
    os.environ[_name] = ""

# Fixed fake webhook secrets: tests can sign requests, real secrets never load.
os.environ["LINE_CHANNEL_SECRET"] = "test-line-channel-secret"
os.environ["MESSENGER_APP_SECRET"] = "test-messenger-app-secret"
os.environ["MESSENGER_VERIFY_TOKEN"] = "test-messenger-verify-token"


# Network guard: any connection or DNS lookup to a non-local host fails the
# calling test instead of reaching a real provider, LINE, Messenger or Meta.
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_real_connect = socket.socket.connect
_real_getaddrinfo = socket.getaddrinfo


BLOCKED_NETWORK_ATTEMPTS: list[str] = []


class ExternalNetworkBlocked(RuntimeError):
    pass


def _block(description):
    # Recorded as well as raised: production code may swallow the exception.
    BLOCKED_NETWORK_ATTEMPTS.append(description)
    raise ExternalNetworkBlocked(f"test attempted {description}")


def _host_of(address):
    return address[0] if isinstance(address, tuple) else address


def _guarded_connect(sock, address):
    if sock.family == socket.AF_UNIX or _host_of(address) in _LOCAL_HOSTS:
        return _real_connect(sock, address)
    _block(f"external connection to {_host_of(address)!r}")


def _guarded_getaddrinfo(host, *args, **kwargs):
    if host in _LOCAL_HOSTS or host is None:
        return _real_getaddrinfo(host, *args, **kwargs)
    _block(f"external DNS lookup for {host!r}")


def _report_blocked_attempts():
    if BLOCKED_NETWORK_ATTEMPTS:
        print(f"BLOCKED EXTERNAL NETWORK ATTEMPTS: {BLOCKED_NETWORK_ATTEMPTS}", file=sys.stderr)


socket.socket.connect = _guarded_connect
socket.getaddrinfo = _guarded_getaddrinfo
atexit.register(_report_blocked_attempts)
