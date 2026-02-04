import discord
from discord import app_commands, ui
import datetime
from typing import Optional

from ..helpers import rotur
from ..shared import allowed_everywhere, send_message

group_cmds = app_commands.Group(name='group', description='Group management')
group_cmds = app_commands.allowed_installs(guilds=True, users=True)(group_cmds)
group_cmds = app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)(group_cmds)

async def _get_linked_token(discord_user_id: int) -> str | None:
    try:
        user = await rotur.get_user_by('discord_id', str(discord_user_id))
    except Exception:
        return None
    if user is None or user.get('error') == 'User not found':
        return None
    return user.get('key')

def _get_linked_token_sync(discord_user_id: int) -> str | None:
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    try:
        user = asyncio.run_coroutine_threadsafe(
            rotur.get_user_by('discord_id', str(discord_user_id)),
            loop
        ).result(timeout=5)
    except Exception:
        return None
    
    if user is None or user.get('error') == 'User not found':
        return None
    return user.get('key')

class GroupCreateModal(ui.Modal):
    tag = ui.TextInput(label='Tag (unique ID)', placeholder='mygroup', min_length=1, max_length=20)
    name = ui.TextInput(label='Name', placeholder='My Awesome Group', min_length=1, max_length=50)
    description = ui.TextInput(label='Description', style=discord.TextStyle.paragraph, placeholder='...', required=False, max_length=500)
    public = ui.TextInput(label='Public? (yes/no)', placeholder='no', default='no')

    def __init__(self):
        super().__init__(title='Create Group')

    async def on_submit(self, interaction: discord.Interaction):
        token = await _get_linked_token(interaction.user.id)
        if not token:
            await interaction.response.send_message("You aren't linked to Rotur.", ephemeral=True)
            return

        tag = self.tag.value.lower().replace(' ', '')
        name = self.name.value
        description = self.description.value
        public = self.public.value.lower() in ['yes', 'y', 'true', '1']

        try:
            status, payload = await rotur.groups_create(token, tag, name, description, "", public)
        except Exception as e:
            await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)
            return

        if status != 201:
            err = "Failed to create group"
            if isinstance(payload, dict):
                err = payload.get('error', err)
            elif isinstance(payload, str):
                err = payload
            await interaction.response.send_message(f"Error: {err}", ephemeral=True)
        else:
            await interaction.response.send_message(f"Group '{name}' ({tag}) created!", ephemeral=True)

class AnnouncementCreateModal(ui.Modal):
    title_input = ui.TextInput(label='Title', placeholder='Important Update!', min_length=1, max_length=100)
    body = ui.TextInput(label='Content', style=discord.TextStyle.paragraph, placeholder='Write your announcement...', min_length=1, max_length=2000)
    ping = ui.TextInput(label='Ping all members? (yes/no)', placeholder='no', default='no')

    def __init__(self, token: Optional[str] = None, group_tag: Optional[str] = None):
        super().__init__(title='Create Announcement')
        self.token = token
        self.group_tag = group_tag

    async def on_submit(self, interaction: discord.Interaction):
        token = self.token
        group_tag = self.group_tag

        if not token or not group_tag:
            await interaction.response.send_message("Error: Missing group context", ephemeral=True)
            return

        title = self.title_input.value
        body = self.body.value
        ping = self.ping.value.lower() in ['yes', 'y', 'true', '1']

        status, payload = await rotur.groups_create_announcement(token, group_tag, title, body, ping)

        if status == 201:
            await interaction.response.send_message(f"Announcement posted to {group_tag}!", ephemeral=True)
        else:
            err = payload.get('error', 'Failed to post announcement')
            await interaction.response.send_message(f"Error: {err}", ephemeral=True)

