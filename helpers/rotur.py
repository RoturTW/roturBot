import os
import aiohttp
import urllib.parse
from typing import Any

server = os.getenv("CENTRAL_SERVER", "https://api.rotur.dev")
ADMIN_HEADERS = {
    "Authorization": os.getenv("ADMIN_TOKEN"),
    "Content-Type": "application/json",
}

TIMEOUT = aiohttp.ClientTimeout(total=5)

_session: aiohttp.ClientSession | None = None


async def get_session():
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(timeout=TIMEOUT)
    return _session


def get_base_url() -> str:
    """Return the Rotur API base URL."""
    return os.getenv("CENTRAL_SERVER", "https://api.rotur.dev").rstrip("/")


def build_url(path: str) -> str:
    """Build an absolute URL for the Rotur API.

    Accepts either a path ("/me") or a full URL.
    """
    if not path:
        return get_base_url()

    if path.startswith("http://") or path.startswith("https://"):
        return path

    if not path.startswith("/"):
        path = "/" + path

    return get_base_url() + path


async def _safe_json_from_aiohttp(resp: aiohttp.ClientResponse) -> Any:
    try:
        return await resp.json(content_type=None)
    except Exception:
        return {}


async def api_json(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: Any | None = None,
    data: Any | None = None,
    headers: dict[str, str] | None = None,
    timeout_total: float | None = None,
) -> tuple[int, Any]:
    """Make a request to the Rotur API and return (status, json-like payload)."""
    session = await get_session()

    request_timeout: aiohttp.ClientTimeout | None = None
    if timeout_total is not None:
        request_timeout = aiohttp.ClientTimeout(total=timeout_total)

    async with session.request(
        method.upper(),
        build_url(path),
        params=params,
        json=json_body,
        data=data,
        headers=headers,
        timeout=request_timeout,
    ) as resp:
        payload = await _safe_json_from_aiohttp(resp)
        return resp.status, payload


async def api_text(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: Any | None = None,
    data: Any | None = None,
    headers: dict[str, str] | None = None,
    timeout_total: float | None = None,
) -> tuple[int, str]:
    session = await get_session()

    request_timeout: aiohttp.ClientTimeout | None = None
    if timeout_total is not None:
        request_timeout = aiohttp.ClientTimeout(total=timeout_total)

    async with session.request(
        method.upper(),
        build_url(path),
        params=params,
        json=json_body,
        data=data,
        headers=headers,
        timeout=request_timeout,
    ) as resp:
        return resp.status, await resp.text()

async def friends_request(auth: str, username: str) -> tuple[int, Any]:
    return await api_json("POST", f"/friends/request/{username}", params={"auth": auth}, timeout_total=10)


async def friends_remove(auth: str, username: str) -> tuple[int, Any]:
    return await api_json("POST", f"/friends/remove/{username}", params={"auth": auth}, timeout_total=10)


async def friends_list(auth: str) -> tuple[int, Any]:
    return await api_json("GET", "/friends", params={"auth": auth}, timeout_total=10)


async def friends_accept(auth: str, username: str) -> tuple[int, Any]:
    return await api_json("POST", f"/friends/accept/{username}", params={"auth": auth}, timeout_total=10)


async def friends_reject(auth: str, username: str) -> tuple[int, Any]:
    return await api_json("POST", f"/friends/reject/{username}", params={"auth": auth}, timeout_total=10)


async def profile_by_discord_id(discord_id: int | str) -> tuple[int, Any]:
    return await api_json(
        "GET",
        "/profile",
        params={"include_posts": 0, "discord_id": str(discord_id)},
    )


async def profile_by_name(username: str) -> tuple[int, Any]:
    return await api_json(
        "GET",
        "/profile",
        params={"include_posts": 0, "name": username},
    )


async def profile_by_username(username: str, include_posts: int = 0) -> tuple[int, Any]:
    return await api_json(
        "GET",
        "/profile",
        params={"include_posts": int(include_posts), "username": username},
    )


async def stats_users() -> tuple[int, Any]:
    return await api_json("GET", "/stats/users")


