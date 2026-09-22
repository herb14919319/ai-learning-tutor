import os


DEFAULT_META_API_VERSION = "v20.0"


def get_meta_api_version() -> str:
    return os.getenv("MESSENGER_API_VERSION", DEFAULT_META_API_VERSION).strip()