class EventCreateModal(ui.Modal):
    event_name = ui.TextInput(label='Event Name', placeholder='Weekly Meeting', min_length=1, max_length=100)
    description = ui.TextInput(label='Description', style=discord.TextStyle.paragraph, placeholder='Event details...', required=False, max_length=500)
    location = ui.TextInput(label='Location/Link', placeholder='Discord voice channel or link...', max_length=200)
    start_time = ui.TextInput(label='Start (unix timestamp)', placeholder='Epoch timestamp')
    duration = ui.TextInput(label='Duration (hours)', placeholder='1', default='1')
    visibility = ui.TextInput(label='Visibility (MEMBERS/PUBLIC)', placeholder='MEMBERS', default='MEMBERS')
    publish = ui.TextInput(label='Publish now? (yes/no)', placeholder='no', default='no')

    def __init__(self, token: Optional[str] = None, group_tag: Optional[str] = None):
        super().__init__(title='Create Event')
        self.token = token
        self.group_tag = group_tag

    async def on_submit(self, interaction: discord.Interaction):
        token = self.token
        group_tag = self.group_tag

        if not token or not group_tag:
            await interaction.response.send_message("Error: Missing group context", ephemeral=True)
            return

        try:
            start_ts = int(self.start_time.value)
            duration_hours = int(self.duration.value)
        except ValueError:
            await interaction.response.send_message("Invalid timestamp or duration", ephemeral=True)
            return

        visibility = self.visibility.value.upper()
        if visibility not in ['MEMBERS', 'PUBLIC']:
            visibility = 'MEMBERS'

        publish = self.publish.value.lower() in ['yes', 'y', 'true', '1']

        status, payload = await rotur.groups_create_event(
            token, group_tag, self.event_name.value, self.description.value,
            self.location.value, start_ts, duration_hours, visibility, publish
        )

        if status == 201:
            await interaction.response.send_message(f"Event created for {group_tag}!", ephemeral=True)
        else:
            err = payload.get('error', 'Failed to create event')
            await interaction.response.send_message(f"Error: {err}", ephemeral=True)

class RoleCreateModal(ui.Modal):
    name = ui.TextInput(label='Role Name', placeholder='VIP', min_length=1, max_length=50)
    description = ui.TextInput(label='Description', placeholder='Special members...', max_length=200)
    priority = ui.TextInput(label='Priority (0-100)', placeholder='50', default='50')
    auto_assign = ui.TextInput(label='Auto-assign to new joiners? (yes/no)', placeholder='no')
    self_assign = ui.TextInput(label='Can members self-assign? (yes/no)', placeholder='yes', default='yes')

    def __init__(self, token: Optional[str] = None, group_tag: Optional[str] = None):
        super().__init__(title='Create Role')
        self.token = token
        self.group_tag = group_tag

    async def on_submit(self, interaction: discord.Interaction):
        token = self.token
        group_tag = self.group_tag

        if not token or not group_tag:
            await interaction.response.send_message("Error: Missing group context", ephemeral=True)
            return

        try:
            priority = int(self.priority.value)
        except ValueError:
            priority = 50

        auto_assign = self.auto_assign.value.lower() in ['yes', 'y', 'true', '1']
        self_assign = self.self_assign.value.lower() in ['yes', 'y', 'true', '1']

        status, payload = await rotur.groups_create_role(
            token, group_tag, self.name.value, self.description.value,
            priority, auto_assign, self_assign
        )

        if status == 201:
            await interaction.response.send_message(f"Role created for {group_tag}!", ephemeral=True)
        else:
            err = payload.get('error', 'Failed to create role')
            await interaction.response.send_message(f"Error: {err}", ephemeral=True)

class ViewSelect(ui.Select):
    def __init__(self, is_owner: bool = False):
        options = [
            discord.SelectOption(label="Overview", value="overview"),
            discord.SelectOption(label="Members", value="members"),
            discord.SelectOption(label="Announcements", value="announcements"),
            discord.SelectOption(label="Events", value="events"),
            discord.SelectOption(label="Tips", value="tips"),
            discord.SelectOption(label="Roles", value="roles"),
        ]

        if is_owner:
            options.append(discord.SelectOption(label="Manage", value="manage", description="Create content"))

        super().__init__(placeholder="View...", options=options)
        self.is_owner = is_owner

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if view is None:
            return

        if self.values[0] == "manage":
            manage_view = GroupManagementView(token=view.token, group_tag=view.group_tag, author_id=view.author_id)
            embed = discord.Embed(title="Group Management", color=discord.Color.gold())
            await interaction.response.edit_message(embed=embed, view=manage_view)
        else:
            await view.show_view(self.values[0], interaction)

class ManageSelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Create Announcement", value="create_announce"),
            discord.SelectOption(label="Create Event", value="create_event"),
            discord.SelectOption(label="Create Role", value="create_role"),
            discord.SelectOption(label="View Announcements", value="manage_announce"),
            discord.SelectOption(label="View Events", value="manage_events"),
            discord.SelectOption(label="View Roles", value="manage_roles"),
            discord.SelectOption(label="View Tips", value="view_tips"),
            discord.SelectOption(label="Back to Group", value="back"),
        ]
        super().__init__(placeholder="Actions", options=options)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, GroupManagementView):
            return

        action = self.values[0]

        if action == "back":
            main_view = GroupView(token=view.token, group_tag=view.group_tag, author_id=view.author_id, is_owner=True)
            await main_view.reload()
            embed = main_view.get_overview_embed()
            main_view.add_item(ViewSelect(is_owner=True))
            await interaction.response.edit_message(embed=embed, view=main_view)
        elif action == "create_announce":
            modal = AnnouncementCreateModal(token=view.token, group_tag=view.group_tag)
            await interaction.response.send_modal(modal)
        elif action == "create_event":
            modal = EventCreateModal(token=view.token, group_tag=view.group_tag)
            await interaction.response.send_modal(modal)
        elif action == "create_role":
            modal = RoleCreateModal(token=view.token, group_tag=view.group_tag)
            await interaction.response.send_modal(modal)
        elif action == "manage_announce":
            await view.show_announcements_management(interaction)
        elif action == "manage_events":
            await view.show_events_management(interaction)
        elif action == "manage_roles":
            await view.show_roles_management(interaction)
        elif action == "view_tips":
            await view.show_tips(interaction)

class ActionButtons(ui.View):
    def __init__(self, token: str, group_tag: str, announcement_id: str):
        super().__init__(timeout=300)
        self.token = token
        self.group_tag = group_tag
        self.announcement_id = announcement_id

    @ui.button(label="Delete", style=discord.ButtonStyle.danger)
    async def delete_button(self, interaction: discord.Interaction, button: ui.Button):
        button.disabled = True
        await interaction.response.edit_message(view=self)

        status, _ = await rotur.groups_delete_announcement(self.token, self.group_tag, self.announcement_id)
        if status == 200:
            await interaction.edit_original_response(content="Announcement deleted", embed=None, view=None)
        else:
            await interaction.edit_original_response(content="Failed to delete", view=self)