async def stats_followers() -> tuple[int, Any]:
    return await api_json("GET", "/stats/followers")


async def stats_systems() -> tuple[int, Any]:
    return await api_json("GET", "/stats/systems")


async def follow_user(auth: str, username: str) -> tuple[int, Any]:
    return await api_json("GET", "/follow", params={"auth": auth, "name": username})


async def unfollow_user(auth: str, username: str) -> tuple[int, Any]:
    return await api_json("GET", "/unfollow", params={"auth": auth, "name": username})


async def following(username: str) -> tuple[int, Any]:
    return await api_json("GET", "/following", params={"name": username})


async def keys_buy(key_id: str, auth: str) -> tuple[int, Any]:
    return await api_json("GET", f"/keys/buy/{key_id}", params={"auth": auth})


async def keys_cancel(key_id: str, auth: str) -> tuple[int, Any]:
    return await api_json("DELETE", f"/keys/cancel/{key_id}", params={"auth": auth})


async def users_patch(auth: str, key: str, value: Any) -> tuple[int, Any]:
    return await api_json(
        "PATCH",
        "/users",
        json_body={"key": key, "value": value, "auth": auth},
        headers={"Content-Type": "application/json"},
    )


async def users_delete(auth: str, key: str) -> tuple[int, Any]:
    # Some endpoints return 204 with empty body.
    status, payload = await api_json(
        "DELETE",
        "/users",
        json_body={"key": key, "auth": auth},
        headers={"Content-Type": "application/json"},
    )
    return status, payload

async def get_user_login(username: str, password_hash: str) -> tuple[int, Any]:
    return await api_json("GET", "/get_user", params={"username": username, "password": password_hash})


async def refresh_token(auth: str) -> tuple[int, Any]:
    return await api_json("POST", "/me/refresh_token", params={"auth": auth})


async def transfer(auth: str, to: str, amount: float, note: str = "") -> tuple[int, Any]:
    return await api_json(
        "POST",
        "/me/transfer",
        params={"auth": auth},
        json_body={"to": to, "amount": amount, "note": note},
        headers={"Content-Type": "application/json"},
    )


async def marriage_propose(auth: str, username: str) -> tuple[int, Any]:
    return await api_json("POST", f"/marriage/propose/{username}", params={"auth": auth}, timeout_total=10)


async def marriage_accept(auth: str) -> tuple[int, Any]:
    return await api_json("POST", "/marriage/accept", params={"auth": auth}, timeout_total=10)


async def marriage_reject(auth: str) -> tuple[int, Any]:
    return await api_json("POST", "/marriage/reject", params={"auth": auth}, timeout_total=10)


async def marriage_cancel(auth: str) -> tuple[int, Any]:
    return await api_json("POST", "/marriage/cancel", params={"auth": auth}, timeout_total=10)


async def marriage_divorce(auth: str) -> tuple[int, Any]:
    return await api_json("POST", "/marriage/divorce", params={"auth": auth}, timeout_total=10)


async def marriage_status(auth: str) -> tuple[int, Any]:
    return await api_json("GET", "/marriage/status", params={"auth": auth}, timeout_total=10)


async def search_posts(query: str, limit: int = 20) -> tuple[int, Any]:
    return await api_json("GET", "/search_posts", params={"limit": int(limit), "q": query})


def bio_from_obj(obj):
    tier = str(obj.get("subscription", "Free"))

    string = (
        f"{tier}\n"
        f'{obj.get("followers", "0")} Followers\n'
        f'Account #{obj.get("index", "unknown")}\n'
    )
    if obj.get("married_to"):
        string += f'Married to {obj["married_to"]}\n'

    string += f'\n{obj.get("bio", "")}\n'
    return string

async def get_user_by(key, value):
    session = await get_session()
    async with session.get(
        f"{get_base_url()}/admin/get_user_by",
        params={"key": key},
        json={"value": value},
        headers=ADMIN_HEADERS,
    ) as resp:
        return await resp.json()
    
    # Group API wrappers
    
