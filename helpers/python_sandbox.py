import subprocess
import json
import tempfile
import os
import sys

WORKER = os.path.abspath("sandbox_worker.py")


def run_sandbox(code: str, timeout: float = 3.0) -> dict:
    p = subprocess.Popen(
        [
            sys.executable,
            "-I",   # isolated
            "-S",   # no site
            "-E",   # ignore env vars
            WORKER
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    try:
        out, err = p.communicate(code, timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        return {
            "success": False,
            "error": "timeout",
            "result": None
        }

    if p.returncode != 0:
        return {
            "success": False,
            "error": err.strip() or "sandbox crashed",
            "result": None
        }

    try:
        return json.loads(out)
    except Exception:
        return {
            "success": False,
            "error": "invalid sandbox response",
            "raw": out
        }