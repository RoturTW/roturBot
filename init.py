import discord
from discord import app_commands, ui
from dotenv import load_dotenv
from .commands import stats, roturacc, counting, group
from .helpers import rotur
from .helpers.quote_generator import quote_generator
from .helpers import icn
from .helpers.icon_cache import IconCache

from .shared import allowed_everywhere, send_message, catify, catmaid_mode

XP_SYSTEM_ENABLED = False

if XP_SYSTEM_ENABLED:
    from .helpers import xp_system
else:
    xp_system = None
import requests, json, os, random, string, re, sys
import aiohttp
from io import BytesIO
import asyncio, psutil, threading

from .helpers import reactionStorage
from .helpers.memory_system import MemorySystem
from .helpers.python_sandbox import run_sandbox

from sympy import sympify
import base64, hashlib, subprocess
from datetime import datetime, timezone, timedelta
from openai import AsyncOpenAI

# logging.basicConfig(level=logging.DEBUG)

# Status sync rate limiting
status_sync_cache = {}  # {user_id: {'last_status': str, 'last_sync': timestamp}}
STATUS_SYNC_COOLDOWN = 5  # seconds between syncs for the same user

def randomString(length):
    """Generate a random string of specified length"""
    letters = string.ascii_lowercase + string.digits
    return ''.join(random.choice(letters) for i in range(length))

load_dotenv()

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_MODULE_DIR)

mistium = str(os.getenv('MISTIUM_ID'))
originOS = str(os.getenv('ORIGIN_SERVER_ID'))
tavily_token = str(os.getenv('TAVILY'))
nvidia_token = str(os.getenv('NVIDIA_API_KEY'))
avatars_api_base = str(os.getenv('AVATARS_BASE_URL', 'https://avatars.rotur.dev'))
BOT_OWNER_ID = int(os.getenv('BOT_OWNER_ID', 603952506330021898))

tools = open(os.path.join(_MODULE_DIR, "static", "tools.json"), "r")
tools = json.load(tools)

with open(os.path.join(_MODULE_DIR, "static", "history.json"), "r") as history_file:
    history = json.load(history_file)

import textwrap

PERSONALITIES_DIR = os.path.join(_MODULE_DIR, "personalities")

CHANNEL_MESSAGE_CACHE: dict[int, list[dict]] = {}
MAX_CACHE_SIZE = 40

class MessageCache:
    """Runtime cache for recent messages per channel."""
    
    _lock = threading.Lock()
    
    @staticmethod
    async def add_message(message: discord.Message):
        """Add a message to the cache."""
        with MessageCache._lock:
            channel_id = message.channel.id
            channel_cache = CHANNEL_MESSAGE_CACHE.get(channel_id, [])

            reactions = []
            for reaction in message.reactions:
                users = []
                async for user in reaction.users():
                    users.append({"id": str(user.id), "name": user.name})
                reactions.append({
                    "emoji": str(reaction.emoji),
                    "count": reaction.count,
                    "users": users
                })

            msg_dict = {
                "id": message.id,
                "author": message.author.name,
                "author_id": str(message.author.id),
                "author_is_bot": message.author.bot,
                "content": message.content,
                "timestamp": message.created_at.isoformat(),
                "reactions": reactions,
            }

            channel_cache.append(msg_dict)

            if len(channel_cache) > MAX_CACHE_SIZE:
                channel_cache[:] = channel_cache[-MAX_CACHE_SIZE:]

            CHANNEL_MESSAGE_CACHE[channel_id] = channel_cache
    
    @staticmethod
    def get_recent_messages(channel_id: int, limit: int = 40) -> list[dict]:
        """Get recent messages from cache."""
        messages = CHANNEL_MESSAGE_CACHE.get(channel_id, [])
        return messages[-limit:]
    
    @staticmethod
    def get_message_by_id(channel_id: int, message_id: int) -> dict | None:
        """Get a specific message by its ID from cache."""
        messages = CHANNEL_MESSAGE_CACHE.get(channel_id, [])
        for msg in messages:
            if msg["id"] == message_id:
                return msg
        return None
    
    @staticmethod
    def get_message_history(channel_id: int) -> str:
        """Format recent messages as context string with message IDs, discord IDs, and reactions."""
        messages = CHANNEL_MESSAGE_CACHE.get(channel_id, [])
        if not messages:
            return ""

        history_lines = []
        for msg in messages[-40:]:
            author_id = msg.get('author_id', 'unknown')
            base = f"[msg_id:{msg['id']}] {msg['author']} (discord_id:{author_id}): {msg['content']}"

            reactions = msg.get('reactions', [])
            if reactions:
                reaction_strs = []
                for r in reactions:
                    emoji = r['emoji']
                    count = r['count']
                    reaction_strs.append(f"{emoji}({count})")
                base += f" {', '.join(reaction_strs)}"

            history_lines.append(base)

        return "\n".join(history_lines)
    
    @staticmethod
    def clear_channel(channel_id: int):
        """Clear cache for a specific channel."""
        CHANNEL_MESSAGE_CACHE.pop(channel_id, None)
    
    @staticmethod
    def clear_all():
        """Clear all caches."""
        CHANNEL_MESSAGE_CACHE.clear()

message_cache = MessageCache()

PREMIUM_PERSONALITIES = {
    "Plus": ["maid", "roommate", "goth"],
    "Drive": ["tsundere"],
    "Pro": ["madscientist"],
}

SUBSCRIPTION_TIER_ORDER = ["Free", "Lite", "Plus", "Drive", "Pro", "Max"]

def get_personality_tier(personality_name: str) -> str | None:
    """Get the subscription tier required for a personality."""
    for tier, personalities in PREMIUM_PERSONALITIES.items():
        if personality_name in personalities:
            return tier
    return None

def has_access_to_personality(tier: str, personality_name: str) -> bool:
    """Check if a subscription tier has access to a personality."""
    personality_tier = get_personality_tier(personality_name)
    if personality_tier is None:
        return True  # Free personality
    
    user_tier_index = SUBSCRIPTION_TIER_ORDER.index(tier) if tier in SUBSCRIPTION_TIER_ORDER else 0
    personality_tier_index = SUBSCRIPTION_TIER_ORDER.index(personality_tier) if personality_tier in SUBSCRIPTION_TIER_ORDER else len(SUBSCRIPTION_TIER_ORDER)
    
    return user_tier_index >= personality_tier_index

def get_tier_requirements(personality_name: str) -> list[str]:
    """Get all tiers that unlock a personality."""
    personality_tier = get_personality_tier(personality_name)
    if personality_tier is None:
        return []
    
    tier_index = SUBSCRIPTION_TIER_ORDER.index(personality_tier) if personality_tier in SUBSCRIPTION_TIER_ORDER else len(SUBSCRIPTION_TIER_ORDER)
    return SUBSCRIPTION_TIER_ORDER[tier_index:]