async def groups_create(auth: str, tag: str, name: str, description: str = "", icon: str = "", public: bool = False) -> tuple[int, Any]:
    """Create a new group."""
    params = {"tag": tag, "name": name, "description": description, "icon": icon, "public": str(public).lower(), "auth": auth}
    return await api_json("POST", "/groups/create", params=params, timeout_total=10)

async def groups_search(auth: str, query: str) -> tuple[int, Any]:
    """Search groups."""
    params = {"query": query, "auth": auth}
    return await api_json("GET", "/groups/search", params=params, timeout_total=10)

async def groups_join(auth: str, grouptag: str) -> tuple[int, Any]:
    """Join a group."""
    return await api_json("POST", f"/groups/{grouptag}/join", params={"auth": auth}, timeout_total=10)

async def groups_leave(auth: str, grouptag: str) -> tuple[int, Any]:
    """Leave a group."""
    return await api_json("POST", f"/groups/{grouptag}/leave", params={"auth": auth}, timeout_total=10)

async def groups_get(auth: str, grouptag: str) -> tuple[int, Any]:
    """Get a group."""
    return await api_json("GET", f"/groups/{grouptag}", params={"auth": auth}, timeout_total=10)

async def groups_update(auth: str, grouptag: str, description: str | None = None, icon: str | None = None, public: bool | None = None) -> tuple[int, Any]:
    """Update a group. Only fields provided are updated."""
    json_body: dict[str, Any] = {}
    if description is not None:
        json_body["description"] = description
    if icon is not None:
        json_body["icon"] = icon
    if public is not None:
        json_body["public"] = public
    return await api_json("PATCH", f"/groups/{grouptag}?auth={auth}", json_body=json_body, timeout_total=10)

async def groups_delete(auth: str, grouptag: str) -> tuple[int, Any]:
    """Delete a group."""
    return await api_json("DELETE", f"/groups/{grouptag}", json_body={"auth": auth}, timeout_total=10)

async def groups_represent(auth: str, grouptag: str) -> tuple[int, Any]:
    """Represent a group (set as sys.group)."""
    return await api_json("POST", f"/groups/{grouptag}/rep", params={"auth": auth}, timeout_total=10)

async def groups_disrepresent(auth: str, grouptag: str) -> tuple[int, Any]:
    """Disrepresent a group."""
    return await api_json("POST", f"/groups/{grouptag}/disrep", params={"auth": auth}, timeout_total=10)

async def groups_report(auth: str, grouptag: str) -> tuple[int, Any]:
    """Report a group."""
    return await api_json("POST", f"/groups/{grouptag}/report", params={"auth": auth}, timeout_total=10)

async def groups_get_mine(auth: str) -> tuple[int, Any]:
    """Get groups the user is a member of."""
    return await api_json("GET", "/groups/mine", params={"auth": auth}, timeout_total=10)

async def groups_get_announcements(auth: str, grouptag: str, limit: int = 10) -> tuple[int, Any]:
    """Get group announcements."""
    return await api_json("GET", f"/groups/{grouptag}/announcements", params={"auth": auth, "limit": limit}, timeout_total=10)

async def groups_create_announcement(auth: str, grouptag: str, title: str, body: str = "", ping_members: bool = False) -> tuple[int, Any]:
    """Create an announcement."""
    params = {"auth": auth, "title": title, "body": body, "ping_members": str(ping_members).lower()}
    return await api_json("POST", f"/groups/{grouptag}/announcements", params=params, timeout_total=10)

async def groups_delete_announcement(auth: str, grouptag: str, announcement_id: str) -> tuple[int, Any]:
    """Delete an announcement."""
    return await api_json("DELETE", f"/groups/{grouptag}/announcements/{announcement_id}", params={"auth": auth}, timeout_total=10)

async def groups_toggle_announcement_mute(auth: str, grouptag: str) -> tuple[int, Any]:
    """Toggle announcement mute status."""
    return await api_json("POST", f"/groups/{grouptag}/announcements/mute", params={"auth": auth}, timeout_total=10)

