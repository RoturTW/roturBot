import json, os, discord
import ofsf, time
from ..helpers import rotur

MISTIUM_ID = "603952506330021898"

async def query(spl, channel, user, dir):
    restrictedKeys = ["username", "max_size", "created", "id", "discord_id", "sys.currency", "sys.subscription"]

    with open(os.path.join(dir, '..', 'systems.json'), 'r') as f:
        systems = json.load(f)
        if not systems:
            await channel.send("No systems found.")
            return

    allowed_ids = {str(system["owner"]["discord_id"]) for system in systems.values() if "owner" in system and "discord_id" in system["owner"]}

    if str(user.id) not in allowed_ids:
        await channel.send("You are not authorized to use this command.")
        return

    if len(spl) < 2:
        await channel.send("Usage: !roturacc <query>")
        return
    user_system = next((sys for name, sys in systems.items() if "owner" in sys and str(sys["owner"].get("discord_id")) == str(user.id)), None)

    if not user_system:
        await channel.send("You do not own any systems.")
        return
    
    isMistium = str(user.id) == MISTIUM_ID
    
    match spl[1]:
        case 'help':
            lines = [
                "!roturacc [name] update [key] [value]",
                "!roturacc [name] remove [key]",
                "!roturacc [name] get",
                "!roturacc [name] size",
                "!roturacc [name] delete",
                "!roturacc [name] refresh_token",
                "Mistium only:",
                "!roturacc [name] token",
                "!roturacc [name] sub <tier>",
                "!roturacc banned_words",
                "!roturacc <word> ban_word",
                "!roturacc <word> unban_word"
            ]
            await channel.send("\n".join(lines))
            return
        case "banned_words":
            if not isMistium:
                await channel.send("Only mistium can view banned words.")
                return
            with open(os.path.join('./banned_words.json'), 'r') as f:
                words = json.load(f)
            await channel.send(f"Banned words: {', '.join(words)}")
    
    
    if len(spl) < 3:
        await channel.send("Usage: !roturacc <username> <command>")
        return
    
    username = spl[1].lower()
    
    match spl[2]:
        case 'size':
            usage_data = ofsf.get_user_file_size(username)
            if usage_data is None:
                await channel.send(f"No file system found for user {username}.")
                return
            await channel.send(f"File system size for {username}: {usage_data}")
        case 'get':
            username = spl[1]
            user_data = rotur.get_user_by("username", username)
            user_data.pop("password", None)
            if not user_data or (not isMistium and user_data.get("system") != user_system["name"]):
                await channel.send(f"User {username} not found in your system.")
                return
            temp_path = os.path.join(dir, "user_data.json")
            with open(temp_path, "w") as temp_file:
                del user_data["key"]
                temp_file.write(json.dumps(user_data, indent=4))
            await channel.send(file=discord.File(temp_path))
            os.remove(temp_path)
        case 'update':
            if len(spl) < 5:
                await channel.send("Usage: !roturacc <username> update <key> <...value>")
                return
            key = spl[3]
            value = " ".join(spl[4:])
            user_data = rotur.get_user_by("username", username)
            if not user_data or (not isMistium and user_data.get("system") != user_system["name"]):
                await channel.send(f"User {username} not found in your system.")
                return
            send_value = value
            if not isMistium and key in restrictedKeys:
                await channel.send(f"You do not have permission to update {key}.")
                return
            if key == "sys.currency":
                try:
                    if isinstance(value, str):
                        if '.' in value:
                            send_value = float(value)
                        else:
                            send_value = float(int(value))
                    else:
                        send_value = float(value)
                except Exception:
                    await channel.send(f"Invalid currency value: {value}")
                    return
            response = rotur.update_user("update", username, key, send_value)
            if response.get("error"):
                await channel.send(f"Error updating user {username}: {response['error']}")
                return
            await channel.send(f"Updated {key} for user {username} to {value}.")
        case 'remove':
            if len(spl) < 4:
                await channel.send("Usage: !roturacc <username> remove <key>")
                return
            key = spl[3]
            user_data = rotur.get_user_by("username", username)
            if not user_data or (not isMistium and user_data.get("system") != user_system["name"]):
                await channel.send(f"User {username} not found in your system.")
                return
            if key in restrictedKeys:
                await channel.send(f"You do not have permission to remove {key}.")
                return
            
            if key not in user_data:
                await channel.send(f"Key {key} not found for user {username}.")
                return
            response = rotur.update_user("remove", username, key)
            if response.get("error"):
                await channel.send(f"Error removing {key} for user {username}: {response['error']}")
                return
            await channel.send(f"Removed {key} for user {username}.")
        case 'delete':
            user_data = rotur.get_user_by("username", username)
            if (not user_data or user_data.get("username", "") == "") or (not isMistium and user_data.get("system") != user_system["name"]):
                await channel.send(f"User {username} not found in your system.")
                return

            resp = rotur.delete_user(user_data.get("username"))
            if "error" in resp:
                await channel.send(resp.get("error"))
            else:
                await channel.send(f"Deleted user {username} from your system.")
        case 'token':
            if not isMistium:
                await channel.send("Only mistium can view tokens")
                return
            user_data = rotur.get_user_by("username", username)
            if not user_data:
                await channel.send(f"User {username} not found.")
                return
            token = user_data.get("key", "No token found.")
            await channel.send(f"Token for {username}: {token}")
        case 'sub':
            if not isMistium:
                await channel.send("Only mistium can add subscriptions")
                return
            username = spl[1]
            sub = spl[3]
            if username == "" or sub == "":
                await channel.send("Usage: !roturacc <username> add_sub <subscription>")
                return
            user_data = rotur.get_user_by("username", username)
            if (not user_data or user_data.get("username", "") == "") or (not isMistium and user_data.get("system") != user_system["name"]):
                await channel.send(f"User {username} not found in your system.")
                return
            resp = rotur.add_subscription(username, sub)
            if "error" in resp:
                await channel.send(resp.get("error"))
            else:
                await channel.send(f"Added subscription {sub} to {username} for 30 days")
        case "ban_word":
            if not isMistium:
                await channel.send("Only mistium can ban words")
                return
            word = spl[1]
            if word == "":
                await channel.send("Usage: !roturacc <word> ban_word")
                return
            with open(os.path.join('./banned_words.json'), 'r') as f:
                words = json.load(f)
            if word in words:
                await channel.send(f"Word {word} is already banned.")
                return
            words.append(word)
            with open(os.path.join('./banned_words.json'), 'w') as f:
                json.dump(words, f)
            await channel.send(f"Banned word {word}.")
        case "unban_word":
            if not isMistium:
                await channel.send("Only mistium can unban words")
                return
            word = spl[1]
            if word == "":
                await channel.send("Usage: !roturacc <word> unban_word")
                return
            with open(os.path.join('./banned_words.json'), 'r') as f:
                words = json.load(f)
            if word not in words:
                await channel.send(f"Word {word} is not banned.")
                return
            words.remove(word)
            with open(os.path.join('./banned_words.json'), 'w') as f:
                json.dump(words, f)
            await channel.send(f"Unbanned word {word}.")