class GroupView(ui.View):
    def __init__(self, *, token: str, group_tag: str, author_id: int, is_owner: bool = False):
        super().__init__(timeout=300)
        self.token = token
        self.group_tag = group_tag
        self.author_id = author_id
        self.current_view = "overview"
        self.group_data = None
        self.is_owner = is_owner

    async def reload(self) -> dict | None:
        status, payload = await rotur.groups_get(self.token, self.group_tag)
        if status == 200 and isinstance(payload, dict):
            self.group_data = payload
            return payload
        return None

    def get_overview_embed(self) -> discord.Embed:
        group = self.group_data or {}
        color = discord.Color.green() if group.get('public') else discord.Color.blue()

        embed = discord.Embed(
            title=group.get('name', 'Unknown'),
            description=group.get('description') or 'No description.',
            color=color
        )
        embed.set_footer(text=f"Tag: {self.group_tag}")

        stats = []
        stats.append(f"{group.get('credits_balance', 0):.0f} credits")
        stats.append(f"{'Public' if group.get('public') else 'Private'}")

        join_policy = group.get('join_policy', 'OPEN')
        stats.append(join_policy)

        created = group.get('created_at')
        if isinstance(created, (int, float)):
            dt = datetime.datetime.fromtimestamp(created, datetime.UTC)
            days_ago = (datetime.datetime.now(datetime.UTC) - dt).days
            stats.append(f"{days_ago}d ago")

        embed.add_field(name="Info", value=" | ".join(stats), inline=False)

        if self.is_owner:
            embed.add_field(name="Owner", value="Use Manage to create content", inline=False)

        icon = group.get('icon_url')
        if icon and icon.startswith('http'):
            embed.set_thumbnail(url=icon)
        elif icon:
            embed.add_field(name="Icon URL", value=f"[Link]({icon})", inline=False)

        return embed

    def get_members_embed(self) -> discord.Embed:
        group = self.group_data or {}
        embed = discord.Embed(
            title=f"Members - {group.get('name', '')}",
            color=discord.Color.blurple()
        )

        owner = group.get('owner_user_id', '')
        embed.add_field(name="Owner", value=f"`{owner}`", inline=True)
        embed.add_field(name="Total", value=str(group.get('members', 0)), inline=True)

        return embed

    async def get_announcements_embed(self) -> discord.Embed:
        group = self.group_data or {}
        embed = discord.Embed(
            title=f"Announcements - {group.get('name', '')}",
            color=discord.Color.gold()
        )

        status, announcements = await rotur.groups_get_announcements(self.token, self.group_tag, limit=5)
        if status == 200 and announcements:
            for ann in announcements[-5:]:
                dt = datetime.datetime.fromtimestamp(ann.get('created_at', 0), datetime.UTC)
                ping = "[PING] " if ann.get('ping_members') else ""
                title = f"{ping}{ann.get('title', 'Untitled')}"
                body = ann.get('body', '')[:200] + "..." if ann.get('body') else "No content"
                value = f"{body}\n\nAuthor: `{ann.get('author_user_id', '')}`"
                embed.add_field(name=title, value=value, inline=False)
                embed.set_footer(text=f"{dt.strftime('%b %d, %H:%M')}")
        else:
            embed.description = "No announcements yet."

        return embed

    async def get_events_embed(self) -> discord.Embed:
        group = self.group_data or {}
        embed = discord.Embed(
            title=f"Events - {group.get('name', '')}",
            color=discord.Color.orange()
        )

        status, events = await rotur.groups_get_events(self.token, self.group_tag)
        if status == 200 and events:
            for event in events[-5:]:
                dt = datetime.datetime.fromtimestamp(event.get('start_time', 0), datetime.UTC)
                vis = "Public" if event.get('visibility') == "PUBLIC" else "Members"
                title = f"{vis} - {event.get('title', 'Untitled')}"
                loc = event.get('location', 'TBA')[:50]
                value = f"{loc}\n{dt.strftime('%b %d, %H:%M')} (UTC)"
                embed.add_field(name=title, value=value, inline=False)
        else:
            embed.description = "No upcoming events."

        return embed

    async def show_view(self, view_type: str, interaction: discord.Interaction):
        self.current_view = view_type

        if view_type == "overview":
            embed = self.get_overview_embed()
        elif view_type == "members":
            embed = self.get_members_embed()
        elif view_type == "announcements":
            embed = await self.get_announcements_embed()
        elif view_type == "events":
            embed = await self.get_events_embed()
        elif view_type == "tips":
            embed = await self.get_tips_embed()
        elif view_type == "roles":
            embed = await self.get_roles_embed()
        else:
            return

        await interaction.response.edit_message(embed=embed, view=self)

    async def get_tips_embed(self) -> discord.Embed:
        group = self.group_data or {}
        embed = discord.Embed(
            title=f"Tips - {group.get('name', '')}",
            description=f"Balance: {group.get('credits_balance', 0):.0f} credits",
            color=discord.Color.gold()
        )

        status, tips = await rotur.groups_get_tips(self.token, self.group_tag, limit=10)
        if status == 200 and tips:
            for tip in tips[-10:]:
                dt = datetime.datetime.fromtimestamp(tip.get('created_at', 0), datetime.UTC)
                amount = tip.get('amount_credits', 0)
                from_user = tip.get('from_user_id', 'Anonymous')
                embed.add_field(
                    name=f"{amount:.0f} credits",
                    value=f"From: `{from_user}`\n{dt.strftime('%b %d, %H:%M')}",
                    inline=False
                )
        else:
            embed.add_field(name="No tips yet", value="Members can tip this group!", inline=False)

        return embed

    async def get_roles_embed(self) -> discord.Embed:
        group = self.group_data or {}
        embed = discord.Embed(
            title=f"Roles - {group.get('name', '')}",
            color=discord.Color.purple()
        )

        status, roles = await rotur.groups_get_roles(self.token, self.group_tag)
        if status == 200 and roles:
            for role in sorted(roles, key=lambda r: r.get('priority', 0), reverse=True):
                name = role.get('name', 'Unknown')
                desc = role.get('description', 'No description')
                priority = role.get('priority', 0)
                auto = "Yes" if role.get('assign_on_join') else "No"
                self_assign = "Yes" if role.get('self_assignable') else "No"

                embed.add_field(
                    name=f"{name} (Prio: {priority})",
                    value=f"{desc}\nAuto: {auto} | Self: {self_assign}",
                    inline=False
                )
        else:
            embed.description = "No roles defined."

        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This panel isn't for you.", ephemeral=True)
            return False
        return True