async def groups_get_events(auth: str, grouptag: str) -> tuple[int, Any]:
    """Get group events."""
    return await api_json("GET", f"/groups/{grouptag}/events", params={"auth": auth}, timeout_total=10)

async def groups_create_event(auth: str, grouptag: str, title: str, description: str = "", location: str = "",
                            start_time: int = 0, duration_hours: int = 1,
                            visibility: str = "MEMBERS", published: bool = False) -> tuple[int, Any]:
    """Create an event."""
    params = {
        "auth": auth,
        "title": title,
        "description": description,
        "location": location,
        "start_time": str(start_time),
        "duration_hours": str(duration_hours),
        "visibility": visibility,
        "published": str(published).lower(),
    }
    return await api_json("POST", f"/groups/{grouptag}/events", params=params, timeout_total=10)

async def groups_send_tip(auth: str, grouptag: str, amount: float) -> tuple[int, Any]:
    """Send a tip to a group."""
    params = {"auth": auth, "amount": str(amount)}
    return await api_json("POST", f"/groups/{grouptag}/tips", params=params, timeout_total=10)

async def groups_get_tips(auth: str, grouptag: str, limit: int = 20) -> tuple[int, Any]:
    """Get group tips."""
    return await api_json("GET", f"/groups/{grouptag}/tips", params={"auth": auth, "limit": limit}, timeout_total=10)

async def groups_get_roles(auth: str, grouptag: str) -> tuple[int, Any]:
    """Get group roles."""
    return await api_json("GET", f"/groups/{grouptag}/roles", params={"auth": auth}, timeout_total=10)

async def groups_create_role(auth: str, grouptag: str, name: str, description: str = "",
                            priority: int = 50, assign_on_join: bool = False,
                            self_assignable: bool = False) -> tuple[int, Any]:
    """Create a role."""
    params = {
        "auth": auth,
        "name": name,
        "description": description,
        "priority": str(priority),
        "assign_on_join": str(assign_on_join).lower(),
        "self_assignable": str(self_assignable).lower(),
    }
    return await api_json("POST", f"/groups/{grouptag}/roles", params=params, timeout_total=10)

async def groups_update_role(auth: str, grouptag: str, role_id: str, **kwargs) -> tuple[int, Any]:
    """Update a role."""
    return await api_json("PATCH", f"/groups/{grouptag}/roles/{role_id}?auth={auth}", json_body=kwargs, timeout_total=10)

async def groups_delete_role(auth: str, grouptag: str, role_id: str) -> tuple[int, Any]:
    """Delete a role."""
    return await api_json("DELETE", f"/groups/{grouptag}/roles/{role_id}", params={"auth": auth}, timeout_total=10)

async def groups_get_user_roles(auth: str, grouptag: str, user_id: str) -> tuple[int, Any]:
    """Get a user's roles in a group."""
    return await api_json("GET", f"/groups/{grouptag}/members/{user_id}/roles", params={"auth": auth}, timeout_total=10)

async def groups_get_user_permissions(auth: str, grouptag: str, user_id: str) -> tuple[int, Any]:
    """Get a user's permissions in a group."""
    return await api_json("GET", f"/groups/{grouptag}/members/{user_id}/permissions", params={"auth": auth}, timeout_total=10)

async def groups_get_user_benefits(auth: str, grouptag: str, user_id: str) -> tuple[int, Any]:
    """Get a user's benefits from a group."""
    return await api_json("GET", f"/groups/{grouptag}/members/{user_id}/benefits", params={"auth": auth}, timeout_total=10)

async def groups_assign_role(auth: str, grouptag: str, user_id: str, role_id: str) -> tuple[int, Any]:
    """Assign a role to a user."""
    return await api_json("POST", f"/groups/{grouptag}/members/{user_id}/roles/{role_id}", params={"auth": auth}, timeout_total=10)

