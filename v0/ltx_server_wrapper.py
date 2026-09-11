#!/usr/bin/env python3
"""Start the installed LTX Desktop backend with a longer embedding timeout."""

import runpy
import os
import sys
from pathlib import Path


BACKEND_ROOT = Path("/Applications/LTX Desktop.app/Contents/Resources/backend")
APP_DATA_ROOT = Path.home() / "Library" / "Application Support" / "LTXDesktop"
os.environ.setdefault("LTX_APP_DATA_DIR", str(APP_DATA_ROOT))
sys.path.insert(0, str(BACKEND_ROOT))

from services.http_client.http_client_impl import HTTPClientImpl  # noqa: E402


_original_post = HTTPClientImpl.post


def _post_with_embedding_headroom(
    self, url, headers=None, json_payload=None, data=None, timeout=30
):
    if url.endswith("/v1/prompt-embedding"):
        timeout = max(timeout, 180)
    return _original_post(
        self,
        url,
        headers=headers,
        json_payload=json_payload,
        data=data,
        timeout=timeout,
    )


HTTPClientImpl.post = _post_with_embedding_headroom
runpy.run_path(str(BACKEND_ROOT / "ltx2_server.py"), run_name="__main__")
