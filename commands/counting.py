import json
import os
import re
import ast
import operator
import time
from typing import Dict, Optional, List
from ..helpers import rotur

counting_state = {}
COUNTING_CHANNEL_ID = "1210367658927722506"
STATE_FILE = None

def init_state_file(module_dir):
    """Initialize the state file path"""
    global STATE_FILE
    STATE_FILE = os.path.join(module_dir, "store", "counting_state.json")
    load_state()

def load_state():
    """Load counting state from file"""
    global counting_state
    if STATE_FILE and os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    counting_state = data
                else:
                    counting_state = {}
        except Exception as e:
            print(f"Error loading counting state: {e}")
            counting_state = {}
    else:
        counting_state = {}

def save_state():
    """Save counting state to file"""
    if STATE_FILE:
        try:
            os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
            with open(STATE_FILE, 'w') as f:
                json.dump(counting_state, f, indent=2)
        except Exception as e:
            print(f"Error saving counting state: {e}")

def _make_default_channel_state() -> Dict:
    return {
        "current_count": 0,
        "last_user": None,
        "total_counts": 0,
        "highest_count": 0,
    "resets": 0,
    "last_count_message_id": None,
    "last_count_value": None,
        "users": {}
    }

def get_channel_state(channel_id: str) -> Dict:
    """Get or create state for a channel"""
    if channel_id not in counting_state:
        counting_state[channel_id] = _make_default_channel_state()
    state = counting_state[channel_id]
    for k, v in _make_default_channel_state().items():
        if k not in state:
            state[k] = v
    return counting_state[channel_id]

class SafeMathEvaluator:
    """Safely evaluate mathematical expressions without using eval()"""
    
    operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }
    
    functions = {
        'abs': abs,
        'round': round,
        'min': min,
        'max': max,
        'sum': sum,
    }
    
    @classmethod
    def evaluate(cls, expression: str) -> Optional[float]:
        """Safely evaluate a mathematical expression"""
        try:
            node = ast.parse(expression, mode='eval')
            return cls._eval_node(node.body)
        except Exception:
            return None
    
    @classmethod
    def _eval_node(cls, node):
        """Recursively evaluate AST nodes"""
        if isinstance(node, ast.Num):
            return node.n
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            else:
                raise ValueError("Invalid constant type")
        elif isinstance(node, ast.BinOp):
            left = cls._eval_node(node.left)
            right = cls._eval_node(node.right)
            op = cls.operators.get(type(node.op))
            if op is None:
                raise ValueError("Unsupported operator")
            return op(left, right)
        elif isinstance(node, ast.UnaryOp):
            operand = cls._eval_node(node.operand)
            op = cls.operators.get(type(node.op))
            if op is None:
                raise ValueError("Unsupported unary operator")
            return op(operand)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
                if func_name in cls.functions:
                    func = cls.functions[func_name]
                    args = [cls._eval_node(arg) for arg in node.args]
                    return func(*args)
            raise ValueError("Unsupported function")
        elif isinstance(node, ast.List):
            return [cls._eval_node(item) for item in node.elts]
        else:
            raise ValueError("Unsupported node type")

def extract_number_from_message(content: str) -> Optional[float]:
    """Extract a number from a message, supporting both plain numbers and math expressions"""
    content = content.strip()
    
    try:
        return float(content)
    except ValueError:
        pass
    
    result = SafeMathEvaluator.evaluate(content)
    if result is not None:
        if result == int(result):
            return int(result)
        return round(result, 10)
    
    return None

def is_rotur_user(user_id: str) -> bool:
    """Check if a user has a rotur account"""
    try:
        user = rotur.get_user_by('discord_id', user_id)
        return user is not None and user.get('error') != "User not found"
    except Exception as e:
        print(f"Error checking rotur user: {e}")
        return False

def _get_or_create_user(state: Dict, user_id: str) -> Dict:
    users = state.setdefault('users', {})
    if user_id not in users:
        users[user_id] = {
            'counts': 0,
            'fails': 0,
            'wrong_attempts': 0,
            'last_seen': int(time.time())
        }
    else:
        users[user_id].setdefault('counts', 0)
        users[user_id].setdefault('fails', 0)
        users[user_id].setdefault('wrong_attempts', 0)
        users[user_id]['last_seen'] = int(time.time())
    return users[user_id]