async def groups_remove_role(auth: str, grouptag: str, user_id: str, role_id: str) -> tuple[int, Any]:
    """Remove a role from a user."""
    return await api_json("DELETE", f"/groups/{grouptag}/members/{user_id}/roles/{role_id}", params={"auth": auth}, timeout_total=10)


async def update_user(type, username, key=None, value=None):
    session = await get_session()
    payload = {
        "type": type,
        "username": username,
        "key": key,
        "value": value,
    }
    async with session.post(
        f"{get_base_url()}/admin/update_user",
        json=payload,
        headers=ADMIN_HEADERS,
    ) as resp:
        return await resp.json()


async def add_subscription(username, tier):
    session = await get_session()
    async with session.post(
        f"{get_base_url()}/admin/set_sub",
        json={"username": username, "tier": tier},
        headers=ADMIN_HEADERS,
    ) as resp:
        return await resp.json()


async def delete_user(username):
    session = await get_session()
    async with session.post(
        f"{get_base_url()}/admin/delete_user",
        json={"username": username},
        headers=ADMIN_HEADERS,
    ) as resp:
        return await resp.json()

async def ban_user(username):
    session = await get_session()
    async with session.post(
        f"{get_base_url()}/admin/ban_user",
        json={"username": username},
        headers=ADMIN_HEADERS,
    ) as resp:
        return await resp.json()

async def transfer_credits(from_username, to_username, amount, note=""):
    session = await get_session()
    query = urllib.parse.urlencode({
        "to": to_username,
        "amount": str(amount),
        "from": from_username,
        "note": note,
    })
    async with session.post(
        f"{get_base_url()}/admin/transfer_credits?{query}",
        headers=ADMIN_HEADERS,
    ) as resp:
        return await resp.json()

async def block_user(token, username):
    session = await get_session()
    async with session.post(
        f"{get_base_url()}/me/block/{username}?auth={token}"
    ) as resp:
        if resp.status == 200:
            return f"You are now blocking {username}."
        return (await resp.json()).get("error", "Unknown error occurred.")


async def unblock_user(token, username):
    session = await get_session()
    async with session.post(
        f"{get_base_url()}/me/unblock/{username}?auth={token}"
    ) as resp:
        if resp.status == 200:
            return f"You are no longer blocking {username}."
        return (await resp.json()).get("error", "Unknown error occurred.")


async def get_users(system, token):
    session = await get_session()
    async with session.get(
        f"{get_base_url()}/system/users",
        params={"auth": token, "system": system},
    ) as resp:
        return await resp.json()


async def get_user(token):
    session = await get_session()
    async with session.get(
        f"{get_base_url()}/me",
        params={"auth": token},
    ) as resp:
        return await resp.json()

async def get_user_file_size(token, username):
    session = await get_session()
    async with session.get(
        f"{get_base_url()}/files/usage?auth={token}",
        params={"username": username},
    ) as resp:
        return await resp.json()

async def close():
    global _session
    if _session:
        await _session.close()


async def set_standing(username: str, level: str, reason: str) -> tuple[int, Any]:
    session = await get_session()
    payload = {
        "username": username,
        "level": level,
        "reason": reason,
    }
    async with session.post(
        f"{get_base_url()}/admin/set_standing",
        json=payload,
        headers=ADMIN_HEADERS,
    ) as resp:
        return resp.status, await resp.json()


async def get_standing_history(username: str) -> tuple[int, Any]:
    session = await get_session()
    payload = {"username": username}
    async with session.post(
        f"{get_base_url()}/admin/get_standing_history",
        json=payload,
        headers=ADMIN_HEADERS,
    ) as resp:
        return resp.status, await resp.json()


async def recover_standing(username: str, reason: str) -> tuple[int, Any]:
    session = await get_session()
    payload = {
        "username": username,
        "reason": reason,
    }
    async with session.post(
        f"{get_base_url()}/admin/recover_standing",
        json=payload,
        headers=ADMIN_HEADERS,
    ) as resp:
        return resp.status, await resp.json()


async def get_user_standing(username: str) -> tuple[int, Any]:
    return await api_json("GET", "/get_standing", params={"username": username})
