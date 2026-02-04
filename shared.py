import discord
from discord import app_commands
import random
import re

def allowed_everywhere(command):
    command = app_commands.allowed_installs(guilds=True, users=True)(command)
    command = app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)(command)
    return command

catmaid_mode = False

EMOTES = ["nya~", "mew~", ":3", ">w<", "uwu", "*purrs*", "*nuzzles*"]
INSERT_POINTS = [",", ".", "!", "?"]

def catify(text: str | None):
    if text is None:
        return None
    if not catmaid_mode:
        return text

    # Step 1 — light phonetic modifications
    def phonetics(w: str):
        # r/l → w
        w = re.sub(r"[rl]", "w", w)
        w = re.sub(r"[RL]", "W", w)

        # "na" "no" "nu" "ne" → nya/nyo/nyu/nye (25% chance each)
        if random.random() < 0.25:
            w = re.sub(r"\b(n)([aeiou])", r"ny\2", w, flags=re.IGNORECASE)
        return w

    lines = text.split('\n')
    processed_lines = []
    
    for line in lines:
        words = line.split()
        words = [phonetics(w) for w in words]
        new = " ".join(words)
        processed_lines.append(new)
    
    new = '\n'.join(processed_lines)

    # Step 2 — occasional stutter (10% chance)
    if random.random() < 0.10:
        new = re.sub(r"\b([a-zA-Z])", r"\1-\1", new, count=1)

    # Step 3 — add cute suffix (30% chance)
    if random.random() < 0.30:
        new += " " + random.choice(EMOTES)

    # Step 4 — insert meow/nya at natural pause points (20% chance)
    for mark in INSERT_POINTS:
        if mark in new and random.random() < 0.20:
            new = new.replace(mark, f" {random.choice(EMOTES)}{mark}")

    return new


async def send_message(
        ctx: discord.InteractionResponse | discord.Webhook,
        message: str | None = None,
        embed: discord.Embed | None = None,
        embeds: list[discord.Embed] | None = None,
        view: discord.ui.View | None = None,
        allowed_mentions: discord.AllowedMentions | None = None,
        file: discord.File | None = None,
        files: list[discord.File] | None = None,
        ephemeral: bool = False
    ):

    if embed is not None:
        embeds = [embed]
    if embeds is None:
        embeds = []
    if catmaid_mode:
        if message:
            message = catify(message)

        if embeds is not None:
            for embed in embeds:
                if embed.title is not None:
                    embed.title = catify(embed.title)

                if embed.description is not None:
                    embed.description = catify(embed.description)

                for i, field in enumerate(embed.fields):
                    embed.set_field_at(
                        i,
                        name=catify(field.name) if field.name else field.name,
                        value=catify(field.value) if field.value else field.value,
                        inline=field.inline,
                    )

    if message is None:
        message = ""
    if allowed_mentions is None:
        allowed_mentions = discord.AllowedMentions.none()

    if file is not None:
        files = [file]
    if files is None:
        files = []
    
    if isinstance(ctx, discord.InteractionResponse):
        if view is not None:
            await ctx.send_message(message, embeds=embeds, files=files, ephemeral=ephemeral, view=view, allowed_mentions=allowed_mentions)
        else:
            await ctx.send_message(message, embeds=embeds, files=files, ephemeral=ephemeral, allowed_mentions=allowed_mentions)
    else:
        if view is not None:
            await ctx.send(message, embeds=embeds, files=files, ephemeral=ephemeral, view=view, allowed_mentions=allowed_mentions)
        else:
            await ctx.send(message, embeds=embeds, files=files, ephemeral=ephemeral, allowed_mentions=allowed_mentions)
