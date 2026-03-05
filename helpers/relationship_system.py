"""
Relationship Tracking System for roturbot
Manages roturbot's thoughts and feelings about specific rotur users.
"""

import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

MODULE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELATIONSHIPS_FILE = os.path.join(MODULE_DIR, "store", "relationships.json")


def load_relationships() -> Dict[str, Dict[str, Any]]:
    """Load all relationships from the relationships file."""
    if not os.path.exists(RELATIONSHIPS_FILE):
        save_to_file({})
        return {}
    
    try:
        with open(RELATIONSHIPS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"[relationship_system] Error loading relationships: {e}")
        return {}


def save_to_file(data: Dict[str, Dict[str, Any]]) -> None:
    """Save relationships data to file."""
    try:
        with open(RELATIONSHIPS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except IOError as e:
        print(f"[relationship_system] Error saving relationships: {e}")


def set_thoughts(user_id: str, username: str, thoughts: str) -> Dict[str, Any]:
    """
    Set roturbot's thoughts about a specific user.
    
    Args:
        user_id: Discord ID of the user
        username: rotur username of the user
        thoughts: roturbot's thoughts/feelings about this user
    
    Returns:
        Dict with success status and updated relationship data
    """
    data = load_relationships()
    
    data[user_id] = {
        "username": username,
        "thoughts": thoughts,
        "last_updated": datetime.now().isoformat()
    }
    
    save_to_file(data)
    
    return {
        "success": True,
        "user_id": user_id,
        "username": username,
        "thoughts": thoughts,
        "last_updated": data[user_id]["last_updated"]
    }


def get_thoughts(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Get roturbot's thoughts about a specific user.
    
    Args:
        user_id: Discord ID of the user
    
    Returns:
        Dict with thoughts data or None if not found
    """
    data = load_relationships()
    return data.get(user_id)


def append_thoughts(user_id: str, username: str, additional_thoughts: str) -> Dict[str, Any]:
    """
    Add additional thoughts to existing thoughts about a user.
    
    Args:
        user_id: Discord ID of the user
        username: rotur username of the user
        additional_thoughts: New thoughts to add
    
    Returns:
        Dict with success status and updated relationship data
    """
    data = load_relationships()
    
    existing = data.get(user_id, {})
    current_thoughts = existing.get("thoughts", "")
    
    # Combine existing and new thoughts
    if current_thoughts:
        combined = f"{current_thoughts}\n\n{additional_thoughts}"
    else:
        combined = additional_thoughts
    
    data[user_id] = {
        "username": username,
        "thoughts": combined,
        "last_updated": datetime.now().isoformat()
    }
    
    save_to_file(data)
    
    return {
        "success": True,
        "user_id": user_id,
        "username": username,
        "thoughts": combined,
        "last_updated": data[user_id]["last_updated"]
    }


def remove_thoughts(user_id: str) -> Dict[str, Any]:
    """
    Remove thoughts about a user.
    
    Args:
        user_id: Discord ID of the user
    
    Returns:
        Dict with success status
    """
    data = load_relationships()
    
    if user_id in data:
        removed = data.pop(user_id)
        save_to_file(data)
        return {
            "success": True,
            "user_id": user_id,
            "message": "Thoughts removed successfully",
            "removed_data": removed
        }
    else:
        return {
            "success": False,
            "user_id": user_id,
            "message": "No thoughts found for this user"
        }


def modify_relationship(action: str, user_id: str, username: str, thoughts: str) -> Dict[str, Any]:
    """
    Modify relationship thoughts based on action.
    
    Args:
        action: 'set', 'append', or 'remove'
        user_id: Discord ID of the user
        username: rotur username of the user
        thoughts: Thoughts to set/append (not used for 'remove')
    
    Returns:
        Dict with success status and relevant data
    """
    action = action.lower()
    
    if action == "set":
        return set_thoughts(user_id, username, thoughts)
    elif action == "append":
        return append_thoughts(user_id, username, thoughts)
    elif action == "remove":
        return remove_thoughts(user_id)
    else:
        return {
            "success": False,
            "message": f"Invalid action: {action}. Use 'set', 'append', or 'remove'."
        }


def get_formatted_thoughts_for_user(user_id: str) -> str:
    """
    Get formatted thoughts about a user for inclusion in prompts.
    
    Args:
        user_id: Discord ID of the user
    
    Returns:
        Formatted string with thoughts, or empty string if none exist
    """
    relationship = get_thoughts(user_id)
    
    if not relationship or not relationship.get("thoughts"):
        return ""
    
    return f"My thoughts on this person are: {relationship['thoughts']}"


class RelationshipSystem:
    """Main relationship system class."""
    
    @staticmethod
    def set_thoughts(user_id: str, username: str, thoughts: str) -> Dict[str, Any]:
        """Set thoughts about a user."""
        return set_thoughts(user_id, username, thoughts)
    
    @staticmethod
    def get_thoughts(user_id: str) -> Optional[Dict[str, Any]]:
        """Get thoughts about a user."""
        return get_thoughts(user_id)
    
    @staticmethod
    def append_thoughts(user_id: str, username: str, additional_thoughts: str) -> Dict[str, Any]:
        """Add additional thoughts about a user."""
        return append_thoughts(user_id, username, additional_thoughts)
    
    @staticmethod
    def remove_thoughts(user_id: str) -> Dict[str, Any]:
        """Remove thoughts about a user."""
        return remove_thoughts(user_id)
    
    @staticmethod
    def modify_relationship(action: str, user_id: str, username: str, thoughts: str) -> Dict[str, Any]:
        """Modify relationship thoughts."""
        return modify_relationship(action, user_id, username, thoughts)
    
    @staticmethod
    def get_formatted_thoughts(user_id: str) -> str:
        """Get formatted thoughts for prompts."""
        return get_formatted_thoughts_for_user(user_id)
    
    @staticmethod
    def get_all_relationships() -> Dict[str, Dict[str, Any]]:
        """Get all relationships."""
        return load_relationships()


# Global instance for easy access
relationship_system = RelationshipSystem()