class GroupManagementView(ui.View):
    def __init__(self, *, token: str, group_tag: str, author_id: int):
        super().__init__(timeout=300)
        self.token = token
        self.group_tag = group_tag
        self.author_id = author_id
        self.add_item(ManageSelect())

    async def show_announcements_management(self, interaction: discord.Interaction):
        status, announcements = await rotur.groups_get_announcements(self.token, self.group_tag, limit=10)

        if status != 200 or not announcements:
            await interaction.response.send_message("No announcements found", ephemeral=True)
            return

        embed = discord.Embed(title="Announcements", color=discord.Color.gold())
        for ann in announcements[-10:]:
            ann_id = ann.get('id', '')
            dt = datetime.datetime.fromtimestamp(ann.get('created_at', 0), datetime.UTC)
            embed.add_field(
                name=f"{ann.get('title', 'Untitled')} [ID: {ann_id[:8]}...]",
                value=f"{ann.get('body', '')[:150]}...\n{dt.strftime('%b %d, %H:%M')}",
                inline=False
            )

        view = ActionButtons(self.token, self.group_tag, announcements[-1].get('id', ''))
        embed.set_footer(text="Click Delete button, then re-open to delete others")
        await interaction.response.edit_message(embed=embed, view=view)

    async def show_events_management(self, interaction: discord.Interaction):
        status, events = await rotur.groups_get_events(self.token, self.group_tag)

        if status != 200 or not events:
            await interaction.response.send_message("No events found", ephemeral=True)
            return

        embed = discord.Embed(title="Events", color=discord.Color.orange())
        for event in events[-10:]:
            dt = datetime.datetime.fromtimestamp(event.get('start_time', 0), datetime.UTC)
            vis = "Public" if event.get('visibility') == "PUBLIC" else "Members"
            embed.add_field(
                name=f"{vis} - {event.get('title', 'Untitled')}",
                value=f"{event.get('location', 'TBA')}\n{dt.strftime('%b %d, %H:%M')}",
                inline=False
            )

        await interaction.response.edit_message(embed=embed, view=None)

    async def show_roles_management(self, interaction: discord.Interaction):
        status, roles = await rotur.groups_get_roles(self.token, self.group_tag)

        if status != 200 or not roles:
            await interaction.response.send_message("No roles found", ephemeral=True)
            return

        embed = discord.Embed(title="Roles", color=discord.Color.purple())
        for role in sorted(roles, key=lambda r: r.get('priority', 0), reverse=True):
            name = role.get('name', 'Unknown')
            perms = role.get('permissions', [])
            perm_str = ", ".join(perms[:3]) + ("..." if len(perms) > 3 else "")
            embed.add_field(
                name=name,
                value=perm_str or 'No permissions',
                inline=False
            )

        await interaction.response.edit_message(embed=embed, view=None)

    async def show_tips(self, interaction: discord.Interaction):
        status, tips = await rotur.groups_get_tips(self.token, self.group_tag, limit=20)

        if status != 200 or not tips:
            await interaction.response.send_message("No tips found", ephemeral=True)
            return

        embed = discord.Embed(title="Recent Tips", color=discord.Color.gold())
        total = sum(t.get('amount_credits', 0) for t in tips)
        embed.description = f"Total shown: {total:.0f} credits"

        for tip in tips[-20:]:
            dt = datetime.datetime.fromtimestamp(tip.get('created_at', 0), datetime.UTC)
            amount = tip.get('amount_credits', 0)
            from_user = tip.get('from_user_id', 'Unknown')
            embed.add_field(
                name=f"{amount:.0f} credits",
                value=f"From: `{from_user}`\n{dt.strftime('%b %d, %H:%M')}",
                inline=False
            )

        await interaction.response.edit_message(embed=embed, view=None)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This panel isn't for you.", ephemeral=True)
            return False
        return True

