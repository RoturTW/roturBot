import discord
from discord import app_commands
from ..shared import allowed_everywhere, send_message, catify
from ..helpers import rotur
from openai import AsyncOpenAI
import os
import asyncio
from dotenv import load_dotenv
from datetime import datetime, timezone
import json

def load_personalities():
    personalities_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "personalities")
    personalities = {}
    if not os.path.exists(personalities_dir):
        return personalities
    
    for filename in os.listdir(personalities_dir):
        if filename.endswith(".md"):
            name = filename[:-3]
            filepath = os.path.join(personalities_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    personalities[name] = f.read()
            except Exception as e:
                print(f"Error loading personality {name}: {e}")
    
    return personalities

def get_personality_prompt(personality_name: str = "roturbot") -> str:
    personalities = load_personalities()
    if personality_name in personalities:
        return personalities[personality_name]

    if "roturbot" in personalities:
        return personalities["roturbot"]

    return "Hey there! I'm here to help."

def load_user_personalities():
    try:
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "store", "user_personalities.json"), "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def get_user_personality(user_id: int) -> str:
    user_personalities = load_user_personalities()
    uid = str(user_id)
    
    if uid in user_personalities:
        personalities = load_personalities()
        personality = user_personalities[uid]
        if personality in personalities:
            return personality
    
    return "roturbot"

load_dotenv()

@allowed_everywhere
@app_commands.command(name='ai', description='Ask roturbot a question without conversation context')
async def ai_command(ctx: discord.Interaction, prompt: str):
    await ctx.response.defer()
    
    rotur_user = await rotur.get_user_by('discord_id', str(ctx.user.id))
    if rotur_user is None or rotur_user.get('error') is not None:
        await send_message(ctx.followup, "You are not linked to a rotur account and cannot use this feature.")
        return

    subscription_tier = rotur_user.get('sys.subscription', {}).get('tier', "Free")
    
    if subscription_tier == "Free":
        await send_message(ctx.followup, "Only subscribers can use this feature. Subscribe at https://ko-fi.com/mistium or use the /subscribe command to get lite (15 credits per month)")
        return
    
    current_time = datetime.now(timezone.utc).isoformat()
    current_time_human = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    user_personality = get_user_personality(ctx.user.id)
    personality_prompt = get_personality_prompt(user_personality)
    personality_prompt = f"CURRENT TIME IS: {current_time_human} (ISO: {current_time})\n\n{personality_prompt}"

    safe_user_data = {k: v for k, v in rotur_user.items() if k not in ['key', 'password']}

    messages = [
        {"role": "system", "content": personality_prompt},
        {"role": "system", "content": f"You are talking to the rotur user named: {rotur_user.get('username', 'someone')}. On discord they are {ctx.user.name} ({ctx.user.id}) with display name: {ctx.user.display_name}. This is a context-free AI query - do NOT reference previous messages or conversation."},
        {"role": "system", "content": f"User object (safe fields only): {json.dumps(safe_user_data)}"},
        {"role": "user", "content": prompt},
    ]

    api_key = os.getenv("NVIDIA_API_KEY", "")
    
    try:
        await send_message(ctx.followup, "waiting for nvidia...")
        
        if subscription_tier == "Lite":
            nvidia_client = AsyncOpenAI(
                base_url="https://integrate.api.nvidia.com/v1",
                api_key=api_key
            )
            model = "gpt-oss-120b"
            extra_body = {}
        else:
            nvidia_client = AsyncOpenAI(
                base_url="https://integrate.api.nvidia.com/v1",
                api_key=api_key
            )
            model = "z-ai/glm4.7"
            extra_body = {
                "chat_template_kwargs": {"enable_thinking": True, "clear_thinking": False}
            }

        response = await nvidia_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=1,
            top_p=1,
            max_tokens=4096,
            extra_body=extra_body
        )
        
        # Update to thinking when response comes in
        try:
            await send_message(ctx.followup, "thinking")
        except Exception:
            pass

        content = response.choices[0].message.content or ""

        if subscription_tier == "Lite" and content and content.strip():
            content = "[Lite - gpt-oss-120b] " + content

        if not content or content.strip() == "":
            content = "Sorry, I couldn't generate a response to that."

        if "@everyone" in content or "@here" in content:
            content = content.replace("@everyone", "@ everyone").replace("@here", "@ here")

        await send_message(ctx.followup, catify(content))

    except Exception as e:
        await send_message(ctx.followup, f"Sorry, I encountered an error processing your request: {str(e)}")
