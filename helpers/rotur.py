import os
import requests
import urllib.parse

server = os.getenv("CENTRAL_SERVER", "https://api.rotur.dev")

def bio_from_obj(obj):
    tier = str(obj.get("subscription", "Free"))

    string = (
        f'{tier}\n'
        f'Credits: {obj.get("currency", "0")}\n'
        f'Account: #{obj.get("index", "unknown")}\n'
    )
    if obj.get("married_to", {}):
        string += f'💍 Married to {obj["married_to"]}\n'

    string += f'\n{obj.get("bio", "")}\n'
    return string

def get_user_by(key, value):
    response = requests.get(f'{server}/admin/get_user_by?key={key}', json={"value": value}, headers={'Authorization': os.getenv("ADMIN_TOKEN"), 'Content-Type': 'application/json'})
    return response.json()

def update_user(type, username, key=None, value=None):
    user_data = {"type": type, "username": username, "key": key, "value": value}
    response = requests.post(f'{server}/admin/update_user', json=user_data, headers={'Authorization': os.getenv('ADMIN_TOKEN'), 'Content-Type': 'application/json'})
    return response.json()

def delete_user_key(username, key):
    return update_user("remove", username, key)

def set_user_key(username, key, value):
    return update_user("update", username, key, value)

def add_subscription(username, tier):
    response = requests.post(f'{server}/admin/set_sub', json={"username": username, "tier": tier}, headers={'Authorization': os.getenv('ADMIN_TOKEN'), 'Content-Type': 'application/json'})
    return response.json()

def delete_user(username):
    response = requests.post(f'{server}/admin/delete_user', json={"username": username}, headers={'Authorization': os.getenv('ADMIN_TOKEN'), 'Content-Type': 'application/json'})
    return response.json()

def transfer_credits(from_username, to_username, amount, note=""):
     query = {
         "to": to_username,
         "amount": str(amount),
         "from": from_username,
         "note": note
     }
     resp = requests.post(f"{server}/admin/transfer_credits?" + urllib.parse.urlencode(query), headers={'Authorization': os.getenv('ADMIN_TOKEN'), 'Content-Type': 'application/json'})
     return resp.json()

def block_user(token, username):
    response = requests.post(f'{server}/me/block/{username}?auth={token}')
    if response.status_code == 200:
        return "You are now blocking " + username + "."
    else:
        return response.json().get('error', 'Unknown error occurred.')

def unblock_user(token, username):
    response = requests.post(f'{server}/me/unblock/{username}?auth={token}')
    if response.status_code == 200:
        return "You are no longer blocking " + username + "."
    else:
        return response.json().get('error', 'Unknown error occurred.')
    
def get_users(system, token):
    response = requests.get(f'{server}/system/users?auth={token}&system={system}')
    return response.json()

def get_user(token):
    response = requests.get(f'{server}/me?auth={token}')
    return response.json()