@allowed_everywhere
@group_cmds.command(name='create', description='Create a new group')
async def group_create(ctx: discord.Interaction):
    token = await _get_linked_token(ctx.user.id)
    if not token:
        await send_message(ctx.response, "You aren't linked to Rotur.", ephemeral=True)
        return

    modal = GroupCreateModal()
    await ctx.response.send_modal(modal)

@allowed_everywhere
@group_cmds.command(name='get', description='View a group by tag')
@app_commands.describe(tag='Group tag')
async def group_get(ctx: discord.Interaction, tag: str):
    token = await _get_linked_token(ctx.user.id)
    if not token:
        await send_message(ctx.response, "You aren't linked to Rotur.", ephemeral=True)
        return

    tag = tag.lower()
    status, user_data = await rotur.profile_by_discord_id(ctx.user.id)
    if status != 200:
        await send_message(ctx.response, "Failed to get your user ID", ephemeral=True)
        return

    user_id = user_data.get('sys.id', '')

    status, group_data = await rotur.groups_get(token, tag)
    if status != 200:
        await send_message(ctx.response, "Group not found", ephemeral=True)
        return

    is_owner = group_data.get('owner_user_id', '') == user_id

    view = GroupView(token=token, group_tag=tag, author_id=ctx.user.id, is_owner=is_owner)
    await view.reload()
    embed = view.get_overview_embed()
    view.add_item(ViewSelect(is_owner=is_owner))

    await send_message(ctx.response, embed=embed, view=view)

@allowed_everywhere
@group_cmds.command(name='search', description='Search for groups')
@app_commands.describe(query='Search query (name or description)')
async def group_search(ctx: discord.Interaction, query: str):
    token = await _get_linked_token(ctx.user.id)
    if not token:
        await send_message(ctx.response, "You aren't linked to Rotur.", ephemeral=True)
        return

    status, groups = await rotur.groups_search(token, query)

    if status != 200 or not groups:
        await send_message(ctx.response, "No groups found matching your query.", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"Search Results for '{query}'",
        description=f"Found {len(groups)} group(s)",
        color=discord.Color.gold()
    )

    for group in groups[:10]:
        tag = group.get('tag', 'unknown')
        name = group.get('name', 'Unknown')
        desc = group.get('description', 'No description')[:100]
        members = group.get('members', 0)
        public = "Public" if group.get('public') else "Private"

        value = f"{desc}\n{public} | {members} members"
        embed.add_field(name=f"{name} (`{tag}`)", value=value, inline=False)

    if len(groups) > 10:
        embed.set_footer(text=f"Showing 10 of {len(groups)} results")

    await send_message(ctx.response, embed=embed)

@allowed_everywhere
@group_cmds.command(name='my', description='View your groups')
async def group_my(ctx: discord.Interaction):
    token = await _get_linked_token(ctx.user.id)
    if not token:
        await send_message(ctx.response, "You aren't linked to Rotur.", ephemeral=True)
        return

    status, groups = await rotur.groups_get_mine(token)

    if status != 200 or not groups:
        await send_message(ctx.response, "You're not a member of any groups.", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"Your Groups ({len(groups)})",
        color=discord.Color.blurple()
    )

    for group in groups[:15]:
        tag = group.get('tag', 'unknown')
        name = group.get('name', 'Unknown')
        desc = group.get('description', 'No description')[:80]
        public = "Public" if group.get('public') else "Private"

        value = f"{desc}\n{public}"
        embed.add_field(name=f"{name} (`{tag}`)", value=value, inline=False)

    if len(groups) > 15:
        embed.set_footer(text=f"Showing 15 of {len(groups)} groups")

    await send_message(ctx.response, embed=embed)