def load_personalities():
    """Load all personalities from the personalities directory."""
    personalities = {}
    if not os.path.exists(PERSONALITIES_DIR):
        return personalities
    
    for filename in os.listdir(PERSONALITIES_DIR):
        if filename.endswith(".md"):
            name = filename[:-3]
            filepath = os.path.join(PERSONALITIES_DIR, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    personalities[name] = f.read()
            except Exception as e:
                print(f"Error loading personality {name}: {e}")
    
    return personalities

def get_personality_prompt(personality_name: str = "roturbot") -> str:
    """Get the system prompt for a specific personality."""
    personalities = load_personalities()
    if personality_name in personalities:
        return personalities[personality_name]

    if "roturbot" in personalities:
        return personalities["roturbot"]

    return "Hey there! I'm here to help."

def get_personality_gif_prefix(personality_name: str) -> str:
    """Extract the GIF_PREFIX from a personality file."""
    personalities = load_personalities()
    if personality_name in personalities:
        content = personalities[personality_name]
        for line in content.split('\n'):
            if line.startswith('GIF_PREFIX:'):
                return line.split(':', 1)[1].strip()
    return ""

def load_tool_instructions():
    """Load tool usage instructions."""
    try:
        with open(os.path.join(_MODULE_DIR, "static", "TOOL_USAGE.md"), "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "Use tools proactively to help with tasks and information retrieval."

def load_user_personalities():
    """Load user personality preferences from JSON file."""
    try:
        with open(os.path.join(_MODULE_DIR, "store", "user_personalities.json"), "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_user_personalities(personalities):
    """Save user personality preferences to JSON file."""
    with open(os.path.join(_MODULE_DIR, "store", "user_personalities.json"), "w") as f:
        json.dump(personalities, f)

def get_user_personality(user_id: int) -> str:
    """Get the personality preference for a user, defaults to 'roturbot'."""
    user_personalities = load_user_personalities()
    uid = str(user_id)
    
    if uid in user_personalities:
        personalities = load_personalities()
        personality = user_personalities[uid]
        if personality in personalities:
            return personality
    
    return "roturbot"

def set_user_personality(user_id: int, personality_name: str) -> bool:
    """Set the personality preference for a user."""
    personalities = load_personalities()
    if personality_name not in personalities:
        return False
    
    user_personalities = load_user_personalities()
    user_personalities[str(user_id)] = personality_name
    save_user_personalities(user_personalities)
    
    return True

SYSTEM_PROMPT = load_personalities()["roturbot"]

def load_activity_exclusions():
    """Load the list of users excluded from activity alerts"""
    try:
        with open(os.path.join(_MODULE_DIR, "store", "activity_exclusions.json"), "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_activity_exclusions(exclusions):
    """Save the list of users excluded from activity alerts"""
    with open(os.path.join(_MODULE_DIR, "store", "activity_exclusions.json"), "w") as f:
        json.dump(exclusions, f)

# ---------------- Daily Credit DM Opt-in Handling ---------------- #
def load_daily_credit_dm_optins():
    """Load list of users who opted in to receive daily credit DM notifications."""
    try:
        with open(os.path.join(_MODULE_DIR, "store", "daily_credit_dm_optins.json"), "r") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_daily_credit_dm_optins(optins):
    """Persist the daily credit DM opt-in list."""
    with open(os.path.join(_MODULE_DIR, "store", "daily_credit_dm_optins.json"), "w") as f:
        json.dump(optins, f)

def toggle_daily_credit_dm_optin(user_id) -> bool:
    """Toggle a user's opt-in status. Returns True if now enabled, False if disabled."""
    uid = str(user_id)
    optins = load_daily_credit_dm_optins()
    if uid in optins:
        optins.remove(uid)
        save_daily_credit_dm_optins(optins)
        return False
    optins.append(uid)
    save_daily_credit_dm_optins(optins)
    return True

def is_daily_credit_dm_enabled(user_id: int) -> bool:
    """Check if a user has opted in to daily credit DM notifications."""
    return str(user_id) in load_daily_credit_dm_optins()

def is_user_excluded(user_id):
    """Check if a user is excluded from activity alerts"""
    exclusions = load_activity_exclusions()
    return str(user_id) in exclusions

def toggle_user_exclusion(user_id):
    """Toggle a user's exclusion status and return new status"""
    exclusions = load_activity_exclusions()
    user_id = str(user_id)
    
    if user_id in exclusions:
        exclusions.remove(user_id)
        save_activity_exclusions(exclusions)
        return False  # No longer excluded
    else:
        exclusions.append(user_id)
        save_activity_exclusions(exclusions)
        return True  # Now excluded

def load_daily_activity():
    """Load daily activity tracking data"""
    try:
        with open(os.path.join(_MODULE_DIR, "store", "daily_activity.json"), "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"date": "", "users": {}}

def save_daily_activity(data):
    """Save daily activity tracking data"""
    with open(os.path.join(_MODULE_DIR, "store", "daily_activity.json"), "w") as f:
        json.dump(data, f)

def get_current_date():
    """Get current date in server timezone (UTC for now)"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def get_user_highest_role_credit(member):
    """Get the credit value for a user's highest valued role"""
    role_credits = {
        1171184265678032896: 3,     # Role with 3 credits
        1208870862011240509: 2.5,   # Role with 2.5 credits  
        1171799529822093322: 2,     # Role with 2 credits
        1204829341658120232: 1.5    # Role with 1.5 credits
    }
    
    highest_credit = 1  # Default credit value
    
    for role in member.roles:
        if role.id in role_credits:
            credit_value = role_credits[role.id]
            if credit_value > highest_credit:
                highest_credit = credit_value
    
    return highest_credit


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            return float(value.strip())
        return float(value)
    except Exception:
        return default


def _subscription_daily_credit_multiplier(tier: str | None) -> float:
    t = (tier or "Free").strip().lower()
    return {
        "free": 1.0,
        "lite": 1.0,
        "plus": 1.0,
        "drive": 2.0,
        "pro": 3.0,
        "max": 3.0,
    }.get(t, 1.0)


def _wealth_daily_credit_multiplier(balance: float) -> float:
    if balance > 1000:
        return 0.0
    if balance > 500:
        return 0.5
    return 1.0

async def award_daily_credit(user_id, credit_amount):
    """Award daily credit to a user via the rotur API"""
    try:
        user = await rotur.get_user_by('discord_id', str(user_id))
        if user.get('error') == "User not found" or user is None:
            return False, "User not linked to rotur"
        
        username = user.get("username")
        if not username:
            return False, "No username found"

        old_balance = _safe_float(user.get("sys.currency", user.get("currency", 0)), 0.0)
        tier = (user.get("sys.subscription", {}) or {}).get("tier", "Free")
        sub_multiplier = _subscription_daily_credit_multiplier(str(tier) if tier is not None else "Free")
        wealth_multiplier = _wealth_daily_credit_multiplier(old_balance)

        base_amount = _safe_float(credit_amount, 0.0)
        awarded_amount = round(base_amount * sub_multiplier * wealth_multiplier, 2)

        if awarded_amount <= 0:
            return True, (old_balance, old_balance, 0.0, str(tier or "Free"), sub_multiplier)

        result = await rotur.transfer_credits("rotur", username, awarded_amount, "daily credit")

        print(f"Update result for {username}: {result}")
        
        if result.get("error"):
            return False, f"API error: {result.get('error')}"
        else:
            new_balance = old_balance + awarded_amount
            return True, (old_balance, new_balance, awarded_amount, str(tier or "Free"), sub_multiplier)
            
    except Exception as e:
        return False, f"Error: {str(e)}"

async def send_credit_dm(user, old_balance, new_balance, credit_amount, subscription_tier: str = "Free", subscription_multiplier: float = 1.0):
    """Send a DM to the user about their daily credit award"""
    try:
        if not is_daily_credit_dm_enabled(user.id):
            return False
        embed = discord.Embed(
            title="💰 Daily Credits Awarded!",
            description=f"You received **{credit_amount:.2f}** rotur credits for being active today!",
            color=discord.Color.green()
        )
        embed.add_field(name="Previous Balance", value=f"{old_balance:.2f} credits", inline=True)
        embed.add_field(name="New Balance", value=f"{new_balance:.2f} credits", inline=True)
        embed.add_field(name="Credits Earned", value=f"+{credit_amount:.2f} credits", inline=True)
        embed.add_field(
            name="Subscription Multiplier",
            value=f"{subscription_tier} (x{subscription_multiplier:g})",
            inline=True,
        )

        if old_balance > 1000 and credit_amount <= 0:
            embed.add_field(
                name="Note",
                value=(
                    "Daily credits are designed to help lower-balance users build up their credits. "
                    "Since your balance is already high, you don't receive daily credits right now."
                ),
                inline=False,
            )
        embed.set_footer(text="Keep being active to earn more daily credits!")
        
        await user.send(embed=embed)
        return True
    except discord.Forbidden:
        return False
    except Exception as e:
        print(f"Error sending DM to {user}: {e}")
        return False

async def process_daily_credits():
    """Reset daily tracking and announce new day at midnight"""
    global last_daily_announcement_date
    try:
        activity_data = load_daily_activity()
    except Exception:
        activity_data = {"date": "", "users": {}}

    current_date = get_current_date()

    if last_daily_announcement_date == current_date:
        return

    users_awarded = len(activity_data.get("users", {}))
    total_credits_awarded = sum(activity_data.get("users", {}).values())

    try:
        save_daily_activity({"date": "", "users": {}})
    except Exception as e:
        print(f"Failed to reset daily activity store: {e}")

    general_channel = client.get_channel(1338555310335463557)  # rotur general
    try:
        if general_channel and isinstance(general_channel, discord.TextChannel):
            if users_awarded > 0:
                embed = discord.Embed(
                    title="🌅 Daily Credits Are Now Available!",
                    description=(
                        f"A new day has begun! Yesterday, **{users_awarded}** users earned daily credits. "
                        "Be active today to earn yours!"
                    ),
                    color=discord.Color.blue()
                )
                embed.add_field(name="Yesterday's Total", value=f"{total_credits_awarded:.2f} credits", inline=True)
                embed.add_field(name="Users Rewarded", value=f"{users_awarded} users", inline=True)
            else:
                embed = discord.Embed(
                    title="🌅 Daily Credits Are Now Available!",
                    description="A new day has begun! Be active today to earn your daily credits!",
                    color=discord.Color.blue()
                )
            embed.set_footer(text="Send your first message today to earn daily credits!")
            await general_channel.send(embed=embed)
    except Exception as e:
        print(f"Failed to send daily credits announcement: {e}")

    print(f"Daily credits reset: Yesterday had {users_awarded} users, {total_credits_awarded:.2f} total credits")
    last_daily_announcement_date = current_date

async def battery_notifier():
    """
    Schedule battery notifications
    Sends a dm to Mistium if the laptop is unplugged from power
    """

    battery = psutil.sensors_battery()
    if not battery:
        return

    was_plugged = battery.power_plugged
    while not client.is_closed():
        try:
            battery = psutil.sensors_battery()
            if not battery:
                return
            if was_plugged and not battery.power_plugged:
                # send dm to mistium
                try:
                    user = client.get_user(int(mistium))
                    if user is not None:
                        await user.send("rotur has been unplugged")
                except Exception:
                    pass
            elif not was_plugged and battery.power_plugged:
                # send dm to mistium
                try:
                    user = client.get_user(int(mistium))
                    if user is not None:
                        await user.send("rotur has been plugged in")
                except Exception:
                    pass
            was_plugged = battery.power_plugged
            await asyncio.sleep(2)

            
        except Exception as e:
            print(f"Error in battery notifier: {str(e)}")
            await asyncio.sleep(3600)

async def daily_credits_scheduler():
    """Schedule daily credits processing at midnight UTC"""
    await client.wait_until_ready()
    
    while not client.is_closed():
        try:
            now = datetime.now(timezone.utc)
            tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            time_until_midnight = (tomorrow - now).total_seconds()
            
            print(f"Daily credits scheduler: waiting {time_until_midnight/3600:.1f} hours until next midnight")
            await asyncio.sleep(time_until_midnight)
            
            await process_daily_credits()
            
        except Exception as e:
            print(f"Error in daily credits scheduler: {e}")
            await asyncio.sleep(3600)

async def icon_cache_cleanup_scheduler():
    """Schedule icon cache cleanup every 24 hours"""
    await client.wait_until_ready()
    
    while not client.is_closed():
        try:
            await asyncio.sleep(86400)
            
            if icon_cache:
                print("Running icon cache cleanup...")
                removed = await icon_cache.cleanup_old_emojis()
                print(f"Icon cache cleanup complete: {removed} emojis removed")
            
        except Exception as e:
            print(f"Error in icon cache cleanup scheduler: {e}")
            await asyncio.sleep(3600)

async def memory_cleanup_scheduler():
    """Schedule memory cleanup every 24 hours to remove expired memories"""
    await client.wait_until_ready()
    
    await asyncio.sleep(300)
    
    while not client.is_closed():
        try:
            print("Running memory cleanup...")
            deleted_count = MemorySystem.cleanup_expired()
            print(f"Memory cleanup complete: {deleted_count} expired memories removed")
            
            await asyncio.sleep(86400)
            
        except Exception as e:
            print(f"Error in memory cleanup scheduler: {e}")
            await asyncio.sleep(3600)

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.presences = True
intents.members = True

client = discord.Client(intents=intents)

last_daily_announcement_date = None
daily_scheduler_started = False
battery_notifier_started = False
icon_cache_cleanup_started = False
memory_cleanup_started = False
icon_cache = None
thread_context_manager = None
discord_thread_handler = None

tree = app_commands.CommandTree(client)

_parent_context_func = None

def set_parent_context(func):
    """Set the parent context function"""
    global _parent_context_func
    _parent_context_func = func

def get_parent_context():
    """Get the parent context"""
    if _parent_context_func is None:
        return {}
    return _parent_context_func()

global getParentContext

transfer = app_commands.Group(name='transfer', description='Commands related to transferring credits')
transfer = app_commands.allowed_installs(guilds=True, users=True)(transfer)
transfer = app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)(transfer)
tree.add_command(transfer)

keys = app_commands.Group(name='keys', description='Commands related to user keys')
keys = app_commands.allowed_installs(guilds=True, users=True)(keys)
keys = app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)(keys)
tree.add_command(keys)

friends = app_commands.Group(name='friends', description='Manage your Rotur friends')
friends = app_commands.allowed_installs(guilds=True, users=True)(friends)
friends = app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)(friends)
tree.add_command(friends)

requests_group = app_commands.Group(name='requests', description='Manage your incoming friend requests')
requests_group = app_commands.allowed_installs(guilds=True, users=True)(requests_group)
requests_group = app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)(requests_group)
tree.add_command(requests_group)
tree.add_command(group.group_cmds)


def _chunk_lines(lines: list[str], chunk_size: int = 20) -> list[str]:
    if chunk_size <= 0:
        chunk_size = 20
    return ["\n".join(lines[i:i + chunk_size]) for i in range(0, len(lines), chunk_size)]


async def _get_linked_token(discord_user_id: int) -> str | None:
    """Return the user's rotur auth token if they're linked, else None."""
    try:
        user = await rotur.get_user_by('discord_id', str(discord_user_id))
    except Exception:
        return None
    if user is None or user.get('error') == 'User not found':
        return None
    token = user.get('key')
    if not token:
        return None
    return token


def _safe_json(resp) -> dict:
    try:
        return resp.json()
    except Exception:
        return {}


def _is_mistium(user_id: int) -> bool:
    """Return True if the given Discord user id matches the configured Mistium id."""
    try:
        return str(user_id) == str(mistium)
    except Exception:
        return False


def _format_entry(link: str, count: int, reacts: dict, emoji: str) -> str:
    """Return a readable field value for a leaderboard entry.

    - Shows emoji and count, author (if available), jump link and a single-line preview of the message.
    - Truncates long messages and sanitizes backticks/newlines for embed compatibility.
    """
    author = reacts.get('author') if isinstance(reacts, dict) else None
    author = author or 'Unknown'
    content = reacts.get('content') if isinstance(reacts, dict) else ''
    if content is None:
        content = ''
    preview = ' '.join(str(content).splitlines())
    preview = preview.replace('`', "'")
    max_len = 300
    if len(preview) > max_len:
        preview = preview[:max_len].rstrip() + '…'
    return f"{emoji} {count} • {author}\n> [Jump to](https://discord.com/channels/{originOS}/{link}) | {preview}"


async def _get_username_from_discord(discord_id: int) -> str | None:
    try:
        status, user_data = await rotur.profile_by_discord_id(discord_id)
        if status == 200 and user_data and user_data.get('error') != 'User not found':
            return user_data.get('username')
    except Exception:
        pass
    return None


@allowed_everywhere
@tree.command(name='standing', description='View your current standing and history')
async def user_standing(ctx: discord.Interaction):
    await ctx.response.defer()
    
    username = await _get_username_from_discord(ctx.user.id)
    if not username:
        await send_message(ctx.followup, "You are not linked to a rotur account. Please link your account first.", ephemeral=True)
        return
    
    try:
        status, data = await rotur.get_user_standing(username)
        if status != 200:
            await send_message(ctx.followup, "Failed to fetch standing data. Please try again later.", ephemeral=True)
            return
        
        current_standing = data.get('standing', 'good')
        recover_at = data.get('recover_at', 0)
        history = data.get('history', [])
        
        color_map = {
            'good': discord.Color.green(),
            'warning': discord.Color.yellow(),
            'suspended': discord.Color.orange(),
            'banned': discord.Color.red(),
        }
        
        embed = discord.Embed(
            title=f"Standing for {username}",
            description=f"**Current Level:** {current_standing.upper()}",
            color=color_map.get(current_standing, discord.Color.blue())
        )
        
        if recover_at and recover_at > 0:
            recover_dt = datetime.fromtimestamp(recover_at, timezone.utc)
            embed.add_field(name="Automatic Recovery", value=f"<t:{recover_at}:R>", inline=False)
        elif current_standing != 'good':
            embed.add_field(name="Automatic Recovery", value="No scheduled recovery", inline=False)
        
        if history:
            history_text = []
            for entry in history[-10:]:
                level = entry.get('level', 'unknown')
                reason = entry.get('reason', 'No reason')
                timestamp = entry.get('timestamp', 0)
                admin_id = entry.get('admin_id', 'system')
                
                if timestamp:
                    dt = datetime.fromtimestamp(timestamp, timezone.utc)
                    time_str = dt.strftime('%b %d, %Y %H:%M')
                else:
                    time_str = 'Unknown'
                
                history_text.append(f"• **{level.upper()}** - {reason} ({time_str})")
            
            if history_text:
                embed.add_field(name=f"Recent History ({len(history_text)} entries)", value="\n".join(history_text), inline=False)
        
        embed.set_footer(text="Standing affects your ability to use certain features.")
        await send_message(ctx.followup, embed=embed)
        
    except Exception as e:
        await send_message(ctx.followup, f"Error fetching standing: {str(e)}", ephemeral=True)


@allowed_everywhere
@tree.command(name='purge', description='[Mistium only] Delete a number of recent messages from this channel')
@app_commands.describe(number='How many messages to delete (1-100)')
async def purge(ctx: discord.Interaction, number: int):
    # Only Mistium can use this command
    if not _is_mistium(ctx.user.id):
        await send_message(ctx.response, 'You do not have permission to use this command.', ephemeral=True)
        return

    # Validate channel
    channel = ctx.channel
    if channel is None or not isinstance(channel, discord.TextChannel):
        await send_message(ctx.response, 'This command can only be used in a server text channel.', ephemeral=True)
        return

    # Bound the purge to something Discord will accept in bulk
    if number is None:
        number = 0
    try:
        number = int(number)
    except Exception:
        await send_message(ctx.response, 'Invalid number.', ephemeral=True)
        return
    if number <= 0:
        await send_message(ctx.response, 'Number must be at least 1.', ephemeral=True)
        return
    if number > 100:
        number = 100

    # Defer so we don't hit the interaction 3s timeout
    try:
        await ctx.response.defer(ephemeral=True, thinking=True)
    except Exception:
        pass

    # Include the invocation message in the deletion set by fetching +1
    limit = min(100, number + 1)
    try:
        messages = [m async for m in channel.history(limit=limit)]
    except Exception as e:
        await send_message(ctx.followup, f'Failed to read channel history: {str(e)}', ephemeral=True)
        return

    if not messages:
        await send_message(ctx.followup, 'No messages found to delete.', ephemeral=True)
        return

    deleted_count = 0
    try:
        deleted = await channel.delete_messages(messages)
        deleted_count = len(deleted) if deleted else 0
    except discord.Forbidden:
        await send_message(ctx.followup, "I don't have permission to delete messages in this channel.", ephemeral=True)
        return
    except discord.HTTPException:
        deleted_count = 0
        for m in messages:
            try:
                await m.delete()
                deleted_count += 1
            except Exception:
                continue
    except Exception as e:
        await send_message(ctx.followup, f'Failed to purge messages: {str(e)}', ephemeral=True)
        return

    await send_message(ctx.followup, f'Deleted {max(0, deleted_count - 1)} message(s).', ephemeral=True)


@allowed_everywhere
@tree.command(name='restart', description='Restart the bot websocket (bot owner only)')
async def restart(ctx: discord.Interaction):
    if ctx.user.id != BOT_OWNER_ID:
        await send_message(ctx.response, 'Only the bot owner can use this command', ephemeral=True)
        return

    try:
        await send_message(ctx.response, 'Restarting websocket...')
        subprocess.run('~/documents/rotur_manager.sh restart websocket', shell=True, capture_output=True, text=True)
    except Exception as e:
        await send_message(ctx.response, f'Error: {str(e)}', ephemeral=True)

@allowed_everywhere
@friends.command(name='add', description='Send a friend request to a user')
@app_commands.describe(username='The username to send a friend request to')
async def friends_add(ctx: discord.Interaction, username: str):
    token = await _get_linked_token(ctx.user.id)
    if not token:
        await send_message(ctx.response, "You aren't linked to rotur (or no auth token found).", ephemeral=True)
        return

    try:
        status, payload = await rotur.friends_request(token, username)
    except Exception as e:
        await send_message(ctx.response, f"Error contacting server: {str(e)}", ephemeral=True)
        return

    if status != 200 or (isinstance(payload, dict) and payload.get('error')):
        err = payload.get('error') if isinstance(payload, dict) else None
        await send_message(ctx.response, err or f"Failed to send request (status {status}).", ephemeral=True)
        return

    msg = payload.get('message') if isinstance(payload, dict) else None
    await send_message(ctx.response, msg or f"Friend request sent to {username}.")


@allowed_everywhere
@friends.command(name='remove', description='Remove a friend')
@app_commands.describe(username='The username to remove from your friends list')
async def friends_remove(ctx: discord.Interaction, username: str):
    token = await _get_linked_token(ctx.user.id)
    if not token:
        await send_message(ctx.response, "You aren't linked to rotur (or no auth token found).", ephemeral=True)
        return

    try:
        status, payload = await rotur.friends_remove(token, username)
    except Exception as e:
        await send_message(ctx.response, f"Error contacting server: {str(e)}", ephemeral=True)
        return

    if status != 200 or (isinstance(payload, dict) and payload.get('error')):
        err = payload.get('error') if isinstance(payload, dict) else None
        await send_message(ctx.response, err or f"Failed to remove friend (status {status}).", ephemeral=True)
        return

    msg = payload.get('message') if isinstance(payload, dict) else None
    await send_message(ctx.response, msg or f"Removed {username} from your friends.")


@allowed_everywhere
@friends.command(name='list', description='List your friends')
async def friends_list(ctx: discord.Interaction):
    token = await _get_linked_token(ctx.user.id)
    if not token:
        await send_message(ctx.response, "You aren't linked to rotur (or no auth token found).", ephemeral=True)
        return

    try:
        status, payload = await rotur.friends_list(token)
    except Exception as e:
        await send_message(ctx.response, f"Error contacting server: {str(e)}", ephemeral=True)
        return

    if status != 200 or (isinstance(payload, dict) and payload.get('error')):
        err = payload.get('error') if isinstance(payload, dict) else None
        await send_message(ctx.response, err or f"Failed to fetch friends (status {status}).", ephemeral=True)
        return

    friends_list = payload.get('friends', []) if isinstance(payload, dict) else []
    if not friends_list:
        await send_message(ctx.response, "You don't have any friends yet.")
        return

    lines = [f"• {u}" for u in friends_list]
    chunks = _chunk_lines(lines, chunk_size=25)
    embed = discord.Embed(title="Your Friends", description=chunks[0], color=discord.Color.blurple())
    if len(chunks) > 1:
        for idx, chunk in enumerate(chunks[1:6], start=2):
            embed.add_field(name=f"Friends (page {idx})", value=chunk, inline=False)
        if len(chunks) > 6:
            embed.set_footer(text=f"Showing {min(len(friends_list), 25*6)} of {len(friends_list)} friends")

    await send_message(ctx.response, embed=embed)


@allowed_everywhere
@requests_group.command(name='list', description='List your incoming friend requests')
async def requests_list(ctx: discord.Interaction):
    token = await _get_linked_token(ctx.user.id)
    if not token:
        await send_message(ctx.response, "You aren't linked to rotur (or no auth token found).", ephemeral=True)
        return

    # There is no dedicated /friends/requests endpoint. Requests are stored on the user object.
    try:
        me = await rotur.get_user_by('discord_id', str(ctx.user.id))
    except Exception as e:
        await send_message(ctx.response, f"Error reading your profile: {str(e)}", ephemeral=True)
        return

    if me is None or me.get('error') == 'User not found':
        await send_message(ctx.response, "You aren't linked to rotur.", ephemeral=True)
        return

    reqs = me.get('sys.requests', [])
    if not reqs:
        await send_message(ctx.response, "You have no pending friend requests.")
        return

    lines = [f"• {u}" for u in reqs]
    chunks = _chunk_lines(lines, chunk_size=25)
    embed = discord.Embed(title="Pending Friend Requests", description=chunks[0], color=discord.Color.gold())
    if len(chunks) > 1:
        for idx, chunk in enumerate(chunks[1:6], start=2):
            embed.add_field(name=f"Requests (page {idx})", value=chunk, inline=False)
        if len(chunks) > 6:
            embed.set_footer(text=f"Showing {min(len(reqs), 25*6)} of {len(reqs)} requests")

    await send_message(ctx.response, embed=embed)


@allowed_everywhere
@requests_group.command(name='accept', description='Accept a friend request from a user')
@app_commands.describe(username='The username whose request you want to accept')
async def requests_accept(ctx: discord.Interaction, username: str):
    token = await _get_linked_token(ctx.user.id)
    if not token:
        await send_message(ctx.response, "You aren't linked to rotur (or no auth token found).", ephemeral=True)
        return

    try:
        status, payload = await rotur.friends_accept(token, username)
    except Exception as e:
        await send_message(ctx.response, f"Error contacting server: {str(e)}", ephemeral=True)
        return

    if status != 200 or (isinstance(payload, dict) and payload.get('error')):
        err = payload.get('error') if isinstance(payload, dict) else None
        await send_message(ctx.response, err or f"Failed to accept request (status {status}).", ephemeral=True)
        return

    msg = payload.get('message') if isinstance(payload, dict) else None
    await send_message(ctx.response, msg or f"Accepted friend request from {username}.")


@allowed_everywhere
@requests_group.command(name='reject', description='Reject a friend request from a user')
@app_commands.describe(username='The username whose request you want to reject')
async def requests_reject(ctx: discord.Interaction, username: str):
    token = await _get_linked_token(ctx.user.id)
    if not token:
        await send_message(ctx.response, "You aren't linked to rotur (or no auth token found).", ephemeral=True)
        return

    try:
        status, payload = await rotur.friends_reject(token, username)
    except Exception as e:
        await send_message(ctx.response, f"Error contacting server: {str(e)}", ephemeral=True)
        return

    if status != 200 or (isinstance(payload, dict) and payload.get('error')):
        err = payload.get('error') if isinstance(payload, dict) else None
        await send_message(ctx.response, err or f"Failed to reject request (status {status}).", ephemeral=True)
        return

    msg = payload.get('message') if isinstance(payload, dict) else None
    await send_message(ctx.response, msg or f"Rejected friend request from {username}.")


@allowed_everywhere
@requests_group.command(name='accept_all', description='Accept all pending friend requests')
async def requests_accept_all(ctx: discord.Interaction):
    token = await _get_linked_token(ctx.user.id)
    if not token:
        await send_message(ctx.response, "You aren't linked to rotur (or no auth token found).", ephemeral=True)
        return

    try:
        me = await rotur.get_user_by('discord_id', str(ctx.user.id))
    except Exception as e:
        await send_message(ctx.response, f"Error reading your profile: {str(e)}", ephemeral=True)
        return

    reqs = (me or {}).get('sys.requests', [])
    if not reqs:
        await send_message(ctx.response, "You have no pending friend requests.")
        return

    accepted = []
    failed = []
    for username in reqs:
        try:
            status, payload = await rotur.friends_accept(token, username)
            if status == 200 and not (isinstance(payload, dict) and payload.get('error')):
                accepted.append(username)
            else:
                err = payload.get('error') if isinstance(payload, dict) else 'failed'
                failed.append(f"{username} ({err or 'failed'})")
        except Exception as e:
            failed.append(f"{username} ({str(e)})")

    msg = f"Accepted {len(accepted)} request(s)."
    if failed:
        msg += f" Failed: {len(failed)}."

    embed = discord.Embed(title="Accept All Requests", description=msg, color=discord.Color.green())
    if accepted:
        embed.add_field(name="Accepted", value="\n".join(accepted[:50]), inline=False)
    if failed:
        embed.add_field(name="Failed", value="\n".join(failed[:25]), inline=False)

    await send_message(ctx.response, embed=embed)


@allowed_everywhere
@requests_group.command(name='reject_all', description='Reject all pending friend requests')
async def requests_reject_all(ctx: discord.Interaction):
    token = await _get_linked_token(ctx.user.id)
    if not token:
        await send_message(ctx.response, "You aren't linked to rotur (or no auth token found).", ephemeral=True)
        return

    try:
        me = await rotur.get_user_by('discord_id', str(ctx.user.id))
    except Exception as e:
        await send_message(ctx.response, f"Error reading your profile: {str(e)}", ephemeral=True)
        return

    reqs = (me or {}).get('sys.requests', [])
    if not reqs:
        await send_message(ctx.response, "You have no pending friend requests.")
        return

    rejected = []
    failed = []
    for username in reqs:
        try:
            status, payload = await rotur.friends_reject(token, username)
            if status == 200 and not (isinstance(payload, dict) and payload.get('error')):
                rejected.append(username)
            else:
                err = payload.get('error') if isinstance(payload, dict) else 'failed'
                failed.append(f"{username} ({err or 'failed'})")
        except Exception as e:
            failed.append(f"{username} ({str(e)})")

    msg = f"Rejected {len(rejected)} request(s)."
    if failed:
        msg += f" Failed: {len(failed)}."

    embed = discord.Embed(title="Reject All Requests", description=msg, color=discord.Color.red())
    if rejected:
        embed.add_field(name="Rejected", value="\n".join(rejected[:50]), inline=False)
    if failed:
        embed.add_field(name="Failed", value="\n".join(failed[:25]), inline=False)

    await send_message(ctx.response, embed=embed)

async def create_embeds_from_user(user, use_emoji_badges=True):
    """Create an embed from a user object."""

    def coerce_discord_color(value, fallback: discord.Colour | None = None) -> discord.Colour | None:
        """Accept discord.Colour/int/hex-string and return a discord.Colour (or None)."""
        if fallback is None:
            fallback = discord.Color.blue()

        if value is None:
            return fallback

        if isinstance(value, discord.Colour):
            return value

        if isinstance(value, int):
            return discord.Color(value=value & 0xFFFFFF)

        if isinstance(value, str):
            s = value.strip()
            if not s:
                return fallback

            s_lower = s.lower()
            if s_lower.startswith('#'):
                s = s[1:]
            elif s_lower.startswith('0x'):
                s = s[2:]

            if re.fullmatch(r"[0-9a-fA-F]{3}", s):
                s = ''.join(ch * 2 for ch in s)

            if re.fullmatch(r"[0-9a-fA-F]{6}", s):
                return discord.Color(value=int(s, 16))

            if re.fullmatch(r"\d+", s):
                try:
                    return discord.Color(value=int(s) & 0xFFFFFF)
                except Exception:
                    return fallback

        return fallback

    badges = user.get('badges', [])
    badge_emojis = []
    
    if use_emoji_badges and icon_cache and badges:
        try:
            badge_emojis = await icon_cache.get_badge_emojis(badges)
        except Exception as e:
            print(f"Error getting badge emojis: {e}")
    
    bio_text = rotur.bio_from_obj(user)
    if badge_emojis:
        badges_line = " ".join(badge_emojis)
        description = f"{badges_line}\n\n{bio_text}"
    else:
        description = bio_text

    theme = user.get("theme") if isinstance(user, dict) else None
    accent_raw = theme.get("accent") if isinstance(theme, dict) else None
    embed_color = coerce_discord_color(accent_raw, discord.Color.blue())

    main_embed = discord.Embed(
        title=user.get('username', 'Unknown User'),
        description=description,
        color=embed_color
    )
    
    username = user.get('username')
    if username and isinstance(username, str) and username.strip():
        if user.get('pfp'):
            main_embed.set_thumbnail(url=f"https://avatars.rotur.dev/{username}.gif?nocache={randomString(5)}")
            
        if user.get('banner'):
            main_embed.set_image(url=f"https://avatars.rotur.dev/.banners/{username}.gif?nocache={randomString(5)}")
    
    standing_data = user.get('sys.standing')
    if standing_data:
        standing_level = None
        recover_at = None
        
        if isinstance(standing_data, dict):
            standing_level = standing_data.get('level')
            recover_at = standing_data.get('recover_at')
        elif isinstance(standing_data, str):
            standing_level = standing_data
        
        if standing_level and standing_level != 'good':
            main_embed.color = {
                'warning': discord.Color.yellow(),
                'suspended': discord.Color.orange(),
                'banned': discord.Color.red(),
            }.get(standing_level, main_embed.color)
            standing_value = f"{standing_level.upper()}"
            
            if recover_at and recover_at > 0:
                recover_dt = datetime.fromtimestamp(recover_at, timezone.utc)
                standing_value += f"\n<:recover:{recover_dt}:R>"
            
            main_embed.add_field(name="Standing", value=standing_value, inline=True)
    
    embeds = [main_embed]
    return embeds

@allowed_everywhere
@tree.command(name='me', description='View your rotur profile')
async def me(ctx: discord.Interaction):
    await ctx.response.defer()

    _, user = await rotur.profile_by_discord_id(ctx.user.id)
    
    if user is None or user.get('error') == "User not found":
        await send_message(ctx.followup, 'You are not linked to a rotur account. Please link your account using `/link` command.')
        return
    
    embeds = await create_embeds_from_user(user)
    await send_message(ctx.followup, embeds=embeds)
    return

@allowed_everywhere
@tree.command(name='user', description='View a user\'s rotur profile')
@app_commands.describe(username='The username of the user to view')
async def user(ctx: discord.Interaction, username: str):
    await ctx.response.defer()

    _, user = await rotur.profile_by_name(username)
    
    if user is None:
        await send_message(ctx.followup, 'User not found.')
        return

    if (str(user.get('sys.banned', False)).lower() == "true"):
        await send_message(ctx.followup, embeds=[discord.Embed(
            title="Account Banned",
            description=f"The account **{user.get('username', 'Unknown')}** has been banned.",
            color=discord.Color.red()
        )])
        return

    if (str(user.get('private', False)).lower() == "true"):
        await send_message(ctx.followup, embeds=[discord.Embed(
            title="Private Profile",
            description="This user has a private profile. You cannot view their details.",
            color=discord.Color.red()
        )])
        return

    embeds = await create_embeds_from_user(user)
    await send_message(ctx.followup, embeds=embeds)

@allowed_everywhere
@tree.command(name='level', description='View your level and XP progress')
async def level(ctx: discord.Interaction):
    if not XP_SYSTEM_ENABLED or not xp_system:
        await send_message(ctx.response, "The XP system is currently disabled.", ephemeral=True)
        return
    
    try:
        xp_stats = xp_system.get_user_xp_stats(ctx.user.id)
        level = xp_stats.get('level', 0)
        xp = xp_stats.get('xp', 0)
        total_messages = xp_stats.get('total_messages', 0)
        
        current_level_xp = xp_system.calculate_xp_for_level(level)
        next_level_xp = xp_system.calculate_xp_for_level(level + 1)
        xp_in_level = xp - current_level_xp
        xp_needed = next_level_xp - current_level_xp
        
        progress_percent = (xp_in_level / xp_needed * 100) if xp_needed > 0 else 0
        
        filled = int(progress_percent / 5)
        bar = "█" * filled + "░" * (20 - filled)
        
        embed = discord.Embed(
            title=f"{ctx.user.display_name}'s Level",
            description=f"**Level {level}**",
            color=discord.Color.gold()
        )
        
        embed.add_field(
            name="XP Progress",
            value=f"`{bar}` {progress_percent:.1f}%\n{xp_in_level:,} / {xp_needed:,} XP",
            inline=False
        )
        
        embed.add_field(
            name="Total XP",
            value=f"{xp:,}",
            inline=True
        )
        
        embed.add_field(
            name="Total Messages",
            value=f"{total_messages:,}",
            inline=True
        )
        
        embed.add_field(
            name="Next Level",
            value=f"Level {level + 1} at {next_level_xp:,} XP\n({next_level_xp - xp:,} XP remaining)",
            inline=False
        )
        
        embed.set_thumbnail(url=ctx.user.display_avatar.url)
        
        await send_message(ctx.response, embed=embed)
        
    except Exception as e:
        await send_message(ctx.response, f"Error fetching level data: {str(e)}")

@allowed_everywhere
@tree.command(name='leaderboard', description='View the XP leaderboard')
async def leaderboard(ctx: discord.Interaction):
    if not XP_SYSTEM_ENABLED or not xp_system:
        await send_message(ctx.response, "The XP system is currently disabled.", ephemeral=True)
        return
    
    await ctx.response.defer()
    
    try:
        data = xp_system.load_user_xp_data()
        
        if not data:
            await send_message(ctx.followup, "No leaderboard data available yet!")
            return
        
        sorted_users = sorted(
            data.items(),
            key=lambda x: (x[1].get('level', 0), x[1].get('xp', 0)),
            reverse=True
        )
        
        user_id = str(ctx.user.id)
        user_rank = None
        for i, (uid, _) in enumerate(sorted_users, 1):
            if uid == user_id:
                user_rank = i
                break
        
        top_10 = sorted_users[:10]
        
        leaderboard_text = []
        for i, (uid, stats) in enumerate(top_10, 1):
            level = stats.get('level', 0)
            xp = stats.get('xp', 0)
            
            medal = ""
            if i == 1:
                medal = "🥇 "
            elif i == 2:
                medal = "🥈 "
            elif i == 3:
                medal = "🥉 "
            
            leaderboard_text.append(f"{medal}**#{i}** <@{uid}> - Level {level} ({xp:,} XP)")
        
        embed = discord.Embed(
            title="XP Leaderboard",
            description="\n".join(leaderboard_text),
            color=discord.Color.gold()
        )
        
        if user_rank:
            user_stats = data[user_id]
            user_level = user_stats.get('level', 0)
            user_xp = user_stats.get('xp', 0)
            
            if user_rank <= 10:
                footer_text = f"You are #{user_rank} on the leaderboard!"
            else:
                footer_text = f"Your Rank: #{user_rank} - Level {user_level} ({user_xp:,} XP)"
            
            embed.set_footer(text=footer_text, icon_url=ctx.user.display_avatar.url)
        else:
            embed.set_footer(text="Start chatting to appear on the leaderboard!")
        
        await send_message(ctx.followup, embed=embed)
        
    except Exception as e:
        await send_message(ctx.followup, f"Error fetching leaderboard: {str(e)}")

@allowed_everywhere
@tree.command(name='up', description='Check if the rotur auth server is online')
async def up(ctx: discord.Interaction):
    try:
        parent_ctx = get_parent_context()
        users = await parent_ctx["get_room_users"]("roturTW")
        found = any(user.get("username") == "sys-rotur" for user in users)
        if found:
            await send_message(ctx.response, "✅ sys-rotur is connected")
        else:
            await send_message(ctx.response, "❌ sys-rotur is not connected")
    except Exception as e:
        await send_message(ctx.response, f"❌ Error checking server status: {str(e)}")

@allowed_everywhere
@tree.command(name='online', description='Show users connected to roturTW')
async def online(ctx: discord.Interaction):
    try:
        parent_ctx = get_parent_context()
        users = await parent_ctx["get_room_users"]("roturTW")
        if not users:
            await send_message(ctx.response, "No users are currently connected to roturTW.")
            return
        lines = []
        for user in users:
            username = user.get("username", "")
            rotur_auth = user.get("rotur", "")
            lines.append(f"{username:<35} Auth: {rotur_auth}")
        await send_message(ctx.response, f"```\n" + "\n".join(lines) + "\n```")
    except Exception as e:
        await send_message(ctx.response, f"❌ Error fetching online users: {str(e)}")

@allowed_everywhere
@tree.command(name='totalusers', description='Display the total number of rotur users')
async def totalusers(ctx: discord.Interaction):
    _, users = await rotur.stats_users()
    if not isinstance(users, dict) or 'total_users' not in users:
        await send_message(ctx.response, "Error fetching user statistics.")
        return
    total_users = users.get('total_users', 0)
    await send_message(ctx.response, f"Total rotur users: {total_users}")

@allowed_everywhere
@tree.command(name='usage', description='Check your file system usage')
async def usage(ctx: discord.Interaction):
    user = await rotur.get_user_by('discord_id', str(ctx.user.id))
    if user is None or user.get('error') == "User not found":
        await send_message(ctx.response, "You aren't linked to rotur.", ephemeral=True)
        return
    usage_data = await rotur.get_user_file_size(user.get("key"), user.get("username", "unknown"))
    if usage_data is None:
        await send_message(ctx.response, "No file system found for your account.")
        return
    await send_message(ctx.response, f'Your file system is: {usage_data}')

@allowed_everywhere
@tree.command(name='changepass', description='[EPHEMERAL] Change the password of your linked rotur account')
@app_commands.describe(new_password='Your new password (will be hashed client-side)')
async def changepass(ctx: discord.Interaction, new_password: str):
    # Require a linked account
    user = await rotur.get_user_by('discord_id', str(ctx.user.id))
    if user is None or user.get('error') == "User not found":
        await send_message(ctx.response, "You aren't linked to rotur.", ephemeral=True)
        return

    token = user.get("key")
    if not token:
        await send_message(ctx.response, "No auth token found for your account.", ephemeral=True)
        return

    # Hash the provided password as requested (raw value should be the md5 hash)
    hashed = hashlib.md5(new_password.encode()).hexdigest()

    try:
        status, payload = await rotur.users_patch(token, "password", hashed)
        if status == 200:
            await send_message(ctx.response, "Your rotur password has been changed.", ephemeral=True)
        else:
            err = payload.get('error') if isinstance(payload, dict) else None
            await send_message(ctx.response, err or f"Failed to change password. Server responded with status {status}.", ephemeral=True)
    except Exception as e:
        await send_message(ctx.response, f"Error changing password: {str(e)}", ephemeral=True)

@allowed_everywhere
@tree.command(name='most_followed', description='See the leaderboard of the most followed users')
async def most_followed(ctx: discord.Interaction):
    _, users = await rotur.stats_followers()
    if users is None:
        await send_message(ctx.response, "Error: Unable to retrieve user data.")
        return

    embed = discord.Embed(title="Most Followed Users", description="Leaderboard of the most followed users")
    for i, user in enumerate(users):
        embed.add_field(name=f"{i + 1}. {user.get('username', 'unknown')}", value=f"Followers: {user.get('follower_count', 0)}", inline=False)

    await send_message(ctx.response, embeds=[embed])

@allowed_everywhere
@tree.command(name='follow', description='Follow a user on rotur')
@app_commands.describe(username='The username of the user to follow')
async def follow(ctx: discord.Interaction, username: str):
    user = await rotur.get_user_by('discord_id', str(ctx.user.id))
    if user is None or user.get('error') == "User not found":
        await send_message(ctx.response, "You aren't linked to rotur.", ephemeral=True)
        return
    
    token = user.get("key")
    if not token:
        await send_message(ctx.response, "No auth token found for your account.", ephemeral=True)
        return

    try:
        status, result = await rotur.follow_user(token, username)
        if status == 200:
            await send_message(ctx.response, f"You are now following {username}.")
        else:
            error_msg = result.get('error', f'Failed to follow user. Server responded with status {status}.') if isinstance(result, dict) else f'Failed to follow user. Server responded with status {status}.'
            await send_message(ctx.response, error_msg, ephemeral=True)
    except Exception as e:
        await send_message(ctx.response, f"Error following user: {str(e)}", ephemeral=True)

@allowed_everywhere
@tree.command(name='unfollow', description='Unfollow a user on rotur')
@app_commands.describe(username='The username of the user to unfollow')
async def unfollow(ctx: discord.Interaction, username: str):
    user = await rotur.get_user_by('discord_id', str(ctx.user.id))
    if user is None or user.get('error') == "User not found":
        await send_message(ctx.response, "You aren't linked to rotur.", ephemeral=True)
        return
    
    token = user.get("key")
    if not token:
        await send_message(ctx.response, "No auth token found for your account.", ephemeral=True)
        return

    try:
        status, result = await rotur.unfollow_user(token, username)
        if status == 200:
            await send_message(ctx.response, f"You are no longer following {username}.")
        else:
            error_msg = result.get('error', f'Failed to unfollow user. Server responded with status {status}.') if isinstance(result, dict) else f'Failed to unfollow user. Server responded with status {status}.'
            await send_message(ctx.response, error_msg, ephemeral=True)
    except Exception as e:
        await send_message(ctx.response, f"Error unfollowing user: {str(e)}", ephemeral=True)

@allowed_everywhere
@tree.command(name='following', description='View users you are following')
async def following_list(ctx: discord.Interaction):
    user = await rotur.get_user_by('discord_id', str(ctx.user.id))
    if user is None or user.get('error') == "User not found":
        await send_message(ctx.response, "You aren't linked to rotur.", ephemeral=True)
        return

    try:
        status, user_data = await rotur.following(user['username'])
        if status == 200 and isinstance(user_data, dict):
            following_list = user_data.get('following', [])
            
            if not following_list:
                await send_message(ctx.response, "You are not following any users.")
                return

            embed = discord.Embed(title="Users You Are Following", description="\n".join(following_list))
            await send_message(ctx.response, embed=embed)
        else:
            await send_message(ctx.response, "Failed to retrieve following list.", ephemeral=True)
    except Exception as e:
        await send_message(ctx.response, f"Error retrieving following list: {str(e)}", ephemeral=True)

@allowed_everywhere
@tree.command(name='subscribe', description='Subscribe to Lite (15 credits per month)')
async def subscribe(ctx: discord.Interaction):
    user = await rotur.get_user_by('discord_id', str(ctx.user.id))
    if user is None or user.get('error') == "User not found":
        await send_message(ctx.response, "You aren't linked to rotur.", ephemeral=True)
        return
    token = user.get("key")
    if not token:
        await send_message(ctx.response, "No auth token found for your account.", ephemeral=True)
        return
    if user.get("sys.subscription", {}).get("tier", "Free") != "Free":
        await send_message(ctx.response, "You already have an active subscription.", ephemeral=True)
        return
    try:
        status, payload = await rotur.keys_buy("4f229157f0c40f5a98cbf28efd39cfe8", token)
        if status == 200:
            await send_message(ctx.response, "You have successfully subscribed to Lite.")
        else:
            err = payload.get('error', 'Unknown error occurred') if isinstance(payload, dict) else 'Unknown error occurred'
            await send_message(ctx.response, f"{err}")
    except Exception as e:
        await send_message(ctx.response, f"Error subscribing to Lite: {str(e)}", ephemeral=True)

@allowed_everywhere
@tree.command(name='unsubscribe', description='Unsubscribe from Lite')
async def unsubscribe(ctx: discord.Interaction):
    user = await rotur.get_user_by('discord_id', str(ctx.user.id))
    if user is None or user.get('error') == "User not found":
        await send_message(ctx.response, "You aren't linked to rotur.", ephemeral=True)
        return
    token = user.get("key")
    if not token:
        await send_message(ctx.response, "No auth token found for your account.", ephemeral=True)
        return
    if user.get("sys.subscription", {}).get("tier", "Free") != "Lite":
        await send_message(ctx.response, "You are not subscribed to Lite.", ephemeral=True)
        return
    try:
        status, payload = await rotur.keys_cancel("4f229157f0c40f5a98cbf28efd39cfe8", token)
        if status == 200:
            await send_message(ctx.response, "You have successfully unsubscribed from Lite.")
        else:
            err = payload.get('error', 'Unknown error occurred') if isinstance(payload, dict) else 'Unknown error occurred'
            await send_message(ctx.response, f"{err}")
    except Exception as e:
        await send_message(ctx.response, f"Error unsubscribing from Lite: {str(e)}", ephemeral=True)

# Marriage Commands Group
marriage = app_commands.Group(name='marriage', description='Commands related to rotur marriage system')
marriage = app_commands.allowed_installs(guilds=True, users=True)(marriage)
marriage = app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)(marriage)
tree.add_command(marriage)

