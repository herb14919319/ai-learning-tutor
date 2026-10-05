"""Test package bootstrap.

Runs before any test module imports the app, so runtime telemetry is written
to a throwaway file instead of the tracked data/runtime_telemetry.jsonl.
Run the suite with: python -m unittest discover -s tests -t .
"""

import atexit
import os
import shutil
import tempfile


_TELEMETRY_DIR = tempfile.mkdtemp(prefix="ai-tutor-test-telemetry-")
os.environ["RUNTIME_TELEMETRY_PATH"] = os.path.join(_TELEMETRY_DIR, "runtime_telemetry.jsonl")
atexit.register(shutil.rmtree, _TELEMETRY_DIR, ignore_errors=True)
