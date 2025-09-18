import os
import requests

def bio_from_obj(obj):
    tier = str(obj.get("subscription", "Free"))

    string = (
        f'{tier}\n'
        f'Credits: {obj.get("currency", "0")}\n'
        f'Account: #{obj.get("index", "unknown")}\n\n'
        f'{obj.get("bio", "")}\n'
    )
    if obj.get("married_to"):
        string += f'💍 Married to {obj["married_to"]}\n'
    
    return string

def get_user_by(key, value):
    response = requests.get(f'https://social.rotur.dev/admin/get_user_by?key={key}', json={"value": value}, headers={'Authorization': os.getenv("ADMIN_TOKEN")})
    return response.json()

def update_user(type, username, key=None, value=None):
    user_data = {"type": type, "username": username, "key": key, "value": value}
    response = requests.post('https://social.rotur.dev/admin/update_user', json=user_data, headers={'Authorization': os.getenv('ADMIN_TOKEN')})
    return response.json()

def delete_user(username):
    response = requests.post('https://social.rotur.dev/admin/delete_user', json={"username": username}, headers={'Authorization': os.getenv('ADMIN_TOKEN')})
    return response.json()