@allowed_everywhere
@group_cmds.command(name='join', description='Join a public group')
@app_commands.describe(tag='Group tag')
async def group_join(ctx: discord.Interaction, tag: str):
    token = await _get_linked_token(ctx.user.id)
    if not token:
        await send_message(ctx.response, "You aren't linked to Rotur.", ephemeral=True)
        return

    tag = tag.lower()
    status, _ = await rotur.groups_join(token, tag)

    if status == 200:
        await send_message(ctx.response, f"You have joined the group `{tag}`!")
    else:
        err = _get_error_from_status(status)
        await send_message(ctx.response, f"Error: {err}", ephemeral=True)

@allowed_everywhere
@group_cmds.command(name='leave', description='Leave a group')
@app_commands.describe(tag='Group tag')
async def group_leave(ctx: discord.Interaction, tag: str):
    token = await _get_linked_token(ctx.user.id)
    if not token:
        await send_message(ctx.response, "You aren't linked to Rotur.", ephemeral=True)
        return

    tag = tag.lower()
    status, _ = await rotur.groups_leave(token, tag)

    if status == 200:
        await send_message(ctx.response, f"You have left the group `{tag}`.")
    else:
        err = _get_error_from_status(status)
        await send_message(ctx.response, f"Error: {err}", ephemeral=True)

@allowed_everywhere
@group_cmds.command(name='represent', description='Represent a group')
@app_commands.describe(tag='Group tag')
async def group_represent(ctx: discord.Interaction, tag: str):
    token = await _get_linked_token(ctx.user.id)
    if not token:
        await send_message(ctx.response, "You aren't linked to Rotur.", ephemeral=True)
        return

    tag = tag.lower()
    status, _ = await rotur.groups_represent(token, tag)

    if status == 200:
        await send_message(ctx.response, f"You are now representing the group `{tag}`.")
    else:
        err = _get_error_from_status(status)
        await send_message(ctx.response, f"Error: {err}", ephemeral=True)

@allowed_everywhere
@group_cmds.command(name='announce', description='Post an announcement to a group')
@app_commands.describe(tag='Group tag')
async def group_announce(ctx: discord.Interaction, tag: str):
    token = await _get_linked_token(ctx.user.id)
    if not token:
        await send_message(ctx.response, "You aren't linked to Rotur.", ephemeral=True)
        return

    tag = tag.lower()
    status, group_data = await rotur.groups_get(token, tag)
    if status != 200:
        await send_message(ctx.response, "Group not found", ephemeral=True)
        return

    modal = AnnouncementCreateModal(token=token, group_tag=tag)
    await ctx.response.send_modal(modal)

@allowed_everywhere
@group_cmds.command(name='event', description='Create an event for a group')
@app_commands.describe(tag='Group tag')
async def group_event(ctx: discord.Interaction, tag: str):
    token = await _get_linked_token(ctx.user.id)
    if not token:
        await send_message(ctx.response, "You aren't linked to Rotur.", ephemeral=True)
        return

    tag = tag.lower()
    status, group_data = await rotur.groups_get(token, tag)
    if status != 200:
        await send_message(ctx.response, "Group not found", ephemeral=True)
        return

    modal = EventCreateModal(token=token, group_tag=tag)
    await ctx.response.send_modal(modal)