@tree.command(name='blocked', description='View users you are blocking')
async def blocked(ctx: discord.Interaction):
    user = await rotur.get_user_by('discord_id', str(ctx.user.id))
    if user is None or user.get('error') == "User not found":
        await send_message(ctx.response, "You aren't linked to rotur.", ephemeral=True)
        return
    blocked = user.get("sys.blocked")
    if not blocked:
        await send_message(ctx.response, "You are not blocking anyone.")
        return

    embed = discord.Embed(title="Users You Are Blocking", description="\n".join(blocked))
    await send_message(ctx.response, embed=embed)

@tree.command(name='block', description='Block a user on rotur')
@app_commands.describe(username='The username of the user to block')
async def block(ctx: discord.Interaction, username: str):
    user = await rotur.get_user_by('discord_id', str(ctx.user.id))
    if user is None or user.get('error') == "User not found":
        await send_message(ctx.response, "You aren't linked to rotur.", ephemeral=True)
        return
    token = user.get("key")
    if not token:
        await send_message(ctx.response, "No auth token found for your account.", ephemeral=True)
        return
    try:
        await send_message(ctx.response, await rotur.block_user(token, username))
    except Exception as e:
        await send_message(ctx.response, f"Error blocking user: {str(e)}", ephemeral=True)

@allowed_everywhere
@tree.command(name='unblock', description='Unblock a user on rotur')
@app_commands.describe(username='The username of the user to unblock')
async def unblock(ctx: discord.Interaction, username: str):
    user = await rotur.get_user_by('discord_id', str(ctx.user.id))
    if user is None or user.get('error') == "User not found":
        await send_message(ctx.response, "You aren't linked to rotur.", ephemeral=True)
        return
    token = user.get("key")
    if not token:
        await send_message(ctx.response, "No auth token found for your account.", ephemeral=True)
        return
    try:
        await send_message(ctx.response, await rotur.unblock_user(token, username))
    except Exception as e:
        await send_message(ctx.response, f"Error unblocking user: {str(e)}", ephemeral=True)

@allowed_everywhere
@marriage.command(name='propose', description='Propose marriage to another rotur user')
@app_commands.describe(username='Username of the person you want to propose to')
async def marriage_propose(ctx: discord.Interaction, username: str):
    # Get user's rotur account
    user_data = await rotur.get_user_by('discord_id', str(ctx.user.id))
    if user_data is None or user_data.get('error') == "User not found":
        await send_message(ctx.response, 'You are not linked to a rotur account. Please link your account using `/link` command.', ephemeral=True)
        return
    
    auth_key = user_data.get('key')
    if not auth_key:
        await send_message(ctx.response, 'Could not retrieve your authentication key.', ephemeral=True)
        return
    
    # Get target user's rotur account to find their Discord ID
    target_user_data = await rotur.get_user_by('username', username)
    if target_user_data is None or target_user_data.get('error') == "User not found":
        await send_message(ctx.response, f'User **{username}** not found on rotur.', ephemeral=True)
        return
    
    target_discord_id = target_user_data.get('discord_id')
    if not target_discord_id:
        await send_message(ctx.response, f'User **{username}** is not linked to a Discord account.', ephemeral=True)
        return
    
    try:
        # Send proposal request
        status, result = await rotur.marriage_propose(auth_key, username)

        if status == 200:
            # Create buttons for accept/reject that only the target user can use
            view = ProposalView(target_discord_id, user_data.get('username'), username)
            
            # Send embed with buttons to the channel
            embed = discord.Embed(
                title="💍 Marriage Proposal!",
                description=f"**{user_data.get('username')}** has proposed to **{username}**! What do you say?",
                color=discord.Color.pink()
            )
            embed.add_field(
                name="Note", 
                value=f"Only **{username}** can respond to this proposal.",
                inline=False
            )
            
            await send_message(ctx.response, embed=embed, view=view)
        else:
            err = result.get('error', 'Unknown error') if isinstance(result, dict) else 'Unknown error'
            await send_message(ctx.response, f"Error: {err}", ephemeral=True)
    except Exception as e:
        await send_message(ctx.response, f"Error sending proposal: {str(e)}", ephemeral=True)