async def handle_counting_message(message, channel):
    """Handle counting messages in the counting channel"""
    if str(channel.id) != COUNTING_CHANNEL_ID:
        return False
    
    if STATE_FILE is None:
        return False
    
    user_id = str(message.author.id)
    content = message.content.strip()
    
    state = get_channel_state(str(channel.id))

    if not is_rotur_user(user_id):
        try:
            await channel.send(
                f"❌ {message.author.mention} you need a rotur account to participate in counting! Link your account with /link"
            )
        except:
            pass  # Can't send DM
        return True
    
    number = extract_number_from_message(content)
    if number is None:
        return True
    
    expected_count = state["current_count"] + 1
    user_stats = _get_or_create_user(state, user_id)
    if number == True or number == False:
        return True;
    if number == expected_count:
        if state["last_user"] == user_id:
            try:
                await message.author.send(
                    f"❌ You can't count twice in a row! Wait for someone else to count {expected_count}."
                )
            except:
                pass
            return True
        
        state["current_count"] = int(number)
        state["last_user"] = user_id
        try:
            state['last_count_message_id'] = str(message.id)
            state['last_count_value'] = int(number)
        except:
            state['last_count_message_id'] = None
            state['last_count_value'] = None
        state["total_counts"] += 1
        user_stats['counts'] += 1
        
        if state["current_count"] > state["highest_count"]:
            state["highest_count"] = state["current_count"]
        
        save_state()
        
        if state["current_count"] % 100 == 0:
            await message.add_reaction("💯")
        elif state["current_count"] % 50 == 0:
            await message.add_reaction("🎉")
        elif state["current_count"] % 10 == 0:
            await message.add_reaction("✨")
        else:
            await message.add_reaction("✅")
        
        return True
    
    else:
        if state["last_user"] != user_id:
            old_count = state["current_count"]
            state["current_count"] = 0
            state["last_user"] = None
            state['resets'] = state.get('resets', 0) + 1
            user_stats['fails'] += 1
            save_state()
            
            reset_msg = await channel.send(
                f"💥 **Count reset!** {message.author.mention} ruined it at {old_count}! "
                f"The next number was **{expected_count}** but they said **{int(number)}**.\n"
                f"Highest count reached: **{state['highest_count']}**\n"
                f"Start again from **1**!"
            )
        else:
            user_stats['wrong_attempts'] += 1
            save_state()
            try:
                await channel.send(
                    f"❌ {message.author.mention} wrong number! The next count should be **{expected_count}**, not **{int(number)}**."
                )
            except:
                pass
        
        return True

def get_leaderboards(channel_id: str, top_n: int = 5) -> Dict[str, List]:
    """Return leaderboards for counts and fails"""
    state = get_channel_state(channel_id)
    users = state.get('users', {})
    items = [(uid, stats) for uid, stats in users.items()]
    top_counts = sorted(items, key=lambda x: x[1].get('counts', 0), reverse=True)[:top_n]
    top_fails = sorted(items, key=lambda x: x[1].get('fails', 0), reverse=True)[:top_n]
    def fmt(list_items):
        return [{'user_id': uid, 'counts': s.get('counts', 0), 'fails': s.get('fails', 0), 'wrong_attempts': s.get('wrong_attempts', 0)} for uid, s in list_items]
    return {
        'top_counters': fmt(top_counts),
        'top_failers': fmt(top_fails)
    }

def get_counting_stats(channel_id: str) -> Dict:
    """Get counting statistics for a channel"""
    state = get_channel_state(channel_id)
    leaders = get_leaderboards(channel_id)
    users = state.get('users', {})
    return {
        "current_count": state["current_count"],
        "highest_count": state["highest_count"],
        "total_counts": state["total_counts"],
        "next_number": state["current_count"] + 1,
        "unique_counters": len(users),
        "resets": state.get('resets', 0),
        "top_counters": leaders['top_counters'],
        "top_failers": leaders['top_failers']
    }
