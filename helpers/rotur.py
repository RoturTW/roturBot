import os
import requests

def bio_from_obj(obj):
    tier = str(obj.get("subscription", "Free"))

    string = (
        f'{tier}\n'
        f'Credits: {obj.get("currency", "0")}\n'
        f'Account: #{obj.get("index", "unknown")}\n'
    )
    if obj.get("married_to", {}).get("status", "") == "married":
        string += f'💍 Married to {obj["married_to"]}\n'

    string += f'\n{obj.get("bio", "")}\n'
    return string

def get_user_by(key, value):
    response = requests.get(f'https://api.rotur.dev/admin/get_user_by?key={key}', json={"value": value}, headers={'Authorization': os.getenv("ADMIN_TOKEN"), 'Content-Type': 'application/json'})
    return response.json()

def update_user(type, username, key=None, value=None):
    user_data = {"type": type, "username": username, "key": key, "value": value}
    response = requests.post('https://api.rotur.dev/admin/update_user', json=user_data, headers={'Authorization': os.getenv('ADMIN_TOKEN'), 'Content-Type': 'application/json'})
    return response.json()

def add_subscription(username, tier):
    response = requests.post('https://api.rotur.dev/admin/set_sub', json={"username": username, "tier": tier}, headers={'Authorization': os.getenv('ADMIN_TOKEN'), 'Content-Type': 'application/json'})
    return response.json()

def delete_user(username):
    response = requests.post('https://api.rotur.dev/admin/delete_user', json={"username": username}, headers={'Authorization': os.getenv('ADMIN_TOKEN'), 'Content-Type': 'application/json'})
    return response.json()

def transfer_credits(from_username, to_username, amount):
     resp = requests.post("https://api.rotur.dev/admin/transfer_credits?to=" + to_username + "&amount=" + str(amount) + "&from=" + from_username, headers={'Authorization': os.getenv('ADMIN_TOKEN'), 'Content-Type': 'application/json'})
     return resp.json()