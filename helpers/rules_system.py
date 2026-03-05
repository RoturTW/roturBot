"""
Rules System for roturbot
Manages self-modifying rules that govern the bot's behavior.
"""

import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

MODULE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES_FILE = os.path.join(MODULE_DIR, "store", "bot_rules.json")

DEFAULT_RULES = [
    "Always provide accurate and helpful responses to user queries",
    "Use clear and concise language when communicating",
    "Be respectful and considerate in all interactions",
    "Research thoroughly before answering if you don't know something",
    "Acknowledge when you're uncertain or don't have enough information"
]


def load_rules() -> List[str]:
    """Load the bot's rules from the rules file."""
    if not os.path.exists(RULES_FILE):
        save_rules(DEFAULT_RULES)
        return DEFAULT_RULES.copy()
    
    try:
        with open(RULES_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            rules = data.get('rules', [])
            if not rules:
                return DEFAULT_RULES.copy()
            return rules
    except (json.JSONDecodeError, IOError) as e:
        print(f"[rules_system] Error loading rules: {e}")
        return DEFAULT_RULES.copy()


def save_rules(rules: List[str]) -> None:
    """Save the bot's rules to the rules file."""
    try:
        data = {
            'rules': rules,
            'last_updated': datetime.now().isoformat()
        }
        with open(RULES_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except IOError as e:
        print(f"[rules_system] Error saving rules: {e}")


def get_rules_as_bullet_points() -> str:
    """Return rules formatted as bullet points for inclusion in prompts."""
    rules = load_rules()
    return "\n".join(f"• {rule}" for rule in rules)


def apply_modifications(modifications: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Apply a list of modifications to the rules.
    
    Args:
        modifications: List of modifications, each with 'action' and relevant data:
            - {'action': 'add', 'rule': 'new rule text'}
            - {'action': 'remove', 'rule': 'existing rule text'}
            - {'action': 'update', 'old_rule': 'old text', 'new_rule': 'new text'}
    
    Returns:
        Dict with 'success' bool, 'message' str, and 'result' list of rules
    """
    current_rules = load_rules()
    results = []
    
    for mod in modifications:
        action = mod.get('action', '').lower()
        
        if action == 'add':
            rule = mod.get('rule', '')
            if rule and rule not in current_rules:
                current_rules.append(rule)
                results.append(f"Added: {rule}")
            elif rule in current_rules:
                results.append(f"Already exists: {rule}")
            else:
                results.append(f"Skipped adding empty rule")
        
        elif action == 'remove':
            rule = mod.get('rule', '')
            if rule in current_rules:
                current_rules.remove(rule)
                results.append(f"Removed: {rule}")
            else:
                results.append(f"Not found: {rule}")
        
        elif action == 'update':
            old_rule = mod.get('old_rule', '')
            new_rule = mod.get('new_rule', '')
            
            if old_rule in current_rules:
                index = current_rules.index(old_rule)
                current_rules[index] = new_rule
                results.append(f"Updated: '{old_rule}' → '{new_rule}'")
            else:
                results.append(f"Not found to update: {old_rule}")
        
        else:
            results.append(f"Unknown action: {action}")
    
    save_rules(current_rules)
    
    return {
        'success': True,
        'message': "\n".join(results),
        'result': current_rules
    }


class RulesSystem:
    """Main rules system class."""
    
    @staticmethod
    def get_rules() -> List[str]:
        """Get current rules."""
        return load_rules()

    @staticmethod
    def get_rules_as_bullet_points() -> str:
        """Return rules formatted as bullet points for inclusion in prompts."""
        rules = load_rules()
        return "\n".join(f"• {rule}" for rule in rules)
    
    @staticmethod
    def add_rule(rule: str) -> List[str]:
        """Add a new rule."""
        rules = load_rules()
        if rule and rule not in rules:
            rules.append(rule)
            save_rules(rules)
        return rules
    
    @staticmethod
    def remove_rule(rule: str) -> List[str]:
        """Remove a rule by text."""
        rules = load_rules()
        if rule in rules:
            rules.remove(rule)
            save_rules(rules)
        return rules
    
    @staticmethod
    def update_rule(old_rule: str, new_rule: str) -> List[str]:
        """Update an existing rule."""
        rules = load_rules()
        if old_rule in rules:
            index = rules.index(old_rule)
            rules[index] = new_rule
            save_rules(rules)
        return rules
    
    @staticmethod
    def apply_modifications(modifications: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Apply multiple modifications at once."""
        return apply_modifications(modifications)


# Global instance for easy access
rules_system = RulesSystem()