@allowed_everywhere
@group_cmds.command(name='tip', description='Tip a group with credits')
@app_commands.describe(tag='Group tag', amount='Amount to tip')
async def group_tip(ctx: discord.Interaction, tag: str, amount: float):
    token = await _get_linked_token(ctx.user.id)
    if not token:
        await send_message(ctx.response, "You aren't linked to Rotur.", ephemeral=True)
        return

    if amount <= 0:
        await send_message(ctx.response, "Amount must be positive", ephemeral=True)
        return

    status, _ = await rotur.groups_send_tip(token, tag.lower(), amount)
    if status == 201:
        await send_message(ctx.response, f"Sent {amount} credits to {tag}!")
    else:
        err = _get_error_from_status(status)
        await send_message(ctx.response, f"Error: {err}", ephemeral=True)

@allowed_everywhere
@group_cmds.command(name='role_assign', description='Assign a role to a member')
@app_commands.describe(tag='Group tag', role_id='Role ID', username='Username (optional, leaves blank for self)')
async def role_assign(ctx: discord.Interaction, tag: str, role_id: str, username: Optional[str] = None):
    token = await _get_linked_token(ctx.user.id)
    if not token:
        await send_message(ctx.response, "You aren't linked to Rotur.", ephemeral=True)
        return

    if username is None:
        status, user_data = await rotur.profile_by_discord_id(ctx.user.id)
        if status != 200:
            await send_message(ctx.response, "Failed to get your user ID", ephemeral=True)
            return
        target_user = user_data.get('username', '')
    else:
        target_user = username

    status, _ = await rotur.groups_assign_role(token, tag.lower(), target_user, role_id)
    if status == 200:
        await send_message(ctx.response, f"Role assigned to {target_user}")
    else:
        err = _get_error_from_status(status)
        await send_message(ctx.response, f"Error: {err}", ephemeral=True)

@allowed_everywhere
@group_cmds.command(name='role_remove', description='Remove a role from a member')
@app_commands.describe(tag='Group tag', role_id='Role ID', username='Username (optional, leaves blank for self)')
async def role_remove(ctx: discord.Interaction, tag: str, role_id: str, username: Optional[str] = None):
    token = await _get_linked_token(ctx.user.id)
    if not token:
        await send_message(ctx.response, "You aren't linked to Rotur.", ephemeral=True)
        return

    if username is None:
        status, user_data = await rotur.profile_by_discord_id(ctx.user.id)
        if status != 200:
            await send_message(ctx.response, "Failed to get your user ID", ephemeral=True)
            return
        target_user = user_data.get('username', '')
    else:
        target_user = username

    status, _ = await rotur.groups_remove_role(token, tag.lower(), target_user, role_id)
    if status == 200:
        await send_message(ctx.response, f"Role removed from {target_user}")
    else:
        err = _get_error_from_status(status)
        await send_message(ctx.response, f"Error: {err}", ephemeral=True)

@allowed_everywhere
@group_cmds.command(name='delete', description='Delete a group you own')
@app_commands.describe(tag='Group tag')
async def group_delete(ctx: discord.Interaction, tag: str):
    token = await _get_linked_token(ctx.user.id)
    if not token:
        await send_message(ctx.response, "You aren't linked to Rotur.", ephemeral=True)
        return

    tag = tag.lower()
    status, group_data = await rotur.groups_get(token, tag)
    if status != 200:
        await send_message(ctx.response, "Group not found", ephemeral=True)
        return

    status, user_data = await rotur.profile_by_discord_id(ctx.user.id)
    if status != 200:
        await send_message(ctx.response, "Failed to get your user ID", ephemeral=True)
        return

    user_id = user_data.get('sys.id', '')
    if group_data.get('owner_user_id', '') != user_id:
        await send_message(ctx.response, "You must be the group owner to delete it.", ephemeral=True)
        return

    status, payload = await rotur.groups_delete(token, tag)
    if status == 200:
        await send_message(ctx.response, f"Group `{tag}` has been deleted.")
    else:
        err = payload.get('error', _get_error_from_status(status))
        await send_message(ctx.response, f"Error: {err}", ephemeral=True)

def _get_error_from_status(status: int) -> str:
    errors = {
        400: "Bad request - check your input",
        403: "You're not authorized",
        404: "Not found",
        500: "Server error"
    }
    return errors.get(status, f"Error (status {status})")
