import os
import json
from typing import Dict, Any


_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STORE_DIR = os.path.join(_BASE_DIR, "store")
_REACTION_FILE = os.path.join(_STORE_DIR, "reaction_stats.json")


def _ensure_store_dir():
    os.makedirs(_STORE_DIR, exist_ok=True)

def load_reaction_stats() -> Dict[str, Any]:
    """Load reaction stats from the store directory.

    Returns an object mapping message links to {"tick": int, "x": int}.
    If the file is missing or malformed, returns an empty dict.
    """
    _ensure_store_dir()
    path = _REACTION_FILE
    try:
        with open(path, "r") as f:
            return json.load(f) or {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_reaction_stats(stats: Dict[str, Any]) -> None:
    """Persist reaction stats to the canonical reaction_stats.json file."""
    _ensure_store_dir()
    with open(_REACTION_FILE, "w") as f:
        json.dump(stats, f)
