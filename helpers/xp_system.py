"""
XP and Leveling System for roturbot
This module handles all XP tracking, level calculations, and related functionality.
"""

import os
import json
import math

_MODULE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_user_xp_data():
    """Load user XP data from the store"""
    try:
        with open(os.path.join(_MODULE_DIR, "store", "user_xp.json"), "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_user_xp_data(data):
    """Save user XP data to the store"""
    with open(os.path.join(_MODULE_DIR, "store", "user_xp.json"), "w") as f:
        json.dump(data, f, indent=2)

def calculate_level(xp):
    """Calculate level from total XP"""
    return math.floor(math.sqrt(xp / 100))

def calculate_xp_for_level(level):
    """Calculate XP required for a given level"""
    return level * level * 100

def get_user_xp_stats(discord_id):
    """Get XP statistics for a user"""
    data = load_user_xp_data()
    user_id = str(discord_id)
    
    if user_id not in data:
        return {"xp": 0, "level": 0, "total_messages": 0, "last_xp_time": 0}
    
    return data[user_id]

def award_xp(discord_id, xp_amount=15):
    """
    Award XP to a user
    Returns None if on cooldown, or (old_level, new_level, new_xp, total_messages) if XP was awarded
    """
    from datetime import datetime, timezone
    
    data = load_user_xp_data()
    user_id = str(discord_id)
    
    if user_id not in data:
        data[user_id] = {"xp": 0, "level": 0, "total_messages": 0, "last_xp_time": 0}
    
    current_time = datetime.now(timezone.utc).timestamp()
    if current_time - data[user_id].get("last_xp_time", 0) < 20:
        data[user_id]["total_messages"] = data[user_id].get("total_messages", 0) + 1
        save_user_xp_data(data)
        return None
    
    old_xp = data[user_id].get("xp", 0)
    old_level = calculate_level(old_xp)
    
    new_xp = old_xp + xp_amount
    new_level = calculate_level(new_xp)
    
    data[user_id]["xp"] = new_xp
    data[user_id]["level"] = new_level
    data[user_id]["total_messages"] = data[user_id].get("total_messages", 0) + 1
    data[user_id]["last_xp_time"] = current_time
    
    save_user_xp_data(data)
    
    return (old_level, new_level, new_xp, data[user_id]["total_messages"])

def load_levelup_message_optouts():
    """Load list of users who opted out of level-up messages"""
    try:
        with open(os.path.join(_MODULE_DIR, "store", "levelup_message_optouts.json"), "r") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_levelup_message_optouts(optouts):
    """Save list of users who opted out of level-up messages"""
    with open(os.path.join(_MODULE_DIR, "store", "levelup_message_optouts.json"), "w") as f:
        json.dump(optouts, f)

def toggle_levelup_message(user_id) -> bool:
    """
    Toggle a user's level-up message preference
    Returns True if messages are now enabled, False if disabled
    """
    uid = str(user_id)
    optouts = load_levelup_message_optouts()
    if uid in optouts:
        optouts.remove(uid)
        save_levelup_message_optouts(optouts)
        return True
    optouts.append(uid)
    save_levelup_message_optouts(optouts)
    return False

def is_levelup_message_enabled(user_id: int) -> bool:
    """Check if a user has level-up messages enabled"""
    return str(user_id) not in load_levelup_message_optouts()
