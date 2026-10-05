"""Test package bootstrap.

Runs before any test module imports the app, so runtime telemetry is written
to a throwaway file instead of the tracked data/runtime_telemetry.jsonl, and no
test can use real provider or channel credentials.
Run the suite with: python -m unittest discover -s tests -t .
"""

import atexit
import os
import shutil
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