class ProposalView(discord.ui.View):
    def __init__(self, target_discord_id: str, proposer_username: str, target_username: str):
        super().__init__(timeout=300)  # 5 minute timeout
        self.target_discord_id = target_discord_id
        self.proposer_username = proposer_username
        self.target_username = target_username
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Only allow the target user to interact with the buttons
        if str(interaction.user.id) != self.target_discord_id:
            await interaction.response.send_message("These buttons are not for you!", ephemeral=True)
            return False
        return True
    
    @discord.ui.button(label='Accept 💕', style=discord.ButtonStyle.green)
    async def accept_proposal(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Get user's auth key
        user_data = await rotur.get_user_by('discord_id', str(interaction.user.id))
        if user_data is None or user_data.get('error') == "User not found":
            await interaction.response.send_message('You are not linked to a rotur account.', ephemeral=True)
            return
        
        auth_key = user_data.get('key')
        if not auth_key:
            await interaction.response.send_message('Could not retrieve your authentication key.', ephemeral=True)
            return
        
        try:
            status, result = await rotur.marriage_accept(auth_key)

            if status == 200:
                embed = discord.Embed(
                    title="💕 Marriage Accepted!",
                    description=f"Congratulations! You and **{self.proposer_username}** are now married!",
                    color=discord.Color.green()
                )
                await interaction.response.edit_message(embed=embed, view=None)
                
                # Try to notify the proposer
                try:
                    proposer_data = await rotur.get_user_by('username', self.proposer_username)
                    if proposer_data and proposer_data.get('discord_id'):
                        proposer_user = await client.fetch_user(int(proposer_data.get('discord_id')))
                        if proposer_user:
                            notification_embed = discord.Embed(
                                title="💕 Proposal Accepted!",
                                description=f"**{self.target_username}** accepted your marriage proposal! Congratulations!",
                                color=discord.Color.green()
                            )
                            await proposer_user.send(embed=notification_embed)
                except:
                    pass  # Ignore if we can't notify
            else:
                err = result.get('error', 'Unknown error') if isinstance(result, dict) else 'Unknown error'
                await interaction.response.send_message(f"Error: {err}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Error accepting proposal: {str(e)}", ephemeral=True)
    
    @discord.ui.button(label='Reject 💔', style=discord.ButtonStyle.red)
    async def reject_proposal(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Get user's auth key
        user_data = await rotur.get_user_by('discord_id', str(interaction.user.id))
        if user_data is None or user_data.get('error') == "User not found":
            await interaction.response.send_message('You are not linked to a rotur account.', ephemeral=True)
            return
        
        auth_key = user_data.get('key')
        if not auth_key:
            await interaction.response.send_message('Could not retrieve your authentication key.', ephemeral=True)
            return
        
        try:
            status, result = await rotur.marriage_reject(auth_key)

            if status == 200:
                embed = discord.Embed(
                    title="💔 Marriage Proposal Rejected",
                    description=f"You have rejected **{self.proposer_username}**'s marriage proposal.",
                    color=discord.Color.red()
                )
                await interaction.response.edit_message(embed=embed, view=None)
                
                # Try to notify the proposer
                try:
                    proposer_data = await rotur.get_user_by('username', self.proposer_username)
                    if proposer_data and proposer_data.get('discord_id'):
                        proposer_user = await client.fetch_user(int(proposer_data.get('discord_id')))
                        if proposer_user:
                            notification_embed = discord.Embed(
                                title="💔 Proposal Rejected",
                                description=f"**{self.target_username}** rejected your marriage proposal.",
                                color=discord.Color.red()
                            )
                            await proposer_user.send(embed=notification_embed)
                except:
                    pass  # Ignore if we can't notify
            else:
                err = result.get('error', 'Unknown error') if isinstance(result, dict) else 'Unknown error'
                await interaction.response.send_message(f"Error: {err}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Error rejecting proposal: {str(e)}", ephemeral=True)
    
    async def on_timeout(self):
        # Disable all buttons when view times out
        for item in self.children:
            try:
                setattr(item, "disabled", True)
            except Exception:
                # If the item doesn't support being disabled, ignore it
                continue

@allowed_everywhere
@marriage.command(name='accept', description='Accept your pending marriage proposal')
async def marriage_accept(ctx: discord.Interaction):
    # Get user's rotur account
    user_data = await rotur.get_user_by('discord_id', str(ctx.user.id))
    if user_data is None or user_data.get('error') == "User not found":
        await send_message(ctx.response, 'You are not linked to a rotur account. Please link your account using `/link` command.', ephemeral=True)
        return
    
    auth_key = user_data.get('key')
    if not auth_key:
        await send_message(ctx.response, 'Could not retrieve your authentication key.', ephemeral=True)
        return
    
    try:
        # Accept proposal
        status, result = await rotur.marriage_accept(auth_key)

        if status == 200:
            embed = discord.Embed(
                title="💕 Marriage Accepted!",
                description=f"Congratulations! You and **{result.get('partner')}** are now married!",
                color=discord.Color.green()
            )
            await ctx.response.edit_message(embed=embed, view=None)
        else:
            err = result.get('error', 'Unknown error') if isinstance(result, dict) else 'Unknown error'
            await send_message(ctx.response, f"Error: {err}", ephemeral=True)
    except Exception as e:
        await send_message(ctx.response, f"Error accepting proposal: {str(e)}", ephemeral=True)

@allowed_everywhere
@marriage.command(name='reject', description='Reject your pending marriage proposal')
async def marriage_reject(ctx: discord.Interaction):
    # Get user's rotur account
    user_data = await rotur.get_user_by('discord_id', str(ctx.user.id))
    if user_data is None or user_data.get('error') == "User not found":
        await send_message(ctx.response, 'You are not linked to a rotur account. Please link your account using `/link` command.', ephemeral=True)
        return
    
    auth_key = user_data.get('key')
    if not auth_key:
        await send_message(ctx.response, 'Could not retrieve your authentication key.', ephemeral=True)
        return
    
    try:
        # Reject proposal
        status, result = await rotur.marriage_reject(auth_key)

        if status == 200:
            embed = discord.Embed(
                title="💔 Marriage Proposal Rejected",
                description=f"You have rejected **{result.get('proposer')}**'s marriage proposal.",
                color=discord.Color.red()
            )
            await ctx.response.edit_message(embed=embed, view=None)
        else:
            err = result.get('error', 'Unknown error') if isinstance(result, dict) else 'Unknown error'
            await send_message(ctx.response, f"Error: {err}", ephemeral=True)
    except Exception as e:
        await send_message(ctx.response, f"Error rejecting proposal: {str(e)}", ephemeral=True)

@allowed_everywhere
@marriage.command(name='cancel', description='Cancel your pending marriage proposal')
async def marriage_cancel(ctx: discord.Interaction):
    # Get user's rotur account
    user_data = await rotur.get_user_by('discord_id', str(ctx.user.id))
    if user_data is None or user_data.get('error') == "User not found":
        await send_message(ctx.response, 'You are not linked to a rotur account. Please link your account using `/link` command.', ephemeral=True)
        return
    
    auth_key = user_data.get('key')
    if not auth_key:
        await send_message(ctx.response, 'Could not retrieve your authentication key.', ephemeral=True)
        return
    
    try:
        # Cancel proposal
        status, result = await rotur.marriage_cancel(auth_key)

        if status == 200:
            embed = discord.Embed(
                title="Proposal Cancelled",
                description="You have cancelled your marriage proposal.",
                color=discord.Color.orange()
            )
            await send_message(ctx.response, embed=embed)
        else:
            err = result.get('error', 'Unknown error') if isinstance(result, dict) else 'Unknown error'
            await send_message(ctx.response, f"Error: {err}", ephemeral=True)
    except Exception as e:
        await send_message(ctx.response, f"Error cancelling proposal: {str(e)}", ephemeral=True)

@allowed_everywhere
@marriage.command(name='divorce', description='Divorce your current spouse')
async def marriage_divorce(ctx: discord.Interaction):
    # Get user's rotur account
    user_data = await rotur.get_user_by('discord_id', str(ctx.user.id))
    if user_data is None or user_data.get('error') == "User not found":
        await send_message(ctx.response, 'You are not linked to a rotur account. Please link your account using `/link` command.', ephemeral=True)
        return
    
    auth_key = user_data.get('key')
    if not auth_key:
        await send_message(ctx.response, 'Could not retrieve your authentication key.', ephemeral=True)
        return
    
    try:
        # Divorce request
        status, result = await rotur.marriage_divorce(auth_key)

        if status == 200:
            embed = discord.Embed(
                title="💔 Divorce Processed",
                description="You are now divorced.",
                color=discord.Color.orange()
            )
            await send_message(ctx.response, embed=embed)
        else:
            err = result.get('error', 'Unknown error') if isinstance(result, dict) else 'Unknown error'
            await send_message(ctx.response, f"Error: {err}", ephemeral=True)
    except Exception as e:
        await send_message(ctx.response, f"Error processing divorce: {str(e)}", ephemeral=True)

@allowed_everywhere
@marriage.command(name='status', description='Check your marriage status')
async def marriage_status(ctx: discord.Interaction):
    # Get user's rotur account
    user_data = await rotur.get_user_by('discord_id', str(ctx.user.id))
    if user_data is None or user_data.get('error') == "User not found":
        await send_message(ctx.response, 'You are not linked to a rotur account. Please link your account using `/link` command.', ephemeral=True)
        return
    
    auth_key = user_data.get('key')
    if not auth_key:
        await send_message(ctx.response, 'Could not retrieve your authentication key.', ephemeral=True)
        return
    
    try:
        # Get marriage status
        status, result = await rotur.marriage_status(auth_key)

        if status == 200 and isinstance(result, dict):
            status = result.get('status', 'single')
            partner = result.get('partner', '')
            
            if status == 'single':
                embed = discord.Embed(
                    title="💔 Single",
                    description="You are currently single and available for marriage.",
                    color=discord.Color.blue()
                )
            elif status == 'proposed':
                proposer = result.get('proposer', '')
                if user_data.get('username') == proposer:
                    embed = discord.Embed(
                        title="💍 Proposal Sent",
                        description=f"You have sent a marriage proposal to **{partner}**. Waiting for their response.",
                        color=discord.Color.yellow()
                    )
                else:
                    embed = discord.Embed(
                        title="💍 Proposal Received",
                        description=f"**{partner}** has proposed to you! Check your DMs for buttons to accept or reject.",
                        color=discord.Color.yellow()
                    )
            elif status == 'married':
                embed = discord.Embed(
                    title="💕 Married",
                    description=f"You are married to **{partner}**!",
                    color=discord.Color.pink()
                )
            else:
                embed = discord.Embed(
                    title="❓ Unknown Status",
                    description=f"Marriage status: {status}",
                    color=discord.Color.greyple()
                )
            
            await send_message(ctx.response, embed=embed)
        else:
            err = result.get('error', 'Unknown error') if isinstance(result, dict) else 'Unknown error'
            await send_message(ctx.response, f"Error: {err}", ephemeral=True)
    except Exception as e:
        await send_message(ctx.response, f"Error checking marriage status: {str(e)}", ephemeral=True)

@tree.command(name='here', description='Ping people in your thread')
async def here(ctx: discord.Interaction):
    if ctx.guild is None or ctx.channel is None or str(ctx.guild.id) != originOS:
        return

    #check if the user owns the curreny thread
    if ctx.channel.type != discord.ChannelType.public_thread and ctx.channel.type != discord.ChannelType.private_thread:
        await send_message(ctx.response, "This command can only be used in a thread.", ephemeral=True)
        return

    if ctx.channel.owner_id != ctx.user.id:
        await send_message(ctx.response, "You do not own this thread.", ephemeral=True)
        return
    
    await send_message(ctx.response, "@here", allowed_mentions=discord.AllowedMentions(everyone=True))

@allowed_everywhere
@tree.command(name='personalities', description='List all available roturbot personalities')
async def list_personalities(ctx: discord.Interaction):
    personalities = load_personalities()
    if not personalities:
        await send_message(ctx.response, "No personalities available.")
        return

    current_personality = get_user_personality(ctx.user.id)
    
    user = await rotur.get_user_by('discord_id', str(ctx.user.id))
    tier = user.get('sys.subscription', {}).get('tier', 'Free') if user and user.get('error') is None else 'Free'

    embed = discord.Embed(
        title="🎭 Roturbot Personalities",
        description="Choose a personality for roturbot to use when talking to you!",
        color=discord.Color.purple()
    )

    for name in sorted(personalities.keys()):
        status = " (currently selected)" if name == current_personality else ""
        requirements = get_tier_requirements(name)
        
        if requirements:
            access_info = f"\n*(Requires: {requirements[0]}+)*"
            has_access = has_access_to_personality(tier, name)
            if not has_access:
                access_info += " - Locked"
        else:
            access_info = ""
        
        embed.add_field(
            name=f"{name}{status}",
            value=f"{access_info}\n\nUse `/set_personality {name}` to select",
            inline=False
        )

    await send_message(ctx.response, embed=embed, ephemeral=True)

@allowed_everywhere
@tree.command(name='set_personality', description='Set roturbot personality for your conversations')
@app_commands.describe(personality='The personality to use')
async def set_personality(ctx: discord.Interaction, personality: str):
    personalities = load_personalities()
    if personality not in personalities:
        available = ", ".join(personalities.keys())
        await send_message(ctx.response, f"Personality '{personality}' not found. Available personalities: {available}", ephemeral=True)
        return

    requirements = get_tier_requirements(personality)
    if requirements:
        user = await rotur.get_user_by('discord_id', str(ctx.user.id))
        if user is None or user.get('error') is not None:
            await send_message(ctx.response, "You need to link your rotur account to use premium personalities.", ephemeral=True)
            return
        
        tier = user.get('sys.subscription', {}).get('tier', 'Free')
        if not has_access_to_personality(tier, personality):
            await send_message(ctx.response, f"The **{personality}** personality requires a {requirements[0]} subscription or higher. Subscribe at https://ko-fi.com/mistium", ephemeral=True)
            return

    if set_user_personality(ctx.user.id, personality):
        await send_message(ctx.response, f"Personality set to **{personality}**! I'll talk to you differently now :P", ephemeral=True)
    else:
        await send_message(ctx.response, "Failed to set personality. Please try again.", ephemeral=True)

@allowed_everywhere
@tree.command(name='my_personality', description='View your current roturbot personality')
async def my_personality(ctx: discord.Interaction):
    current = get_user_personality(ctx.user.id)
    await send_message(ctx.response, f"Your current personality is **{current}** :P")

@allowed_everywhere
@tree.command(name='most_true', description='Show top 10 most true messages')
async def most_true(ctx: discord.Interaction):
     
     try:
        await ctx.response.defer()
        stats = reactionStorage.load_reaction_stats() or {}

        cur_emoji = "✅"
        neg_emoji = "❌"

        entries: list[tuple[str, int, dict]] = []
        for link, reacts in stats.items():
            if not isinstance(reacts, dict):
                continue
            count = int(reacts.get(cur_emoji, 0) or 0) - int(reacts.get(neg_emoji, 0) or 0)
            if count > 0:
                entries.append((link, count, reacts))

        if not entries:
            await send_message(ctx.followup, f"No messages have received any {cur_emoji} reactions yet.", ephemeral=True)
            return

        entries.sort(key=lambda e: e[1], reverse=True)
        top = entries[:10]

        embed = discord.Embed(title="Most True Messages", description=f"Messages with the most {cur_emoji} reactions", color=discord.Color.green())
        for i, (link, count, reacts) in enumerate(top, start=1):
            value = _format_entry(link, count, reacts, cur_emoji)
            embed.add_field(name=f"#{i}", value=value, inline=False)

        await send_message(ctx.followup, embed=embed)
     except Exception as e:
        await send_message(ctx.followup, f"Error generating leaderboard: {str(e)}", ephemeral=True)

@allowed_everywhere
@tree.command(name='most_false', description='Show top 10 most false messages')
async def most_false(ctx: discord.Interaction):
    try:
        await ctx.response.defer()
        stats = reactionStorage.load_reaction_stats() or {}

        cur_emoji = "❌"
        neg_emoji = "✅"

        entries: list[tuple[str, int, dict]] = []
        for link, reacts in stats.items():
            if not isinstance(reacts, dict):
                continue
            count = int(reacts.get(cur_emoji, 0) or 0) - int(reacts.get(neg_emoji, 0) or 0)
            if count > 0:
                entries.append((link, count, reacts))

        if not entries:
            await send_message(ctx.followup, f"No messages have received any {cur_emoji} reactions yet.", ephemeral=True)
            return

        entries.sort(key=lambda e: e[1], reverse=True)
        top = entries[:10]

        embed = discord.Embed(title="Most False Messages", description=f"Messages with the most {cur_emoji} reactions", color=discord.Color.red())
        for i, (link, count, reacts) in enumerate(top, start=1):
            # Use the same formatting helper as most_true for consistency
            value = _format_entry(link, count, reacts, cur_emoji)
            embed.add_field(name=f"#{i}", value=value, inline=False)

        await send_message(ctx.followup, embed=embed)
    except Exception as e:
        await send_message(ctx.followup, f"Error generating leaderboard: {str(e)}", ephemeral=True)

@allowed_everywhere
@tree.command(name='link', description='[EPHEMERAL] Link your Discord account to your rotur account')
@app_commands.describe(username='Your rotur username', password='Your rotur password')
async def link(ctx: discord.Interaction, username: str, password: str):
    user = await rotur.get_user_by('discord_id', str(ctx.user.id))
    if user and user.get('error') != "User not found":
        await send_message(ctx.response, "You are already linked to a rotur account.", ephemeral=True)
        return
    hashed_password = hashlib.md5(password.encode()).hexdigest()
    _, user = await rotur.get_user_login(username, hashed_password)
    token = user.get("key") if isinstance(user, dict) else None
    if not token:
        err = user.get('error', 'Unknown error occurred.') if isinstance(user, dict) else 'Unknown error occurred.'
        await send_message(ctx.response, err, ephemeral=True)
        return
    try:
        resp = await rotur.update_user("update", user.get('username'), "discord_id", str(ctx.user.id))
        if not resp.get("error"):
            await send_message(ctx.response, "Your Discord account has been linked to your rotur account.", ephemeral=True)
        else:
            await send_message(ctx.response, f"Failed to link account. Server responded with: {resp.get("error")}.", ephemeral=True)
    except Exception as e:
        await send_message(ctx.response, f"Error linking account: {str(e)}", ephemeral=True)
    return

@tree.command(name='icon', description='Render an icn file')
@app_commands.describe(icon='The icn file to render', size='The size of the icon')
async def icon(ctx: discord.Interaction, icon: str, size: float):
    try:
        icon = icon.strip()
        if not icon:
            await send_message(ctx.response, "Icon is required", ephemeral=True)
            return
        
        size = float(size)
        if size <= 0:
            await send_message(ctx.response, "Size must be greater than 0", ephemeral=True)
            return
        
        width = 500
        height = 500
        
        img = icn.draw(icon, width=width, height=height, scale=size)
        buffer = BytesIO()
        img.save(buffer, format="png")
        buffer.seek(0)
        file = discord.File(buffer, filename="icn.png")
        await send_message(ctx.response, file=file)
    except Exception as e:
        await send_message(ctx.response, f"Error rendering icon: {str(e)}", ephemeral=True)

@allowed_everywhere
@tree.command(name='unlink', description='[EPHEMERAL] Unlink your Discord account from your rotur account')
async def unlink(ctx: discord.Interaction):
    user = await rotur.get_user_by('discord_id', str(ctx.user.id))
    if user.get('error') == "User not found" or user is None:
        await send_message(ctx.response, "You aren't linked to rotur.", ephemeral=True)
        return
    token = user.get("key")
    if not token:
        await send_message(ctx.response, "No auth token found for your account.", ephemeral=True)
        return
    try:
        resp = await rotur.update_user("update", user.get('username'), "discord_id", "")
        if not resp.get("error"):
            await send_message(ctx.response, "Your Discord account has been unlinked from your rotur account.", ephemeral=True)
        else:
            await send_message(ctx.response, f"Failed to unlink account. Server responded with: {resp.get("error")}.", ephemeral=True)
    except Exception as e:
        await send_message(ctx.response, f"Error unlinking account: {str(e)}", ephemeral=True)
    return

@allowed_everywhere
@tree.command(name='refresh_token', description='[EPHEMERAL] Refresh (rotate) your rotur auth token')
async def refresh_token_cmd(ctx: discord.Interaction):
    """Rotate the user's rotur auth token via the /me/refresh_token endpoint.

    Returns an ephemeral confirmation and (for convenience) the first / last characters
    of the new token so the user can verify rotation without fully exposing it in logs.
    """
    user = await rotur.get_user_by('discord_id', str(ctx.user.id))
    if user is None or user.get('error') == 'User not found':
        await send_message(ctx.response, "You aren't linked to rotur.", ephemeral=True)
        return

    old_token = user.get('key')
    if not old_token:
        await send_message(ctx.response, "No auth token found for your account.", ephemeral=True)
        return

    try:
        status, payload = await rotur.refresh_token(old_token)
    except Exception as e:
        await send_message(ctx.response, f"Error contacting server: {str(e)}", ephemeral=True)
        return

    if status != 200 or (isinstance(payload, dict) and payload.get('error')):
        err = payload.get('error', f'Server responded with status {status}.') if isinstance(payload, dict) else f'Server responded with status {status}.'
        await send_message(ctx.response, f"Failed to refresh token: {err}", ephemeral=True)
        return

    try:
        updated = await rotur.get_user_by('discord_id', str(ctx.user.id))
    except Exception:
        updated = None

    new_token = None
    if updated and not updated.get('error'):
        new_token = updated.get('key')

    def mask(tok: str | None):
        if not tok:
            return 'unavailable'
        if len(tok) <= 10:
            return tok
        return tok[:4] + '...' + tok[-4:]

    embed = discord.Embed(
        title='Token Refreshed',
        description='Your rotur authentication token has been rotated successfully.',
        color=discord.Color.green()
    )
    embed.add_field(name='Old Token (masked)', value=mask(old_token), inline=False)
    embed.add_field(name='New Token (masked)', value=mask(new_token), inline=False)
    if new_token == old_token:
        embed.add_field(name='Notice', value='The token appears unchanged. If this persists, try again later.', inline=False)
    else:
        embed.add_field(name='Usage', value='Your token is now refreshed.', inline=False)

    await send_message(ctx.response, embed=embed, ephemeral=True)
    return

@allowed_everywhere
@tree.command(name='syncpfp', description='syncs your pfp from discord to rotur')
async def syncpfp(ctx: discord.Interaction):
    # Acknowledge immediately to avoid 3s interaction timeout
    try:
        await ctx.response.defer(ephemeral=True, thinking=True)
    except Exception:
        pass

    user = await rotur.get_user_by('discord_id', str(ctx.user.id))
    if user is None or user.get('error') == "User not found":
        await send_message(ctx.followup, "You aren't linked to rotur.", ephemeral=True)
        return
    token = user.get("key")
    if not token:
        await send_message(ctx.followup, "No auth token found for your account.", ephemeral=True)
        return
    try:
        # Fetch user's Discord avatar bytes
        asset = str(ctx.user.display_avatar)
        async with aiohttp.ClientSession() as session:
            async with session.get(asset, timeout=aiohttp.ClientTimeout(total=15)) as r:
                r.raise_for_status()
                avatar_bytes = await r.read()

        b64_avatar = base64.b64encode(avatar_bytes).decode("utf-8")
        data_url = f"data:{r.content_type};base64,{b64_avatar}"

        payload = {"token": token, "image": data_url}

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{avatars_api_base}/rotur-upload-pfp?ADMIN_TOKEN={os.getenv('ADMIN_TOKEN')}",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                if resp.status == 200:
                    await send_message(ctx.followup, "Your profile picture has been synced to rotur.", ephemeral=True)
                else:
                    await send_message(ctx.followup,
                        f"Failed to sync profile picture. Server responded with status {resp.status}, message: {await resp.text()}",
                        ephemeral=True,
                    )
            await rotur.update_user("update", user.get("username"), "pfp", f"{user.get('username')}?nocache={randomString(5)}")
    except Exception as e:
        # Use followup since we've already deferred
        await send_message(ctx.followup, f"Error syncing profile picture: {str(e)}", ephemeral=True)
    return

@allowed_everywhere
@tree.command(name='gamble', description='Gamble your credits for a chance to win more')
async def gamble(ctx: discord.Interaction, amount: float):
    await send_message(ctx.response, "This command is currently disabled. If you want more credits: https://ko-fi.com/s/eebeb7269f")
    return

@allowed_everywhere
@tree.command(name='allkeys', description='Get a list of all the keys in your account')
async def all_keys(ctx: discord.Interaction):
    user = await rotur.get_user_by('discord_id', str(ctx.user.id))
    if user is None or user.get('error') == "User not found":
        await send_message(ctx.response, "You aren't linked to rotur.", ephemeral=True)
        return
    
    token = user.get("key")
    if not token:
        await send_message(ctx.response, "No auth token found for your account.", ephemeral=True)
        return
    
    try:
        keys = {k: v for k, v in user.items() if k not in ['username', 'discord_id', 'key', 'pfp', 'banner']}
        if not keys:
            await send_message(ctx.response, "No keys found in your account.", ephemeral=True)
            return
        lines = [f"{key}, " for key, value in keys.items()]
        await send_message(ctx.response, "```\n" + "".join(lines) + "\n```")
    except Exception as e:
        await send_message(ctx.response, f"Error retrieving keys: {str(e)}", ephemeral=True)

@allowed_everywhere
@tree.command(name='created', description='Get the creation date of your account')
async def created(ctx: discord.Interaction):
    user = await rotur.get_user_by('discord_id', str(ctx.user.id))
    if user is None or user.get('error') == "User not found":
        await send_message(ctx.response, "You aren't linked to rotur.", ephemeral=True)
        return

    created_at = user.get('created', "Unknown")
    if not isinstance(created_at, (int, float)):
        await send_message(ctx.response, "Invalid creation date format.")
        return

    embed = discord.Embed(
        title="Account Information",
        description=f"Your account was created on: <t:{round(created_at / 1000)}:f>",
        color=discord.Color.green()
    )
    await send_message(ctx.response, embed=embed)

@allowed_everywhere
@tree.command(name='balance', description='Check your current credit balance')
async def balance(ctx: discord.Interaction):
    user = await rotur.get_user_by('discord_id', str(ctx.user.id))
    if user is None or user.get('error') == "User not found":
        await send_message(ctx.response, "You aren't linked to rotur.", ephemeral=True)
        return
    
    balance = user.get('sys.currency', 0)
    embed = discord.Embed(
        title=f"You have {balance} credits",
    )
    await send_message(ctx.response, embed=embed)

@allowed_everywhere
@transfer.command(name='rotur', description='Transfer credits to another user')
async def transfer_credits(ctx: discord.Interaction, username: str, amount: float, note: str = ""):
    user = await rotur.get_user_by('discord_id', str(ctx.user.id))
    if user is None or user.get('error') == "User not found":
        await send_message(ctx.response, "You aren't linked to rotur.", ephemeral=True)
        return

    token = user.get("key")
    if not token:
        await send_message(ctx.response, "No auth token found for your account.", ephemeral=True)
        return

    try:
        status, payload = await rotur.transfer(token, username, amount, note)
        if status == 200:
            await send_message(ctx.response, f"Successfully transferred {amount} credits to {username}." + (f"\nNote: {note}" if note else ""))
        else:
            err = payload.get('error', 'Unknown error occurred') if isinstance(payload, dict) else 'Unknown error occurred'
            await send_message(ctx.response, f"{err}", ephemeral=True)
    except Exception as e:
        await send_message(ctx.response, f"Error transferring credits: {str(e)}", ephemeral=True)

@allowed_everywhere
@transfer.command(name='discord', description='Transfer credits to a Discord user')
async def transfer_discord(ctx: discord.Interaction, discord_user: discord.User, amount: float, note: str = ""):
    user = await rotur.get_user_by('discord_id', str(ctx.user.id))
    if user is None or user.get('error') == "User not found":
        await send_message(ctx.response, "You aren't linked to rotur.", ephemeral=True)
        return
    to_user = await rotur.get_user_by('discord_id', str(discord_user.id))
    if to_user is None or to_user.get('error') == "User not found":
        await send_message(ctx.response, "Recipient user is not linked to rotur.", ephemeral=True)
        return

    token = user.get("key")
    if not token:
        await send_message(ctx.response, "No auth token found for your account.")
        return

    try:
        status, payload = await rotur.transfer(token, to_user["username"], amount, note)
        if status == 200:
            await send_message(ctx.response, f"Successfully transferred {amount} credits to {to_user['username']}." + (f"\nNote: {note}" if note else ""))
        else:
            err = payload.get('error', 'Unknown error occurred') if isinstance(payload, dict) else 'Unknown error occurred'
            await send_message(ctx.response, f"{err}", ephemeral=True)
    except Exception as e:
        await send_message(ctx.response, f"Error transferring credits: {str(e)}")

@allowed_everywhere
@keys.command(name='set', description='Set a key in your account')
@app_commands.describe(key='The key to set', value='The value of the key')
async def set_key(ctx: discord.Interaction, key: str, value: str):
    user = await rotur.get_user_by('discord_id', str(ctx.user.id))
    if user is None or user.get('error') == "User not found":
        await send_message(ctx.response, "You aren't linked to rotur.", ephemeral=True)
        return

    token = user.get("key")
    if not token:
        await send_message(ctx.response, "No auth token found for your account.", ephemeral=True)
        return

    try:
        status, payload = await rotur.users_patch(token, key, value)
        if status == 200:
            await send_message(ctx.response, f"Key '{key}' set to '{value}'.")
        else:
            err = payload.get('error', 'Unknown error occurred') if isinstance(payload, dict) else 'Unknown error occurred'
            await send_message(ctx.response, f"{err}", ephemeral=True)
    except Exception as e:
        await send_message(ctx.response, f"Error setting key: {str(e)}", ephemeral=True)

@allowed_everywhere
@keys.command(name='del', description='Delete a key from your account')
@app_commands.describe(key='The key to delete')
async def del_key(ctx: discord.Interaction, key: str):
    user = await rotur.get_user_by('discord_id', str(ctx.user.id))
    if user is None or user.get('error') == "User not found":
        await send_message(ctx.response, "You aren't linked to rotur.", ephemeral=True)
        return
    
    token = user.get("key")
    if not token:
        await send_message(ctx.response, "No auth token found for your account.", ephemeral=True)
        return

    try:
        status, _payload = await rotur.users_delete(token, key)
        if status == 204:
            await send_message(ctx.response, f"Key '{key}' deleted successfully.")
        else:
            await send_message(ctx.response, f"Failed to delete key '{key}'. Server responded with status {status}.", ephemeral=True)
    except Exception as e:
        await send_message(ctx.response, f"Error deleting key: {str(e)}", ephemeral=True)

@allowed_everywhere
@keys.command(name='get', description='Get a key from your account')
@app_commands.describe(key='The key to get')
async def get_key(ctx: discord.Interaction, key: str):
    user = await rotur.get_user_by('discord_id', str(ctx.user.id))
    if user is None or user.get('error') == "User not found":
        await send_message(ctx.response, "You aren't linked to rotur.", ephemeral=True)
        return
    
    if key not in user:
        await send_message(ctx.response, f"Key '{key}' not found in your account.", ephemeral=True)
        return

    if key in ["key", "password"]:
        await send_message(ctx.response, f"You cannot display this key, it contains sensitive information", ephemeral=True)
    
    value = user[key]
    embed = discord.Embed(
        title=f"Key: {key}",
        description=f"{value}",
        color=discord.Color.blue()
    )
    await send_message(ctx.response, embed=embed)

@allowed_everywhere
@tree.command(name='tod', description='Play truth or dare')
@app_commands.describe(mode="Choose 'truth' or 'dare'")
@app_commands.choices(mode=[
    app_commands.Choice(name='Truth', value='truth'),
    app_commands.Choice(name='Dare', value='dare')
])
async def tod(ctx: discord.Interaction, mode: str = 'truth'):
    try:
        response = requests.get(f'https://api.truthordarebot.xyz/v1/{mode}')
        if response.status_code == 200:
            data = response.json()
            question = data.get('question', 'No question available')
            
            embed = discord.Embed(
                title=f"{mode.capitalize()} for {ctx.user.display_name}",
                description=question,
                color=0x00ff00 if mode == 'truth' else 0xff0000
            )
            await send_message(ctx.response, embed=embed)
        else:
            await send_message(ctx.response, "Sorry, couldn't fetch a question right now.", ephemeral=True)
    except Exception as e:
        await send_message(ctx.response, "An error occurred while fetching the question.", ephemeral=True)

@allowed_everywhere
@tree.command(name='quote', description='Generate a quote image from a message')
@app_commands.describe(message_id='The ID of the message to quote')
async def quote_command(ctx: discord.Interaction, message_id: str):
    try:
        await ctx.response.defer()
        
        channel = ctx.channel
        if channel is None or not hasattr(channel, "fetch_message"):
            await send_message(ctx.followup, "❌ This channel does not support fetching messages (e.g. Category/Forum or no context); please run this in a text channel and provide a valid message ID.", ephemeral=True)
            return

        try:
            if isinstance(channel, discord.ForumChannel) or isinstance(channel, discord.CategoryChannel):
                return
            message = await channel.fetch_message(int(message_id))
        except ValueError:
            await send_message(ctx.followup, "❌ Invalid message ID.", ephemeral=True)
            return
        except discord.NotFound:
            await send_message(ctx.followup, "❌ Message not found.", ephemeral=True)
            return
        except discord.Forbidden:
            await send_message(ctx.followup, "❌ No permission to access that message.", ephemeral=True)
            return
        except Exception as e:
            print(f"Error fetching message: {e}")
            await send_message(ctx.followup, "❌ An error occurred while fetching the message.", ephemeral=True)
            return

        if message.author.bot:
            await send_message(ctx.followup, "❌ Cannot quote bot messages.", ephemeral=True)
            return
        
        quote_image = await quote_generator.generate_quote_image(
            author_name=message.author.name,
            author_avatar_url=str(message.author.display_avatar.url),
            message_content=message.content or "[No text content]",
            timestamp=message.created_at
        )
        
        if quote_image:
            await ctx.followup.send(
                file=discord.File(quote_image, filename="quote.png")
            )
        else:
            await send_message(ctx.followup, "❌ Failed to generate quote image.", ephemeral=True)
            
    except ValueError:
        await send_message(ctx.followup, "❌ Invalid message ID.", ephemeral=True)
    except discord.NotFound:
        await send_message(ctx.followup, "❌ Message not found.", ephemeral=True)
    except discord.Forbidden:
        await send_message(ctx.followup, "❌ No permission to access that message.", ephemeral=True)
    except Exception as e:
        print(f"Error in quote command: {e}")
        await send_message(ctx.followup, "❌ An error occurred while generating the quote.", ephemeral=True)

@allowed_everywhere
@tree.command(name='accorigins', description='Get stats on how many accounts are linked to each rotur OS')
async def accorigins(ctx: discord.Interaction):
    _, system_stats = await rotur.stats_systems()
    embed = discord.Embed(title="Account Origins", color=discord.Color.blue())
    
    if not system_stats or not isinstance(system_stats, dict):
        await send_message(ctx.response, "Error fetching system statistics.")
        return
    
    total = sum(system_stats.values())
    sorted_stats = sorted(system_stats.items(), key=lambda x: x[1], reverse=True)
    
    for system, count in sorted_stats:
        percentage = (count / total * 100) if total else 0
        embed.add_field(
            name=f"{system}",
            value=f"{count} users ({percentage:.1f}%)",
            inline=True
        )
    
    embed.set_footer(text=f"Total: {total} users")
    await send_message(ctx.response, embed=embed)

@allowed_everywhere
@tree.command(name='counting', description='Get counting statistics for the current channel')
async def counting_stats(ctx: discord.Interaction):
    if ctx.channel is None:
        await send_message(ctx.response, "This command can only be used in a channel!", ephemeral=True)
        return
    await ctx.response.defer(thinking=True)

    channel_id = str(ctx.channel.id)

    if channel_id != counting.COUNTING_CHANNEL_ID:
        await send_message(ctx.followup, "This command only works in the counting channel!", ephemeral=True)
        return

    try:
        stats = counting.get_counting_stats(channel_id)
    except Exception as e:
        await send_message(ctx.followup, f"❌ Error reading counting stats: {e}", ephemeral=True)
        return

    embed = discord.Embed(
        title="🔢 Counting Statistics",
        color=discord.Color.green()
    )

    embed.add_field(
        name="Current Count",
        value=f"**{stats['current_count']}**",
        inline=True
    )

    embed.add_field(
        name="Next Number",
        value=f"**{stats['next_number']}**",
        inline=True
    )

    embed.add_field(
        name="Highest Count",
        value=f"**{stats['highest_count']}**",
        inline=True
    )

    embed.add_field(
        name="Total Counts",
        value=f"**{stats['total_counts']}**",
        inline=True
    )

    embed.add_field(
        name="Unique Counters",
        value=f"**{stats.get('unique_counters', 0)}**",
        inline=True
    )

    embed.add_field(
        name="Resets",
        value=f"**{stats.get('resets', 0)}**",
        inline=True
    )

    top_counters = stats.get('top_counters', [])
    if top_counters:
        lines = []
        for idx, entry in enumerate(top_counters, start=1):
            uid = entry.get('user_id')
            display_name = uid
            try:
                user = await client.fetch_user(int(uid))
                display_name = f"{user.name}#{user.discriminator}" if getattr(user, 'discriminator', None) else user.name
            except Exception:
                try:
                    rot = await rotur.get_user_by('discord_id', str(uid))
                    if rot and not rot.get('error'):
                        display_name = rot.get('username', uid)
                except Exception:
                    pass
            lines.append(f"{idx}. {display_name} — {entry.get('counts', 0)}")
        embed.add_field(name="🏅 Top Counters", value="\n".join(lines), inline=False)
    else:
        embed.add_field(name="🏅 Top Counters", value="No data yet", inline=False)

    top_failers = stats.get('top_failers', [])
    if top_failers:
        lines = []
        for idx, entry in enumerate(top_failers, start=1):
            uid = entry.get('user_id')
            display_name = uid
            try:
                user = await client.fetch_user(int(uid))
                display_name = f"{user.name}#{user.discriminator}" if getattr(user, 'discriminator', None) else user.name
            except Exception:
                try:
                    rot = await rotur.get_user_by('discord_id', str(uid))
                    if rot and not rot.get('error'):
                        display_name = rot.get('username', uid)
                except Exception:
                    pass
            lines.append(f"{idx}. {display_name} — {entry.get('fails', 0)}")
        embed.add_field(name="💥 Top Failers", value="\n".join(lines), inline=False)
    else:
        embed.add_field(name="💥 Top Failers", value="No data yet", inline=False)

    embed.set_footer(text="Only users with rotur accounts can participate!")

    await send_message(ctx.followup, embed=embed)

@allowed_everywhere
@tree.command(name='reset_counting', description='Reset the counting (Admin only)')
async def reset_counting(ctx: discord.Interaction):
    if str(ctx.user.id) != mistium:  # Only mistium can reset
        await send_message(ctx.response, "❌ Only administrators can reset the counting!", ephemeral=True)
        return
    
    if ctx.channel is None:
        await send_message(ctx.response, "This command can only be used in a channel!", ephemeral=True)
        return
        
    channel_id = str(ctx.channel.id)
    
    if channel_id != counting.COUNTING_CHANNEL_ID:
        await send_message(ctx.response, "This command only works in the counting channel!", ephemeral=True)
        return
    
    state = counting.get_channel_state(channel_id)
    old_count = state["current_count"]
    state["current_count"] = 0
    state["last_user"] = None
    counting.save_state()
    
    embed = discord.Embed(
        title="🔄 Counting Reset",
        description=f"The counting has been reset by {ctx.user.mention}!\nPrevious count: **{old_count}**\nStart counting from **1**!",
        color=discord.Color.orange()
    )
    
    await send_message(ctx.response, embed=embed)

@allowed_everywhere
@tree.command(name='counting_help', description='Learn how the counting game works')
async def counting_help(ctx: discord.Interaction):
    embed = discord.Embed(
        title="🔢 Counting Game Rules",
        description="Welcome to the counting game! Here's how it works:",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="📝 Basic Rules",
        value=(
            "• Count upwards starting from 1\n"
            "• Each person can only count once in a row\n"
            "• Must have a rotur account to participate\n"
            "• Math expressions are allowed (e.g., `2+3` for 5)"
        ),
        inline=False
    )
    
    embed.add_field(
        name="❌ What Resets the Count",
        value=(
            "• Wrong number (unless same person who just counted)\n"
            "• Anyone without a rotur account posting\n"
            "• Non-numeric messages in the counting channel"
        ),
        inline=False
    )
    
    embed.add_field(
        name="✅ Allowed Math",
        value=(
            "• Basic operators: `+`, `-`, `*`, `/`, `%`, `**`\n"
            "• Functions: `abs()`, `round()`, `min()`, `max()`, `sum()`\n"
            "• Examples: `2*3`, `10/2`, `abs(-7)`, `round(4.7)`"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🏆 Channel",
        value=f"Play in <#{counting.COUNTING_CHANNEL_ID}>",
        inline=False
    )
    
    embed.set_footer(text="Link your rotur account using /link")
    
    await send_message(ctx.response, embed=embed, ephemeral=True)

@allowed_everywhere
@tree.command(name='activity_alert', description='Toggle activity alerts for role changes')
async def activity_alert(ctx: discord.Interaction):
    user_id = ctx.user.id
    is_excluded = toggle_user_exclusion(user_id)
    
    if is_excluded:
        embed = discord.Embed(
            title="🔕 Activity Alerts Disabled",
            description="You will no longer receive notifications when your roles change and affect your rotur credit earnings.",
            color=discord.Color.orange()
        )
    else:
        embed = discord.Embed(
            title="🔔 Activity Alerts Enabled", 
            description="You will now receive notifications when your roles change and affect your rotur credit earnings.",
            color=discord.Color.green()
        )
    
    await send_message(ctx.response, embed=embed, ephemeral=True)

@allowed_everywhere
@tree.command(name='daily_credit_dm', description='Toggle receiving a DM when daily credits are awarded (opt-in)')
async def daily_credit_dm(ctx: discord.Interaction):
    enabled = toggle_daily_credit_dm_optin(ctx.user.id)
    if enabled:
        embed = discord.Embed(
            title="✅ Daily Credit DMs Enabled",
            description="You will receive a DM when your daily credits are awarded (at midnight UTC).",
            color=discord.Color.green()
        )
    else:
        embed = discord.Embed(
            title="🔕 Daily Credit DMs Disabled",
            description="You will no longer receive daily credit award DMs.",
            color=discord.Color.orange()
        )
    embed.set_footer(text="Use /daily_credit_dm again to toggle.")
    await send_message(ctx.response, embed=embed, ephemeral=True)

@allowed_everywhere
@tree.command(name='levelup_messages', description='Toggle level-up notification messages')
async def levelup_messages(ctx: discord.Interaction):
    if not XP_SYSTEM_ENABLED or not xp_system:
        await send_message(ctx.response, "The XP system is currently disabled.", ephemeral=True)
        return
    
    enabled = xp_system.toggle_levelup_message(ctx.user.id)
    if enabled:
        embed = discord.Embed(
            title="Level-Up Messages Enabled",
            description="You will receive a message when you level up.",
            color=discord.Color.green()
        )
    else:
        embed = discord.Embed(
            title="Level-Up Messages Disabled",
            description="You will no longer receive level-up messages.",
            color=discord.Color.orange()
        )
    embed.set_footer(text="Use /levelup_messages again to toggle.")
    await send_message(ctx.response, embed=embed, ephemeral=True)

@allowed_everywhere
@tree.command(name='process_daily_credits', description='[Admin] Manually reset daily credits and announce new day')
async def manual_daily_credits(ctx: discord.Interaction):
    if str(ctx.user.id) != mistium:
        await send_message(ctx.response, "❌ Only administrators can run this command!", ephemeral=True)
        return
    
    await ctx.response.defer()
    
    try:
        await process_daily_credits()
        embed = discord.Embed(
            title="✅ Daily Credits Reset",
            description="Daily credits have been reset and new day announced!",
            color=discord.Color.green()
        )
        await ctx.followup.send(embed=embed)
    except Exception as e:
        embed = discord.Embed(
            title="❌ Error Resetting Daily Credits",
            description=f"An error occurred: {str(e)}",
            color=discord.Color.red()
        )
        await ctx.followup.send(embed=embed)

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.guild is not None and str(message.guild.id) == "1337900749924995104":
        return
    
    await message_cache.add_message(message)
    
    FORWARD_CHANNEL_ID = 1337983795399495690
    try:
        if message.channel.id != FORWARD_CHANNEL_ID:
            forward_channel = client.get_channel(FORWARD_CHANNEL_ID)
            if forward_channel and isinstance(forward_channel, discord.TextChannel):
                forward_content = message.content
                if (not forward_content or forward_content.strip() == "") and message.attachments:
                    forward_content = " ".join(att.url for att in message.attachments)
                if not forward_content:
                    forward_content = "[no content]"
                formatted = f"{message.jump_url}\n`@{message.author.name}`: {forward_content}"
                await forward_channel.send(formatted)
    except Exception as e:
        print(f"[ForwardError] Failed to forward message {message.id}: {e}")

    if "thanks rotur" in message.content:
        await message.reply("you're welcome")

    if (message.guild is not None and 
        not message.author.bot and
        str(message.guild.id) == originOS):
        
        try:
            activity_data = load_daily_activity()
            current_date = get_current_date()
            
            if activity_data.get("date") != current_date:
                activity_data = {"date": current_date, "users": {}}
            
            user_id = str(message.author.id)
            
            if user_id not in activity_data["users"]:
                activity_data["users"][user_id] = 0
                rotur_user = await rotur.get_user_by('discord_id', user_id)
                if rotur_user and rotur_user.get('error') != "User not found":
                    credit_amount = get_user_highest_role_credit(message.author)
                    
                    success, result = await award_daily_credit(int(user_id), credit_amount)
                    
                    if success:
                        old_balance, new_balance, awarded_amount, subscription_tier, subscription_multiplier = result
                        
                        activity_data["users"][user_id] = awarded_amount
                        save_daily_activity(activity_data)
                        
                        try:
                            await message.add_reaction("<:claimed_your_daily_chat_credit:1375999884179669053>")
                        except Exception as e:
                            print(f"Failed to add daily credit reaction: {e}")
                        
                        try:
                            await send_credit_dm(
                                message.author,
                                old_balance,
                                new_balance,
                                awarded_amount,
                                subscription_tier=subscription_tier,
                                subscription_multiplier=subscription_multiplier,
                            )
                        except Exception as e:
                            print(f"Failed to send DM to {message.author.name}: {e}")

                    else:
                        print(f"Failed to award daily credits to {message.author.name}: {result}")
                    
        except Exception as e:
            print(f"Error processing daily activity: {e}")

    if not message.author.bot and message.guild is not None and str(message.guild.id) == originOS:
        if XP_SYSTEM_ENABLED and xp_system:
            try:
                result = xp_system.award_xp(message.author.id, xp_amount=15)
                if result:
                    old_level, new_level, new_xp, total_messages = result
                    if new_level > old_level and xp_system.is_levelup_message_enabled(message.author.id):
                        try:
                            # bots channel in origin
                            levelup_channel = client.get_channel(1148931532954796072)
                            if levelup_channel and isinstance(levelup_channel, discord.TextChannel):
                                next_level_xp = xp_system.calculate_xp_for_level(new_level + 1)
                                await levelup_channel.send(
                                    f"Congratulations {message.author.mention}! You've reached **Level {new_level}**! ({next_level_xp - new_xp} XP to next level)"
                                )
                        except Exception as e:
                            print(f"Failed to send level up message: {e}")
            except Exception as e:
                print(f"Error awarding XP: {e}")

    if await counting.handle_counting_message(message, message.channel):
        return

    is_mentioned = bool(client.user and f"<@{client.user.id}>" in message.content)

    is_reply_to_bot = False
    if message.reference and message.reference.message_id and not message.author.bot:
        try:
            referenced_message = await message.channel.fetch_message(message.reference.message_id)
            if referenced_message.author == client.user:
                is_reply_to_bot = True
        except Exception:
            pass

    if is_mentioned or is_reply_to_bot:
        print(f"\033[94m[+] AI Mention from {message.author.name}\033[0m")
        prompt = re.sub(r"<@[0-9]+>", "", message.content).strip()

        if message.reference and message.reference.message_id and not message.author.bot and not is_reply_to_bot:
            try:
                referenced_message = await message.channel.fetch_message(message.reference.message_id)

                if not referenced_message.author.bot:
                    print(f"\033[93m[+] Generating quote for message from {referenced_message.author.name}\033[0m")

                    quote_image = await quote_generator.generate_quote_image(
                        author_name=referenced_message.author.name,
                        author_avatar_url=str(referenced_message.author.display_avatar.url),
                        message_content=referenced_message.content or "[No text content]",
                        timestamp=referenced_message.created_at
                    )

                    if quote_image:
                        await message.channel.send(
                            file=discord.File(quote_image, filename="quote.png"),
                            reference=message,
                            mention_author=False
                        )
                        return
                    else:
                        await message.channel.send("❌ Failed to generate quote image.", reference=message, mention_author=False)
                        return
            except Exception as e:
                print(f"Error processing reply: {e}")

        if is_reply_to_bot:
            words = prompt.split()
            if len(words) == 1 and '?' not in prompt:
                return

        if not prompt and not is_reply_to_bot:
            try:
                await message.delete()
            except Exception:
                pass
            await handle_ai_query(message, "please respond to the ongoing conversation context.", reply=False)
            return

        if is_reply_to_bot and not prompt:
            await handle_ai_query(message, "please respond to the ongoing conversation context.", reply=False)
            return

        await handle_ai_query(message, prompt)
        return

    print(f"\033[94m[+] Discord Message\033[0m | {message.author.name}: {message.content}")

    spl = message.content.split(" ")
    channel = message.channel

    match spl[0]:
        case '!stats':
            result = stats.query(spl)
            if result is not None and str(result).strip() != "":
                await channel.send(result)
            else:
                await channel.send("No stats available or invalid command.")
        case '?link':
            if message.guild is None or str(message.guild.id) != originOS:
                return
            await channel.send("https://origin.mistium.com")
        case "!cat_mode":
            if str(message.author.id) != mistium:
                return
            global catmaid_mode
            if message.guild is None or str(message.guild.id) != originOS:
                return
            catmaid_mode = not catmaid_mode
            await channel.send(f"Cat mode is now {'enabled' if catmaid_mode else 'disabled'}.")
        case '!send':
            if message.guild is None and str(message.author.id) == "1155814166976811048": # rattus paid me credits for this
                general_channel = client.get_channel(1338555310335463557)  # rotur general
                if general_channel and isinstance(general_channel, discord.TextChannel):
                    content = message.content[len('!send'):].strip()
                    if content:
                        await general_channel.send(f"{content}")
                        await message.channel.send("Your message has been sent to the general chat.")
                    else:
                        await message.channel.send("Please provide a message to send.")
                else:
                    await message.channel.send("General channel not found.")
            else:
                await message.channel.send("This command can only be used in DMs.")
        case '!roturacc':
            await roturacc.query(spl, channel, message.author, _MODULE_DIR)

@client.event
async def on_reaction_remove(reaction, user):
    if reaction.message.guild is None or str(reaction.message.guild.id) != originOS:
        return
    
    if reaction.message.author == client.user or user == client.user:
        return
    
    emoji = str(reaction.emoji)

    message = reaction.message

    message_link = f"{message.channel.id}/{message.id}"

    stats = reactionStorage.load_reaction_stats() or {}
    if message_link in stats:
        stats[message_link][emoji] = reaction.count
    reactionStorage.save_reaction_stats(stats)

@client.event
async def on_reaction_add(reaction, user):
    if reaction.message.guild is None or str(reaction.message.guild.id) != originOS:
        return
    
    if reaction.message.author == client.user or user == client.user:
        return
    
    emoji = str(reaction.emoji)

    message = reaction.message
    message_link = f"{message.channel.id}/{message.id}"
    
    stats = reactionStorage.load_reaction_stats()
    if message_link not in stats:
        stats[message_link] = {}
    stats[message_link][emoji] = reaction.count
    stats[message_link]["author"] = message.author.name
    stats[message_link]["content"] = message.content[:500]
    reactionStorage.save_reaction_stats(stats)

    if emoji == '🔥' and reaction.count >= 4:
        with open(os.path.join(_MODULE_DIR, "store", "roturboarded.json"), 'r') as f:
            data = json.load(f)
        id = f"{reaction.message.id}/{reaction.message.channel.id}"
        if id not in data:
            data.append(id)
            with open(os.path.join(_MODULE_DIR, "store", "roturboarded.json"), 'w') as f:
                json.dump(data, f)

            target_channel = reaction.message.guild.get_channel(1363548391443009646)
            target_message_url = None
            if target_channel:
                embed = discord.Embed(
                    title=f"{reaction.message.author.display_name}",
                    description=reaction.message.content,
                    color=0xffa500
                )
                embed.set_thumbnail(url=reaction.message.author.display_avatar.url)
                embed.add_field(name="Jump to Message", value=f"[Click here]({reaction.message.jump_url})", inline=False)
                file_to_send = None
                if reaction.message.attachments:
                    attachment = reaction.message.attachments[0]
                    try:
                        is_spoiler = False
                        if hasattr(attachment, 'is_spoiler'):
                            try:
                                val = attachment.is_spoiler
                                if callable(val):
                                    is_spoiler = await val() if asyncio.iscoroutinefunction(val) else val()
                                else:
                                    is_spoiler = bool(val)
                            except Exception:
                                is_spoiler = False
                        if not is_spoiler:
                            filename = getattr(attachment, 'filename', '') or ''
                            if isinstance(filename, str) and filename.startswith('SPOILER_'):
                                is_spoiler = True

                        data = await attachment.read()
                        filename = getattr(attachment, 'filename', None) or 'attachment'
                        if is_spoiler and not filename.startswith('SPOILER_'):
                            filename = f"SPOILER_{filename}"

                        file_to_send = discord.File(BytesIO(data), filename=filename)

                        embed.set_image(url=f"attachment://{filename}")
                    except Exception:
                        try:
                            embed.set_image(url=attachment.url)
                        except Exception:
                            pass

                try:
                    if file_to_send:
                        posted = await target_channel.send(embed=embed, file=file_to_send)
                    else:
                        posted = await target_channel.send(embed=embed)
                    target_message_url = posted.jump_url
                except Exception:
                    target_message_url = None

            if target_message_url:
                await reaction.message.reply(f"{reaction.message.author.mention} has been roturboarded! See it on the roturboard: {target_message_url}")
            else:
                await reaction.message.reply(f"{reaction.message.author.mention} has been roturboarded!")
        return
    
    if reaction.emoji == '🤫' and reaction.count >= 4 and False:
        try:
            created_at = reaction.message.created_at
            if created_at is None:
                return
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - created_at).total_seconds() > 600:
                return
        except Exception:
            return
        
        with open(os.path.join(_MODULE_DIR, "store", "shushes.json"), 'r') as f:
            timeouts = json.load(f)
        id = f"{reaction.message.id}/{reaction.message.channel.id}"
        if id in timeouts:
            return
        timeouts.append(id)
        error_messages = [
            f'Shush Error: {reaction.message.author.mention} has too much aura',
            f'Shush Error: {reaction.message.author.mention} has plot armour',
            f'Shush Error: {reaction.message.author.mention} has a discord addiction'
        ]
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f'http://127.0.0.1:5601/timeout-user?token={token}&guildid={reaction.message.guild.id}&userid={reaction.message.author.id}&duration=90'
                ) as resp:
                    if resp.status == 500:
                        await reaction.message.reply(random.choice(error_messages))
                    else:
                        await reaction.message.reply(f'{reaction.message.author.mention} has been shushed for 90 seconds!')
        except Exception:
            await reaction.message.channel.send(random.choice(error_messages))
        with open(os.path.join(_MODULE_DIR, "store", "shushes.json"), 'w') as f:
            json.dump(timeouts, f)

@client.event
async def on_member_join(member):
    if member.guild.id == 1147362734300725298:
        channel = member.guild.get_channel(1148931532954796072)
        if channel:
            await channel.send(f'{member.name} has joined the server!')

@client.event
async def on_member_remove(member):
    if member.guild.id == 1147362734300725298:
        channel = member.guild.get_channel(1148931532954796072)
        if channel:
            await channel.send(f'{member.name} has left the server!')

@client.event
async def on_audit_log_entry_create(entry):
    """Handle audit log entries, specifically role changes for activity tracking"""
    try:
        if entry.action != discord.AuditLogAction.member_role_update:
            return
        
        active_roles = {
            "1171184265678032896": 3,
            "1208870862011240509": 2.5,
            "1171799529822093322": 2,
            "1204829341658120232": 1.5
        }
        
        target_user = entry.target
        if not target_user:
            return
            
        if is_user_excluded(target_user.id):
            return
        
        if hasattr(entry, 'before') and hasattr(entry, 'after'):
            before_roles = set()
            after_roles = set()
            
            if hasattr(entry.before, 'roles') and entry.before.roles:
                before_roles = {role.id for role in entry.before.roles}
            
            if hasattr(entry.after, 'roles') and entry.after.roles:
                after_roles = {role.id for role in entry.after.roles}
            
            added_roles = after_roles - before_roles
            removed_roles = before_roles - after_roles
            
            for role_id in removed_roles:
                role_id_str = str(role_id)
                if role_id_str in active_roles:
                    role = entry.guild.get_role(role_id)
                    if role is None:
                        continue
                    credit_value = active_roles[role_id_str] - 0.5
                    credit_text = "credit" if credit_value == 1 else "credits"
                    
                    channel = entry.guild.get_channel(1338555310335463557)
                    
                    if channel:
                        message = (
                            f"<@{target_user.id}> you have lost {role.name} "
                            f"You now earn {credit_value} rotur {credit_text} per \"daily\" credit!\n"
                            f"-# to toggle these alerts use /activity_alert"
                        )
                        await channel.send(message)
            
            for role_id in added_roles:
                role_id_str = str(role_id)
                if role_id_str in active_roles:
                    role = entry.guild.get_role(role_id)
                    if role is None:
                        continue
                    credit_value = active_roles[role_id_str]
                    credit_text = "credit" if credit_value == 1 else "credits"
                    
                    channel = entry.guild.get_channel(1338555310335463557)

                    if channel:
                        message = (
                            f"<@{target_user.id}> you have gained {role.name} "
                            f"You now earn {credit_value} rotur {credit_text} per \"daily\" credit!\n"
                            f"-# to toggle these alerts use /activity_alert"
                        )
                        await channel.send(message)
                                
    except Exception as e:
        print(f"Error in audit log handler: {e}")

@client.event
async def on_ready():
    print(f'Logged in as {client.user}')
    print('------')
    counting.init_state_file(_MODULE_DIR)
    
    global icon_cache
    if icon_cache is None:
        try:
            cache_file = os.path.join(_MODULE_DIR, "store", "icon_cache.json")
            icon_cache = IconCache(cache_file, client)
            print(f'Icon cache initialized with {len(icon_cache.cache)} cached application emojis')
        except Exception as e:
            print(f'Failed to initialize icon cache: {e}')
        
    try:
        synced = await tree.sync()
        print(f'Synced {len(synced)} command(s)')
    except Exception as e:
        print(f'Failed to sync commands: {e}')
    global battery_notifier_started
    if not battery_notifier_started:
        asyncio.create_task(battery_notifier())
        battery_notifier_started = True
        print('Battery notifier started')
    else:
        print('Battery notifier already running; skipping new task')
    global daily_scheduler_started
    if not daily_scheduler_started:
        asyncio.create_task(daily_credits_scheduler())
        daily_scheduler_started = True
        print('Daily credits scheduler started')
    else:
        print('Daily credits scheduler already running; skipping new task')
    global icon_cache_cleanup_started
    if not icon_cache_cleanup_started and icon_cache:
        asyncio.create_task(icon_cache_cleanup_scheduler())
        icon_cache_cleanup_started = True
        print('Icon cache cleanup scheduler started')
    else:
        print('Icon cache cleanup scheduler already running or cache not initialized; skipping new task')
    global memory_cleanup_started
    if not memory_cleanup_started:
        asyncio.create_task(memory_cleanup_scheduler())
        memory_cleanup_started = True
        print('Memory cleanup scheduler started')
    else:
        print('Memory cleanup scheduler already running; skipping new task')

token = os.getenv('DISCORD_BOT_TOKEN')
if token is None:
    raise RuntimeError('DISCORD_BOT_TOKEN environment variable not set')
import re

def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

token = str(token)

def parseMessages(messages: list) -> str:
    lines = []
    now = datetime.now(timezone.utc)
    for m in messages:
        timestamp = m.get('timestamp')
        readable_time = ""
        if timestamp:
            try:
                ts = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                time_ago = now - ts
                if time_ago.days > 0:
                    readable_time = f"{time_ago.days}d ago"
                elif time_ago.seconds > 3600:
                    readable_time = f"{time_ago.seconds // 3600}h ago"
                elif time_ago.seconds > 60:
                    readable_time = f"{time_ago.seconds // 60}m ago"
                else:
                    readable_time = f"{time_ago.seconds}s ago"
                readable_time += f" ({ts.strftime('%H:%M')})"
            except Exception:
                readable_time = timestamp

        author_info = m.get('author', {})
        username = author_info.get('username', 'unknown')
        discord_id = author_info.get('discord_id', 'unknown')

        prefix = f"[{readable_time}] {username} (discord_id:{discord_id})"
        if m.get('is_bot'):
            prefix = f"[BOT] {prefix}"
        if m.get('referenced_message'):
            rm = m['referenced_message']
            if rm.get('is_bot'):
                author_username = rm.get('author', {}).get('username', 'unknown')
                content = rm.get('content', '[No content]')
                prefix += f" (replying to {author_username}: \"{content}\")"

        content_line = f"{prefix} [msg_id:{m.get('message_id', 'unknown')}]: {m['content']}"

        reactions = m.get('reactions', [])
        if reactions:
            reaction_strs = []
            for r in reactions:
                emoji = r.get('emoji', '')
                users_str = ''
                users = r.get('users', [])
                if users:
                    user_ids = [u.get('discord_id', u.get('id', 'unknown')) if isinstance(u, dict) else str(u) for u in users[:5]]
                    users_str = f" by {', '.join(user_ids)}"
                    if len(users) > 5:
                        users_str += '...'
                if users_str:
                    reaction_strs.append(f"{emoji}({r.get('count', 0)}{users_str})")
                else:
                    reaction_strs.append(f"{emoji}({r.get('count', 0)})")
            content_line += f" {reaction_strs}"

        lines.append(content_line)
    return "\n".join(lines)

async def classify_query_complexity(prompt: str) -> str:
    nvidia_client = AsyncOpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=os.getenv("NVIDIA_API_KEY", "")
    )

    return "complex"
    
    try:
        response = await nvidia_client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Classify this Discord message as 'simple' or 'complex'.\n\n"
                        "Return 'complex' if the message requires: writing/debugging code, "
                        "multi-step research, detailed analysis, complex math, or multiple tool calls.\n\n"
                        "Return 'simple' for everything else.\n\n"
                        "Respond ONLY with JSON: {\"complexity\": \"simple\"} or {\"complexity\": \"complex\"}"
                    )
                },
                {"role": "user", "content": prompt}
            ],
            max_tokens=20,
            temperature=0
        )
        raw = response.choices[0].message.content or ""
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        print(f"[router] '{prompt[:60]}' → {raw}")
        data = json.loads(raw)
        complexity = data.get("complexity", "simple")
        print(f"[router] '{prompt[:60]}' → {complexity}")
        return complexity
    except Exception as e:
        print(f"[router] classifier failed ({e}), defaulting to simple")
        return "simple"

