"""
Emotional State System for roturbot
Manages per-server emotional states with reasons for those feelings.
"""

import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

MODULE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EMOTIONAL_STATES_FILE = os.path.join(MODULE_DIR, "store", "emotional_states.json")

# Common emotional states
EMOTIONAL_STATES = [
    "neutral", "happy", "excited", "content", "amused",
    "sad", "upset", "angry", "frustrated", "disappointed",
    "confused", "surprised", "curious", "thoughtful", "calm",
    "anxious", "nervous", "embarrassed", "proud", "grateful"
]

def load_emotional_states() -> Dict[str, Dict[str, Any]]:
    """Load all emotional states from the file."""
    if not os.path.exists(EMOTIONAL_STATES_FILE):
        save_to_file({})
        return {}
    
    try:
        with open(EMOTIONAL_STATES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"[emotional_state] Error loading emotional states: {e}")
        return {}


def save_to_file(data: Dict[str, Dict[str, Any]]) -> None:
    """Save emotional states data to file."""
    try:
        with open(EMOTIONAL_STATES_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except IOError as e:
        print(f"[emotional_state] Error saving emotional states: {e}")


def set_emotional_state(guild_id: str, state: str, reason: str) -> Dict[str, Any]:
    """
    Set emotional state for a server.
    
    Args:
        guild_id: Discord server ID (as string)
        state: The emotional state (must be one of EMOTIONAL_STATES)
        reason: The reason for this emotional state
    
    Returns:
        Dict with success status and emotional state data
    """
    # Validate state
    if state not in EMOTIONAL_STATES:
        return {
            "success": False,
            "message": f"Invalid emotional state. Must be one of: {', '.join(EMOTIONAL_STATES)}"
        }
    
    data = load_emotional_states()
    
    data[guild_id] = {
        "state": state,
        "reason": reason,
        "last_updated": datetime.now().isoformat()
    }
    
    save_to_file(data)
    
    return {
        "success": True,
        "guild_id": guild_id,
        "state": state,
        "reason": reason,
        "last_updated": data[guild_id]["last_updated"]
    }


def get_emotional_state(guild_id: str) -> Dict[str, Any]:
    """
    Get emotional state for a server.
    
    Args:
        guild_id: Discord server ID (as string)
    
    Returns:
        Dict with emotional state data or 'neutral' if not set
    """
    data = load_emotional_states()
    
    if guild_id in data:
        return data[guild_id]
    
    # Default to neutral for new servers
    return {
        "state": "neutral",
        "reason": "Default state",
        "last_updated": datetime.now().isoformat()
    }


def reset_emotional_state(guild_id: str) -> Dict[str, Any]:
    """
    Reset emotional state to neutral for a server.
    
    Args:
        guild_id: Discord server ID (as string)
    
    Returns:
        Dict with success status
    """
    data = load_emotional_states()
    
    if guild_id in data:
        del data[guild_id]
        save_to_file(data)
    
    return {
        "success": True,
        "guild_id": guild_id,
        "message": "Emotional state reset to neutral",
        "state": "neutral"
    }


def modify_emotional_state(action: str, guild_id: str, state: str = "", reason: str = "") -> Dict[str, Any]:
    """
    Modify emotional state based on action.
    
    Args:
        action: 'set' or 'reset'
        guild_id: Discord server ID (as string)
        state: The emotional state (for 'set' action)
        reason: The reason for this state (for 'set' action)
    
    Returns:
        Dict with success status and relevant data
    """
    action = action.lower()
    
    if action == "set":
        if not state or not reason:
            return {
                "success": False,
                "message": "Missing required parameters for 'set': state and reason are required"
            }
        return set_emotional_state(guild_id, state, reason)
    elif action == "reset":
        return reset_emotional_state(guild_id)
    else:
        return {
            "success": False,
            "message": f"Invalid action: {action}. Use 'set' or 'reset'."
        }


def get_formatted_emotional_state(guild_id: str) -> str:
    """
    Get formatted emotional state for inclusion in prompts.
    
    Args:
        guild_id: Discord server ID (as string)
    
    Returns:
        Formatted string with emotional state and reason
    """
    emotional_data = get_emotional_state(guild_id)
    
    state = emotional_data.get("state", "neutral")
    reason = emotional_data.get("reason", "")
    
    if state == "neutral" and reason == "Default state":
        return ""
    
    result = f"You are currently feeling {state}"
    if reason:
        result += f" because {reason}"
    
    return result


class EmotionalStateSystem:
    """Main emotional state system class."""
    
    @staticmethod
    def get_valid_states() -> List[str]:
        """Get list of valid emotional states."""
        return EMOTIONAL_STATES.copy()
    
    @staticmethod
    def set_state(guild_id: str, state: str, reason: str) -> Dict[str, Any]:
        """Set emotional state for a server."""
        return set_emotional_state(guild_id, state, reason)
    
    @staticmethod
    def get_state(guild_id: str) -> Optional[Dict[str, Any]]:
        """Get emotional state for a server."""
        return get_emotional_state(guild_id)
    
    @staticmethod
    def reset_state(guild_id: str) -> Dict[str, Any]:
        """Reset emotional state for a server."""
        return reset_emotional_state(guild_id)
    
    @staticmethod
    def modify_state(action: str, guild_id: str, state: str = "", reason: str = "") -> Dict[str, Any]:
        """Modify emotional state."""
        return modify_emotional_state(action, guild_id, state, reason)
    
    @staticmethod
    def get_formatted_state(guild_id: str) -> str:
        """Get formatted emotional state for prompts."""
        return get_formatted_emotional_state(guild_id)
    
    @staticmethod
    def get_all_states() -> Dict[str, Dict[str, Any]]:
        """Get all emotional states."""
        return load_emotional_states()


# Global instance for easy access
emotional_state_system = EmotionalStateSystem()