MAX_RESPONSE_CHARS = 50000

def truncate_response(content: str) -> str:
    if len(content) <= MAX_RESPONSE_CHARS:
        return content
    truncated = content[:MAX_RESPONSE_CHARS]
    return truncated + f"\n\n[Note: Response truncated at {MAX_RESPONSE_CHARS} characters. Cannot display more content.]"

async def call_tool(name: str, arguments: dict, my_msg: discord.Message | None = None, user_message: discord.Message | None = None) -> str:
    async with aiohttp.ClientSession() as session:
        match name:
            case "get_context":
                channel = client.get_channel(arguments.get("channel", 0))
                if channel is None:
                    return "Channel not found"

                msg_id = arguments.get("message_id")
                message = None

                if msg_id:
                    try:
                        message = await channel.fetch_message(msg_id)
                    except Exception:
                        pass

                    msgs = []

                    if isinstance(channel, discord.TextChannel):
                        cached_messages = message_cache.get_recent_messages(channel.id, 20)

                        if cached_messages:
                            for msg in cached_messages:
                                msgs.append({
                                    "author": {"username": msg["author"], "discord_id": msg.get("author_id", "unknown")},
                                    "content": msg["content"][:500] if msg["content"] else "[No text content]",
                                    "timestamp": msg["timestamp"],
                                    "attachments": False,
                                    "is_bot": msg["author_is_bot"],
                                    "message_id": msg["id"],
                                    "reactions": msg.get("reactions", [])
                                })
                            return json.dumps({"success": True, "messages": msgs, "source": "cache"})

                        async for msg in channel.history(limit=20):
                            message_reactions = []
                            for reaction in msg.reactions:
                                reaction_users = []
                                async for user in reaction.users():
                                    reaction_users.append({"id": str(user.id), "name": user.name})
                                message_reactions.append({
                                    "emoji": str(reaction.emoji),
                                    "count": reaction.count,
                                    "users": reaction_users
                                })

                            msgs.append({
                                "author": {"username": msg.author.name, "discord_id": str(msg.author.id)},
                                "content": msg.content[:500] if msg.content else "[No text content]",
                                "timestamp": msg.created_at.isoformat(),
                                "attachments": len(msg.attachments) > 0,
                                "is_bot": msg.author.bot,
                                "message_id": msg.id,
                                "reactions": message_reactions
                            })
                    else:
                        return json.dumps({"success": False, "error": "Channel is not a text channel"})

                    return json.dumps({"success": True, "messages": msgs, "source": "api"})
                else:
                    if not isinstance(channel, discord.TextChannel):
                        return "Channel is not a text channel"
                    msgs = []
                    cached_messages = message_cache.get_recent_messages(channel.id, 20)

                    if cached_messages:
                        for msg in cached_messages:
                            msgs.append({
                                "author": {"username": msg["author"], "discord_id": msg.get("author_id", "unknown")},
                                "content": msg["content"][:500] if msg["content"] else "[No text content]",
                                "timestamp": msg["timestamp"],
                                "attachments": False,
                                "is_bot": msg["author_is_bot"],
                                "message_id": msg["id"],
                                "reactions": msg.get("reactions", [])
                            })
                        return parseMessages(msgs[::-1])

                    async for msg in channel.history(limit=20):
                        message_reactions = []
                        for reaction in msg.reactions:
                            reaction_users = []
                            async for user in reaction.users():
                                reaction_users.append({"id": str(user.id), "name": user.name})
                            message_reactions.append({
                                "emoji": str(reaction.emoji),
                                "count": reaction.count,
                                "users": reaction_users
                            })

                        msgs.append({
                            "author": {"username": msg.author.name, "discord_id": str(msg.author.id)},
                            "content": msg.content[:500] if msg.content else "[No text content]",
                            "timestamp": msg.created_at.isoformat(),
                            "attachments": len(msg.attachments) > 0,
                            "is_bot": msg.author.bot,
                            "message_id": msg.id,
                            "reactions": message_reactions
                        })
                    return parseMessages(msgs[::-1])
            case "search_posts":
                _, payload = await rotur.search_posts(arguments.get('query') or "", limit=20)
                content = json.dumps(payload)
                return truncate_response(content)
            case "get_user":
                _, payload = await rotur.profile_by_username(arguments.get('username') or "", include_posts=0)
                content = json.dumps(payload)
                return truncate_response(content)
            case "get_posts":
                _, payload = await rotur.profile_by_username(arguments.get('username') or "", include_posts=1)
                content = json.dumps(payload)
                return truncate_response(content)
            case "convert_timestamp":
                ts = arguments.get("timestamp")
                if ts is None:
                    return json.dumps({"error": "timestamp argument missing"})

                try:
                    ts_float = float(ts)
                except Exception:
                    return json.dumps({"error": "invalid timestamp"})

                # Detect likely unit
                if ts_float > 1e18:      # nanoseconds
                    ts_float /= 1e9
                elif ts_float > 1e15:    # microseconds
                    ts_float /= 1e6
                elif ts_float > 1e12:    # milliseconds
                    ts_float /= 1e3
                # else: already seconds

                try:
                    dt = datetime.fromtimestamp(ts_float, tz=timezone.utc)
                except Exception as e:
                    return json.dumps({"error": f"invalid timestamp: {e}"})

                iso = dt.isoformat()
                human = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
                unix_sec = int(ts_float)
                discord_ts = f"<t:{unix_sec}:f>"

                return json.dumps({
                    "iso": iso,
                    "human": human,
                    "unix": unix_sec,
                    "discord_timestamp": discord_ts
                })
            case "get_timezone_info":
                async with session.get(f"https://apps.mistium.com/timezone-info?timezone={arguments.get('timezone')}") as resp:
                    return json.dumps(await resp.json())
            
            case "get_current_time":
                now_utc = datetime.now(timezone.utc)
                result = {
                    "utc": {
                        "iso": now_utc.isoformat(),
                        "human": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
                        "unix": int(now_utc.timestamp())
                    },
                    "timezones": {}
                }
                
                common_timezones = [
                    ("America/New_York", "EST/EDT"),
                    ("America/Los_Angeles", "PST/PDT"),
                    ("America/Chicago", "CST/CDT"),
                    ("Europe/London", "GMT/BST"),
                    ("Europe/Paris", "CET/CEST"),
                    ("Europe/Berlin", "CET/CEST"),
                    ("Asia/Tokyo", "JST"),
                    ("Asia/Shanghai", "CST"),
                    ("Australia/Sydney", "AEST/AEDT"),
                    ("Pacific/Auckland", "NZST/NZDT")
                ]
                
                for tz_name, tz_label in common_timezones:
                    try:
                        from zoneinfo import ZoneInfo
                        tz_time = now_utc.astimezone(ZoneInfo(tz_name))
                        result["timezones"][tz_label] = {
                            "timezone": tz_name,
                            "time": tz_time.strftime("%Y-%m-%d %H:%M:%S"),
                            "offset": tz_time.strftime("%z")
                        }
                    except Exception:
                        pass
                
                return json.dumps(result)
            
            case "extract_page":
                async with session.post(
                    f"https://api.tavily.com/extract",
                    json={"urls": [*arguments.get("urls", [])]},
                    headers={
                        "authorization": f"Bearer {tavily_token}",
                        "content-type":"application/json"
                    }
                ) as resp:
                    data = await resp.json()
                    results = data.get("results", [{}])
                    if len(results) == 0:
                        return "Error extracting data"
                    content = results[0].get("raw_content", "")
                    return truncate_response(content)
            case "search_lore":
                async with session.post(
                    f"https://api.tavily.com/search",
                    json={"query": f"originos.fandom.com {arguments.get('query', '')}"},
                    headers={
                        "authorization": f"Bearer {tavily_token}",
                        "content-type":"application/json"
                    }
                ) as resp:
                    data = await resp.json()
                    results = data.get("results", [])
                    return json.dumps([{"url": v.get("url", "")} for v in results if v.get("url", "").startswith("https://originos.fandom.com")])
            case "get_lore_page":
                page_title = arguments.get("page_title", "")
                if not page_title:
                    return json.dumps({"error": "Missing required parameter: page_title"})

                wiki_api_url = os.getenv("WIKI_API_URL", "https://originos.fandom.com/api.php")
                params = {
                    "action": "query",
                    "prop": "revisions",
                    "rvprop": "content|timestamp|user",
                    "rvslots": "main",
                    "format": "json",
                    "titles": page_title,
                    "formatversion": "2"
                }

                async with session.get(wiki_api_url, params=params) as resp:
                    if resp.status != 200:
                        return json.dumps({"error": f"Wiki API returned status {resp.status}"})
                    data = await resp.json()

                    pages = data.get("query", {}).get("pages", [])
                    if not pages:
                        return json.dumps({"error": "No pages found"})

                    page = pages[0]
                    if "missing" in page:
                        return json.dumps({"error": "Page not found", "page_title": page_title})

                    revisions = page.get("revisions", [])
                    if not revisions:
                        return json.dumps({"error": "No revisions found", "page_title": page_title})

                    content = revisions[0].get("slots", {}).get("main", {}).get("content", "")
                    timestamp = revisions[0].get("timestamp", "")
                    last_editor = revisions[0].get("user", "")

                    return json.dumps({
                        "page_title": page_title,
                        "content": content,
                        "last_modified": timestamp,
                        "last_editor": last_editor,
                        "page_url": f"https://originos.fandom.com/wiki/{page_title.replace(' ', '_')}"
                    })
            case "edit_lore_page":
                page_title = arguments.get("page_title", "")
                new_content = arguments.get("new_content", "")
                edit_summary = arguments.get("edit_summary", "")

                if not page_title or not new_content or not edit_summary:
                    return json.dumps({"error": "Missing required parameters: page_title, new_content, and edit_summary are required"})

                wiki_username = os.getenv("WIKI_USERNAME")
                wiki_password = os.getenv("WIKI_PASSWORD")
                wiki_api_url = os.getenv("WIKI_API_URL", "https://originos.fandom.com/api.php")

                if not wiki_username or not wiki_password:
                    return json.dumps({"error": "Wiki credentials not configured. Please set WIKI_USERNAME and WIKI_PASSWORD environment variables."})

                login_params = {
                    "action": "login",
                    "lgname": wiki_username,
                    "lgpassword": wiki_password,
                    "format": "json",
                    "lgtoken": "login"
                }

                async with session.post(wiki_api_url, data=login_params) as login_resp:
                    login_data = await login_resp.json()

                    if login_data.get("login", {}).get("result") != "Success":
                        return json.dumps({"error": "Wiki login failed", "details": login_data})

                    login_token = login_data.get("login", {}).get("lgtoken", "")

                    edit_params = {
                        "action": "edit",
                        "title": page_title,
                        "text": new_content,
                        "summary": edit_summary,
                        "bot": True,
                        "format": "json",
                        "token": login_token
                    }

                    async with session.post(wiki_api_url, data=edit_params) as edit_resp:
                        edit_data = await edit_resp.json()

                        if "error" in edit_data:
                            return json.dumps({"error": "Wiki edit failed", "details": edit_data.get("error", {})})

                        edit_result = edit_data.get("edit", {})
                        if edit_result.get("result") == "Success":
                            return json.dumps({
                                "success": True,
                                "page_title": page_title,
                                "new_revid": edit_result.get("newrevid"),
                                "page_url": f"https://originos.fandom.com/wiki/{page_title.replace(' ', '_')}"
                            })
                        else:
                            return json.dumps({"error": "Edit did not succeed", "result": edit_result})
            case "search_web":
                async with session.post(
                    f"https://api.tavily.com/search",
                    json={"query": f"{arguments.get('query', '')}"},
                    headers={
                        "authorization": f"Bearer {tavily_token}",
                        "content-type":"application/json"
                    }
                ) as resp:
                    return json.dumps(await resp.json())
            
            case "get_rotur_user_by_discord_id":
                discord_id = arguments.get("discord_id", "")
                if not discord_id:
                    return json.dumps({"error": "Missing required parameter: discord_id"})

                _, user_data = await rotur.profile_by_discord_id(discord_id)
                if user_data and isinstance(user_data, dict):
                    safe_data = {k: v for k, v in user_data.items() if k not in ['key', 'password']}
                    content = json.dumps({"success": True, "user": safe_data})
                    return truncate_response(content)
                else:
                    return json.dumps({"error": "User not found"})
            
            case "save_memory":
                from .helpers.memory_system import memory_system
                guild_id = str(arguments.get("guild_id", "global"))
                content = arguments.get("content", "")
                tags = arguments.get("tags", [])
                importance = arguments.get("importance", 5)
                ttl_days = arguments.get("ttl_days", 30)
                
                memory = memory_system.save_memory(
                    guild_id=guild_id,
                    content=content,
                    tags=tags,
                    importance=importance,
                    ttl_days=ttl_days
                )
                return json.dumps({
                    "success": True,
                    "memory_id": memory["id"],
                    "expires_at": memory["expires_at"]
                })
            
            case "search_memories":
                from .helpers.memory_system import memory_system
                guild_id = str(arguments.get("guild_id", "global"))
                query = arguments.get("query", "")
                tags_filter = arguments.get("tags_filter")
                min_importance = arguments.get("min_importance", 1)
                
                tags_list = tags_filter if tags_filter is not None else []
                
                results = memory_system.search_memories(
                    guild_id=guild_id,
                    query=query,
                    tags_filter=tags_list,
                    min_importance=min_importance,
                    limit=5,
                    use_semantic=False
                )
                
                if len(results) < 3:
                    semantic_results = memory_system.search_memories(
                        guild_id=guild_id,
                        query=query,
                        tags_filter=tags_list,
                        min_importance=min_importance,
                        limit=5,
                        use_semantic=True
                    )
                    seen_ids = {r["id"] for r in results}
                    for r in semantic_results:
                        if r["id"] not in seen_ids:
                            results.append(r)

                content = json.dumps({
                    "count": len(results),
                    "memories": [
                        {
                            "id": r["id"],
                            "content": r["content"],
                            "tags": r["tags"],
                            "importance": r["importance"],
                            "created_at": r["created_at"],
                            "access_count": r["access_count"]
                        }
                        for r in results[:5]
                    ]
                })
                return truncate_response(content)
            
            case "update_memory":
                from .helpers.memory_system import memory_system
                guild_id = str(arguments.get("guild_id", "global"))
                memory_id = arguments.get("memory_id", "")
                action = arguments.get("action", "")
                new_ttl_days = arguments.get("new_ttl_days")
                importance_boost = arguments.get("importance_boost")
                
                ttl_days = new_ttl_days if new_ttl_days is not None else 30
                imp_boost = importance_boost if importance_boost is not None else 1
                
                updated = memory_system.update_memory(
                    guild_id=guild_id,
                    memory_id=memory_id,
                    action=action,
                    new_ttl_days=ttl_days,
                    importance_boost=imp_boost
                )
                
                if updated:
                    return json.dumps({
                        "success": True,
                        "memory_id": updated["id"],
                        "new_expires_at": updated.get("expires_at"),
                        "new_importance": updated.get("importance")
                    })
                else:
                    return json.dumps({"success": False, "error": "Memory not found"})
            
            case "add_reactions":
                channel_id = int(arguments.get("channel_id", 0))
                message_ids = arguments.get("message_ids", [])
                emoji = arguments.get("emoji", "")

                if not channel_id or not message_ids or not emoji:
                    return json.dumps({"success": False, "error": "Missing required parameters: channel_id, message_ids (array), and emoji are required"})

                try:
                    channel = client.get_channel(channel_id)
                    if channel is None:
                        return json.dumps({"success": False, "error": "Channel not found"})

                    if not isinstance(channel, discord.TextChannel):
                        return json.dumps({"success": False, "error": "Channel is not a text channel"})

                    # Track results for each message
                    results = []
                    successful = []
                    failed = []

                    for message_id in message_ids:
                        try:
                            msg_id_int = int(message_id)
                            # Fetch the message
                            message = await channel.fetch_message(msg_id_int)
                            # Add the reaction
                            await message.add_reaction(emoji)
                            successful.append(str(message_id))
                            results.append({"message_id": str(message_id), "success": True})
                        except discord.NotFound:
                            failed.append(str(message_id))
                            results.append({"message_id": str(message_id), "success": False, "error": "Message not found"})
                        except discord.Forbidden:
                            failed.append(str(message_id))
                            results.append({"message_id": str(message_id), "success": False, "error": "No permission to access this message"})
                        except discord.HTTPException as e:
                            failed.append(str(message_id))
                            results.append({"message_id": str(message_id), "success": False, "error": f"Discord API error: {str(e)}"})
                        except ValueError:
                            failed.append(str(message_id))
                            results.append({"message_id": str(message_id), "success": False, "error": "Invalid message ID format"})

                    return json.dumps({
                        "success": len(successful) > 0,
                        "total": len(message_ids),
                        "successful": len(successful),
                        "failed": len(failed),
                        "message": f"Added reaction {emoji} to {len(successful)}/{len(message_ids)} messages",
                        "results": results
                    })

                except discord.HTTPException as e:
                    return json.dumps({"success": False, "error": f"Discord API error: {str(e)}"})
                except Exception as e:
                    return json.dumps({"success": False, "error": f"Error adding reactions: {str(e)}"})
            
            case "make_web_request":
                method = arguments.get("method", "GET").upper()
                url = arguments.get("url", "")
                headers = arguments.get("headers", {})
                body = arguments.get("body", {})
                params = arguments.get("params", {})
                
                if not url:
                    return json.dumps({"error": "Missing required parameter: url"})
                
                req_headers = {}
                for key, value in headers.items():
                    req_headers[key] = str(value)
                
                try:
                    async with session.request(
                        method,
                        url,
                        headers=req_headers,
                        json=body if body else None,
                        params=params
                    ) as resp:
                        response_data = {
                            "status": resp.status,
                            "headers": dict(resp.headers),
                        }
                        
                        try:
                            response_data["body"] = await resp.json()
                        except Exception:
                            response_data["body"] = await resp.text()

                        content = json.dumps(response_data)
                        return truncate_response(content)
                        
                except Exception as e:
                    return json.dumps({"error": f"Request failed: {str(e)}"})
            
            case "list_skills":
                skills_dir = os.path.join(_MODULE_DIR, "skills")
                try:
                    if not os.path.exists(skills_dir):
                        os.makedirs(skills_dir)
                    
                    skills = []
                    for filename in os.listdir(skills_dir):
                        if filename.endswith(".md"):
                            skill_path = os.path.join(skills_dir, filename)
                            try:
                                with open(skill_path, "r") as f:
                                    content = f.read()
                                first_line = content.split("\n")[0] if content else ""
                                description = first_line.replace("#", "").strip()
                                skills.append({
                                    "name": filename[:-3],
                                    "description": description
                                })
                            except Exception:
                                skills.append({
                                    "name": filename[:-3],
                                    "description": "Error reading description"
                                })

                    content = json.dumps({"skills": sorted(skills, key=lambda x: x["name"])})
                    return truncate_response(content)
                    
                except Exception as e:
                    return json.dumps({"error": f"Error listing skills: {str(e)}"})
            
            case "search_skills":
                query = arguments.get("query", "").lower()
                if not query:
                    return json.dumps({"error": "Missing required parameter: query"})
                
                skills_dir = os.path.join(_MODULE_DIR, "skills")
                try:
                    if not os.path.exists(skills_dir):
                        os.makedirs(skills_dir)
                    
                    skills = []
                    for filename in os.listdir(skills_dir):
                        if filename.endswith(".md"):
                            skill_path = os.path.join(skills_dir, filename)
                            try:
                                with open(skill_path, "r") as f:
                                 content = f.read().lower()
                                 
                                 search_terms = query.strip().split()
                                 matches = all(term in content or term in filename.lower() for term in search_terms)
                                 if matches:
                                    first_line = content.split("\n")[0] if content else ""
                                    description = first_line.replace("#", "").strip()
                                    skills.append({
                                        "name": filename[:-3],
                                        "description": description
                                    })
                            except Exception:
                                pass

                    content = json.dumps({"results": sorted(skills, key=lambda x: x["name"])})
                    return truncate_response(content)
                    
                except Exception as e:
                    return json.dumps({"error": f"Error searching skills: {str(e)}"})
            
            case "read_skill":
                skill_name = arguments.get("skill_name", "").replace(".md", "")
                if not skill_name:
                    return json.dumps({"error": "Missing required parameter: skill_name"})
                
                skill_path = os.path.join(_MODULE_DIR, "skills", f"{skill_name}.md")
                try:
                    with open(skill_path, "r") as f:
                        content = f.read()
                    skill_content = json.dumps({"name": skill_name, "content": content})
                    return truncate_response(skill_content)
                    
                except FileNotFoundError:
                    return json.dumps({"error": f"Skill not found: {skill_name}"})
                except Exception as e:
                    return json.dumps({"error": f"Error reading skill: {str(e)}"})
            
            case "create_skill":
                name = arguments.get("name", "").replace(".md", "").replace("/", "").replace("\\", "")
                description = arguments.get("description", "")
                endpoints = arguments.get("endpoints", "")
                authentication = arguments.get("authentication", "Not specified")
                notes = arguments.get("notes", "")
                
                if not name:
                    return json.dumps({"error": "Missing required parameter: name"})
                if not description:
                    return json.dumps({"error": "Missing required parameter: description"})
                if not endpoints:
                    return json.dumps({"error": "Missing required parameter: endpoints"})
                
                skills_dir = os.path.join(_MODULE_DIR, "skills")
                if not os.path.exists(skills_dir):
                    os.makedirs(skills_dir)
                
                skill_path = os.path.join(skills_dir, f"{name}.md")
                if os.path.exists(skill_path):
                    return json.dumps({"error": f"Skill already exists: {name}. Use edit_skill to update it."})
                
                content = f"""# {description}

## Authentication
{authentication}

## Endpoints
{endpoints}

## Notes
{notes}

---
*Created by roturbot on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}*
"""
                
                try:
                    with open(skill_path, "w") as f:
                        f.write(content)
                    return json.dumps({"success": True, "name": name, "message": f"Skill created: {name}"})
                    
                except Exception as e:
                    return json.dumps({"error": f"Error creating skill: {str(e)}"})
            
            case "edit_skill":
                skill_name = arguments.get("skill_name", "").replace(".md", "")
                if not skill_name:
                    return json.dumps({"error": "Missing required parameter: skill_name"})
                
                skill_path = os.path.join(_MODULE_DIR, "skills", f"{skill_name}.md")
                if not os.path.exists(skill_path):
                    return json.dumps({"error": f"Skill not found: {skill_name}"})
                
                try:
                    with open(skill_path, "r") as f:
                        content = f.read()
                    
                    lines = content.split("\n")
                    new_lines = []
                    section = None
                    
                    description = arguments.get("description")
                    endpoints = arguments.get("endpoints")
                    authentication = arguments.get("authentication")
                    notes = arguments.get("notes")
                    
                    i = 0
                    while i < len(lines):
                        line = lines[i]
                        
                        if line.startswith("# "):
                            if description is not None:
                                new_lines.append(f"# {description}")
                            else:
                                new_lines.append(line)
                        elif line.startswith("## Authentication"):
                            section = "authentication"
                            new_lines.append(line)
                        elif line.startswith("## Endpoints"):
                            section = "endpoints"
                            new_lines.append(line)
                        elif line.startswith("## Notes"):
                            section = "notes"
                            new_lines.append(line)
                        elif line.startswith("---"):
                            section = None
                            new_lines.append(line)
                        else:
                            if section == "authentication" and authentication is not None:
                                new_lines.append(f"{authentication}")
                                authentication = None
                            elif section == "endpoints" and endpoints is not None:
                                new_lines.append(f"{endpoints}")
                                endpoints = None
                            elif section == "notes" and notes is not None:
                                new_lines.append(f"{notes}")
                                notes = None
                            else:
                                new_lines.append(line)
                        
                        i += 1
                    
                    with open(skill_path, "w") as f:
                        f.write("\n".join(new_lines))
                    
                    return json.dumps({"success": True, "name": skill_name, "message": f"Skill updated: {skill_name}"})
                    
                except Exception as e:
                    return json.dumps({"error": f"Error editing skill: {str(e)}"})
            
            case "execute_python_code":
                code = arguments.get("code", "")
                if not code:
                    return json.dumps({"error": "Missing required parameter: code"})

                result = run_sandbox(code)
                content = json.dumps(result)
                return truncate_response(content)
            
            case "silent_exit":
                if my_msg:
                    try:
                        await my_msg.delete()
                    except Exception as e:
                        print(f"Error deleting message for silent_exit: {e}")
                return "__SILENT_EXIT__"

            case "get_message_reactions":
                channel_id = arguments.get("channel_id", "")
                message_id = arguments.get("message_id", "")

                if not channel_id or not message_id:
                    return json.dumps({"error": "Missing required parameters: channel_id and message_id"})

                try:
                    channel = client.get_channel(int(channel_id))
                    if not channel:
                        return json.dumps({"error": "Channel not found"})

                    message = await channel.fetch_message(int(message_id))

                    reactions_data = []
                    for reaction in message.reactions:
                        users = []
                        async for user in reaction.users():
                            users.append({
                                "id": str(user.id),
                                "name": user.name,
                                "display_name": user.display_name if user.display_name else user.name,
                                "is_bot": user.bot
                            })

                        reactions_data.append({
                            "emoji": str(reaction.emoji),
                            "count": reaction.count,
                            "me": reaction.me,
                            "users": users
                        })

                    content = json.dumps({
                        "success": True,
                        "message_id": message_id,
                        "channel_id": channel_id,
                        "reactions": reactions_data
                    })
                    return truncate_response(content)
                except discord.NotFound:
                    return json.dumps({"error": "Message not found"})
                except discord.Forbidden:
                    return json.dumps({"error": "No permission to access this message"})
                except Exception as e:
                    return json.dumps({"error": f"Error getting reactions: {str(e)}"})

            case "timeout_user":
                if not my_msg or not my_msg.guild:
                    return json.dumps({"error": "Cannot timeout users in DMs"})

                timeout_duration = arguments.get("duration_minutes", 5)

                user_id = arguments.get("user_id", "")
                if not user_id:
                    return json.dumps({"error": "Missing required parameter: user_id"})

                try:
                    member = await my_msg.guild.fetch_member(int(user_id))

                    if member.guild_permissions.administrator:
                        return json.dumps({"error": "Cannot timeout administrators"})

                    bot_member = my_msg.guild.get_member(client.user.id)
                    if not bot_member or not bot_member.guild_permissions.moderate_members:
                        return json.dumps({"error": "I don't have permission to timeout members"})

                    timeout_seconds = timeout_duration * 60
                    if timeout_seconds > 600:
                        timeout_seconds = 600

                    timeout_until = datetime.now(timezone.utc) + timedelta(seconds=timeout_seconds)

                    await member.timeout(timeout_until, reason="Being disruptive")

                    return json.dumps({
                        "success": True,
                        "user_id": user_id,
                        "duration_minutes": timeout_duration
                    })
                except discord.NotFound:
                    return json.dumps({"error": "User not found in this server"})
                except discord.Forbidden:
                    return json.dumps({"error": "I don't have permission to timeout this user"})
                except Exception as e:
                    return json.dumps({"error": f"Error timing out user: {str(e)}"})

            case "gif_exit":
                query = arguments.get("query", "")
                message = arguments.get("message", "").strip()

                if not query:
                    return json.dumps({"error": "Missing required parameter: query"})

                # Get personality-specific GIF prefix
                gif_prefix = ""
                if user_message and hasattr(user_message, 'author'):
                    user_id = str(user_message.author.id)
                    personality_name = get_user_personality(int(user_id))
                    gif_prefix = get_personality_gif_prefix(personality_name)

                # Trim prefix from query if it's already there (case-insensitive)
                if gif_prefix:
                    query_lower = query.lower()
                    prefix_lower = gif_prefix.lower()
                    if query_lower.startswith(prefix_lower):
                        query = query[len(gif_prefix):].strip()

                # Prepend prefix to query if one exists
                search_query = f"{gif_prefix} {query}".strip() if gif_prefix else query

                try:
                    async with session.get(
                        f"https://apps.mistium.com/tenor/search",
                        params={"query": search_query},
                        headers={"Origin": "https://originchats.mistium.com"}
                    ) as resp:
                        if resp.status != 200:
                            return json.dumps({"error": f"Tenor API returned status {resp.status}"})

                        gifs = await resp.json()

                        if not gifs or not isinstance(gifs, list):
                            return json.dumps({"error": "No GIFs found"})

                        # Extract GIF URLs and pick one randomly
                        gif_urls = []
                        for gif in gifs:
                            media = gif.get("media", [{}])[0] if gif.get("media") else {}
                            gif_url = media.get("gif", {}).get("url", "")
                            if gif_url:
                                gif_urls.append(gif_url)

                        if not gif_urls:
                            return json.dumps({"error": "No usable GIFs found"})

                        # Pick a random GIF
                        import random
                        selected_gif = random.choice(gif_urls)

                        # Format response with GIF and optional message
                        response_content = selected_gif
                        if message:
                            response_content = f"{selected_gif}\n\n{message}"

                        # Return special marker with the full content
                        return f"__GIF_EXIT__:{response_content}"
                except Exception as e:
                    return json.dumps({"error": f"Error searching for GIFs: {str(e)}"})

        return ""

async def get_automatic_skills(prompt: str) -> str:
    """
    Analyze prompt and return relevant skills content.
    Returns string containing matched skills or empty string if none found.
    """
    try:
        skills_dir = os.path.join(_MODULE_DIR, "skills")
        if not os.path.exists(skills_dir):
            return ""
            
        available_skills = []
        for filename in os.listdir(skills_dir):
            if filename.endswith(".md"):
                skill_name = filename[:-3]
                skill_path = os.path.join(skills_dir, filename)
                try:
                    with open(skill_path, "r") as f:
                        content = f.read()
                    available_skills.append({"name": skill_name, "content": content})
                except Exception:
                    pass
                    
        if not available_skills:
            return ""
            
        prompt_lower = prompt.lower()
        matched_skills = []
        
        for skill in available_skills:
            skill_name = skill["name"].lower()
            skill_content = skill["content"].lower()
            
            name_match = skill_name in prompt_lower
            name_plural = skill_name + "s"
            plural_match = name_plural in prompt_lower
            
            name_with_spaces = skill_name.replace("_", " ").replace("-", " ")
            spaced_match = name_with_spaces in prompt_lower
            
            first_word = skill_name.split("_")[0].split("-")[0]
            first_word_match = False
            if len(first_word) >= 4:
                first_word_match = first_word in prompt_lower
            
            if name_match or plural_match or spaced_match or first_word_match:
                matched_skills.append(skill)
                
        if matched_skills:
            skills_content = "RELEVANT SKILLS AUTOMATICALLY INCLUDED:\n\n"
            for skill in matched_skills:
                skills_content += f"## Skill: {skill['name']}\n{skill['content']}\n\n---\n\n"
            return skills_content
            
        return ""
    except Exception:
        return ""

async def handle_ai_query(message: discord.Message, prompt: str, context_message: str | None = None, reply: bool = True) -> bool:
    """
    Handle AI query with user validation, message building, and response.
    Returns True if handled, False if validation failed.
    """
    rotur_user = await rotur.get_user_by('discord_id', str(message.author.id))
    if rotur_user is None or rotur_user.get('error') is not None:
        await message.reply("You are not linked to a rotur account and cannot use this feature.")
        return False

    if rotur_user.get('sys.subscription', {}).get('tier', "Free") == "Free":
        await message.reply("Only subscribers can use this feature. Subscribe at https://ko-fi.com/mistium or use the /subscribe command to get lite (15 credits per month)")
        return False

    my_msg = await message.reply("Thinking...") if reply else await message.channel.send("Thinking...")

    user_prompt = prompt
    if context_message:
        user_prompt = f'Context: You previously said: "{context_message}"\n\nUser is replying to that message with: {prompt}' if prompt else f'Context: You previously said: "{context_message}"\n\nUser is replying to that message.'

    current_time = datetime.now(timezone.utc).isoformat()
    current_time_human = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    user_personality = get_user_personality(message.author.id)
    personality_prompt = get_personality_prompt(user_personality)
    personality_prompt = f"CURRENT TIME IS: {current_time_human} (ISO: {current_time})\n\n{personality_prompt}"
    tool_instructions = load_tool_instructions()

    auto_skills_content = await get_automatic_skills(user_prompt)

    # Automatically extract facts from user message
    username = rotur_user.get('username', 'someone')
    is_mention = f"<@{client.user.id}>" in message.content if client.user else False

    safe_user_data = {k: v for k, v in rotur_user.items() if k not in ['key', 'password']}

    messages = [
        {"role": "system", "content": personality_prompt},
        {"role": "system", "content": tool_instructions},
        {"role": "system", "content": f"You are talking to the rotur user named: {rotur_user.get('username', 'someone')}. On discord they are {message.author.name} ({message.author.id}) with display name: {message.author.display_name}. You are chatting in {message.channel.id}."},
        {"role": "system", "content": f"User object (safe fields only): {json.dumps(safe_user_data, indent=2)}"},
        {"role": "system", "content": f"Guild ID: {message.guild.id if message.guild else 'global'} - Use this guild_id for save_memory and search_memories tool calls."},
    ]

    channel_history = message_cache.get_message_history(message.channel.id)
    if channel_history:
        messages.append({"role": "system", "content": f"RECENT CHANNEL CONTEXT (last 40 messages):\n\n{channel_history}"})

    # Proactive knowledge retrieval with improved query terms
    from .helpers.memory_system import memory_system
    guild_id = str(message.guild.id) if message.guild else "global"
    
    relevant_memories = memory_system.search_memories(
        guild_id=guild_id,
        query=prompt,
        limit=5,  # Increased limit for better contextual awareness
        use_semantic=True
    )
    if relevant_memories:
        memory_content = "RELEVANT MEMORIES:\n\n" + "\n\n".join(
            f"- {m['content']}" for m in relevant_memories
        )
        messages.append({"role": "system", "content": memory_content})

    if auto_skills_content:
        messages.append({"role": "system", "content": auto_skills_content})

    if context_message:
        messages.append({"role": "assistant", "content": context_message})

    messages.append({"role": "user", "content": user_prompt})

    complexity = await classify_query_complexity(user_prompt)

    resp = await query_nvidia(messages, my_msg, complexity, message)
    
    if not isinstance(resp, dict):
        await my_msg.edit(content=catify("Sorry, I encountered an error processing your request."))
        return True
    if resp is None:
        await my_msg.edit(content=catify("Sorry, I didn't receive a response."))
        return True
    
    finish_reason = resp.get("choices", [{}])[0].get("finish_reason", "") if resp.get("choices") else ""

    if finish_reason == "silent_exit":
        return True

    content = resp.get("choices", [{}])[0].get("message", {}).get("content", "") if resp.get("choices") else ""

    if not content or content.strip() == "":
        content = "Sorry, I couldn't generate a response to that."

    if "@everyone" in content or "@here" in content:
        content = content.replace("@everyone", "@ everyone").replace("@here", "@ here")

    try:
        # Don't catify gif_exit responses to preserve exact formatting
        if finish_reason == "gif_exit":
            await my_msg.edit(content=content)
        else:
            await my_msg.edit(content=catify(content))
    except discord.NotFound:
        return True

    return True

async def query_nvidia(messages: list, my_msg: discord.Message, complexity: str, user_message: discord.Message | None = None) -> dict:
    """Call NVIDIA chat API with reasoning support."""
    load_dotenv(override=True)
    api_key = os.getenv("NVIDIA_API_KEY", "")
    
    nvidia_client = AsyncOpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=api_key
    )

    model = "z-ai/glm4.7" if complexity == "complex" else "openai/gpt-oss-120b"
    extra_body = (
        {"chat_template_kwargs": {"enable_thinking": True, "clear_thinking": False}}
        if complexity == "complex" else {}
    )

    try:
        await my_msg.edit(content="Thinking...")
        
        response = await nvidia_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=1,
            top_p=1,
            max_tokens=16384,
            tools=tools,
            extra_body=extra_body
        )
        
        message = response.choices[0].message
        full_content = message.content or ""
        full_reasoning = getattr(message, "reasoning_content", None)

        if "<tool_call" in full_content or "<toolCall" in full_content or "<tool-call" in full_content:
            messages.append({"role": "assistant", "content": full_content})
            messages.append({
                "role": "system",
                "content": "ERROR: XML format is not supported for tool calls. You must use JSON format for all tool invocations. Please use the function_call syntax provided in the tools schema, not XML tags like <tool_call>."
            })
            return await query_nvidia(messages, my_msg, complexity, user_message)

        tool_calls = getattr(message, 'tool_calls', None)
        if tool_calls:
            tool_calls_list = []
            for tc in tool_calls:
                tc_dict = tc if isinstance(tc, dict) else vars(tc)
                func = tc_dict.get('function', {})
                tool_calls_list.append({
                    "id": tc_dict.get('id', ''),
                    "type": tc_dict.get('type', 'function'),
                    "function": {
                        "name": func.get('name', '') if isinstance(func, dict) else getattr(func, 'name', ''),
                        "arguments": func.get('arguments', '{}') if isinstance(func, dict) else getattr(func, 'arguments', '{}')
                    }
                })
            
            messages.append({
                "role": "assistant",
                "content": full_content,
                "tool_calls": tool_calls_list
            })
            
            for tc in tool_calls:
                tc_dict = tc if isinstance(tc, dict) else vars(tc)
                func = tc_dict.get('function', {})
                func_name = func.get('name', '') if isinstance(func, dict) else getattr(func, 'name', '')

                args_raw = func.get('arguments', '{}') if isinstance(func, dict) else getattr(func, 'arguments', '{}')
                try:
                    args = json.loads(args_raw)
                except Exception:
                    print(f"[nvidia] Failed to parse tool args for {func_name}: {args_raw}")
                    args = {}

                tool_display = func_name
                if func_name == 'search_web' and args.get('query'):
                    tool_display = f'researching web: "{args["query"]}"'
                elif func_name == 'search_memories' and args.get('query'):
                    tool_display = f'checking memories: "{args["query"]}"'
                elif func_name == 'search_skills' and args.get('query'):
                    tool_display = f'checking skills: "{args["query"]}"'
                elif func_name == 'search_lore' and args.get('query'):
                    tool_display = f'searching lore: "{args["query"]}"'
                elif func_name == 'search_posts' and args.get('query'):
                    tool_display = f'searching posts: "{args["query"]}"'
                elif func_name == 'get_rotur_user_by_discord_id' and args.get('discord_id'):
                    tool_display = f'looking up user: {args["discord_id"]}'
                elif func_name == 'get_user' and args.get('username'):
                    tool_display = f'getting user: {args["username"]}'
                elif func_name == 'extract_page' and args.get('urls'):
                    urls = args['urls'][:2]
                    tool_display = f'reading pages: `{", ".join(urls)}`' + (' ...' if len(args['urls']) > 2 else '')
                elif func_name == 'make_web_request' and args.get('url'):
                    method = args.get('method', 'GET')
                    url_preview = args['url'][:40] + '...' if len(args['url']) > 40 else args['url']
                    tool_display = f'making request to `{url_preview}`'
                elif func_name == 'read_skill' and args.get('skill_name'):
                    tool_display = f'reading skill: {args["skill_name"]}'
                elif func_name == 'create_skill' and args.get('name'):
                    tool_display = f'creating skill: {args["name"]}'
                elif func_name == 'edit_skill' and args.get('skill_name'):
                    tool_display = f'editing skill: {args["skill_name"]}'
                elif func_name == 'execute_python_code' and args.get('code'):
                    code_preview = args['code'][:40] + '...' if len(args['code']) > 40 else args['code']
                    tool_display = f'running code'
                elif func_name == 'get_current_time':
                    tool_display = 'getting current time'
                elif func_name == 'get_timezone_info' and args.get('timezone'):
                    tool_display = f'checking timezone: {args["timezone"]}'
                elif func_name == 'get_message_reactions':
                    tool_display = 'getting message reactions'
                elif func_name == 'timeout_user' and args.get('user_id'):
                    duration = args.get('duration_minutes', 5)
                    tool_display = f'timing out user for {duration} min'
                elif func_name == 'gif_exit' and args.get('query'):
                    tool_display = f'finding a GIF for: "{args["query"]}"'

                try:
                    await my_msg.edit(content=f'Calling {tool_display}')
                except Exception:
                    pass

                tool_result = await call_tool(func_name, args, my_msg, user_message)

                if tool_result == "__SILENT_EXIT__":
                    return {"choices": [{"message": {"content": "", "finish_reason": "silent_exit"}}]}

                if tool_result.startswith("__GIF_EXIT__:"):
                    gif_url = tool_result.split("__GIF_EXIT__:", 1)[1]
                    return {"choices": [{"message": {"content": gif_url, "finish_reason": "gif_exit"}}]}

                messages.append({
                    "tool_call_id": tc_dict.get('id', ''),
                    "role": "tool",
                    "content": tool_result
                })

            try:
                await my_msg.edit(content="Thinking...")
            except Exception:
                pass

            return await query_nvidia(messages, my_msg, complexity, user_message)
        
        return {
            "choices": [{
                "message": {
                    "content": full_content,
                    "reasoning": full_reasoning
                },
                "finish_reason": "stop"
            }]
        }
        
    except Exception as e:
        print(f"[nvidia] Exception during request: {e}")
        import traceback
        traceback.print_exc()
        return {"choices": [{"message": {"content": "Sorry, I encountered an error. Please try again."}}]}

def run(parent_context_func=None):
    """Run the Discord bot"""
    if token is None:
        raise RuntimeError('DISCORD_BOT_TOKEN environment variable not set')

    if parent_context_func is not None:
        set_parent_context(parent_context_func)

    print("Starting roturbot...")
    try:
        client.run(token)
    except Exception as e:
        print(f"Error running bot: {e}")

@client.event
async def on_message_delete(message):
    """Detect deletion of the most recent counted message and notify the channel."""
    try:
        if message.guild is None:
            return

        channel_id = str(message.channel.id)
        if channel_id != counting.COUNTING_CHANNEL_ID:
            return

        state = counting.get_channel_state(channel_id)
        last_msg_id = state.get('last_count_message_id')
        last_value = state.get('last_count_value')

        if last_msg_id and str(message.id) == str(last_msg_id):
            try:
                deleted_value = int(last_value) if last_value is not None else None
            except:
                deleted_value = None

            if deleted_value is None:
                await message.channel.send("A counted message was deleted. Next number may have changed.")
            else:
                new_current = max(0, deleted_value)
                state['current_count'] = new_current
                state['last_count_message_id'] = None
                state['last_count_value'] = None
                counting.save_state()

                next_number = state['current_count'] + 1
                await message.channel.send(f"user deleted number: {deleted_value}, next number is: {next_number}")
    except Exception as e:
        print(f"Error in on_message_delete: {e}")

if __name__ == "__main__":
    run()
else:
    print("roturbot module imported. Bot will not run automatically.")
