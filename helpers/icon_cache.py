import json
import os
import hashlib
from io import BytesIO
from typing import Optional, Dict, Any, Union
import discord
from . import icn

class IconCache:
    def __init__(self, cache_file_path: str, client: discord.Client):
        self.cache_file = cache_file_path
        self.client = client
        self.cache: Dict[str, Union[str, Dict[str, Any]]] = self._load_cache()
        self._dirty = False
    
    def _load_cache(self) -> Dict[str, Union[str, Dict[str, Any]]]:
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading icon cache: {e}")
        return {}
    
    def _save_cache(self):
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            print(f"Error saving icon cache: {e}")
    
    def _hash_icon(self, icon_code: str) -> str:
        return hashlib.md5(icon_code.encode()).hexdigest()[:12]
    
    async def _render_icon(self, icon_code: str, size: int = 128) -> BytesIO:
        high_res = size * 4
        img = icn.draw(icon_code, width=high_res, height=high_res, scale=high_res / 20)
        
        from PIL import Image
        img = img.resize((size, size), Image.Resampling.LANCZOS)
        
        buffer = BytesIO()
        img.save(buffer, format="PNG", optimize=False)
        buffer.seek(0)
        return buffer
    
    async def get_emoji(self, icon_code: str, emoji_name: Optional[str] = None) -> Optional[str]:
        icon_hash = self._hash_icon(icon_code)
        
        if icon_hash in self.cache:
            cache_entry = self.cache[icon_hash]
            emoji_id = cache_entry if isinstance(cache_entry, str) else cache_entry.get('id')
            if emoji_id:
                self.cache[icon_hash] = {
                    'id': str(emoji_id),
                    'last_used': int(__import__('time').time())
                }
                self._dirty = True
                return f"<:i_{icon_hash}:{emoji_id}>"
        
        try:
            emoji_name = f"i_{icon_hash}"
            
            image_buffer = await self._render_icon(icon_code)
            
            emoji = await self.client.create_application_emoji(
                name=emoji_name,
                image=image_buffer.read()
            )
            
            self.cache[icon_hash] = {
                'id': str(emoji.id),
                'last_used': int(__import__('time').time())
            }
            self._save_cache()
            
            print(f"Created new application emoji: {emoji.name} ({emoji.id}) for icon hash {icon_hash}")
            return str(emoji)
            
        except discord.HTTPException as e:
            print(f"Failed to create application emoji for icon {icon_hash}: {e}")
            return None
        except Exception as e:
            print(f"Error creating application emoji: {e}")
            return None
    
    async def get_badge_emojis(self, badges: list) -> list:
        import asyncio
        
        async def fetch_emoji(badge):
            icon_code = badge.get('icon', '')
            badge_name = badge.get('name', 'badge')
            if icon_code:
                return await self.get_emoji(icon_code, badge_name)
            return None
        
        emoji_results = await asyncio.gather(*[fetch_emoji(badge) for badge in badges], return_exceptions=True)
        emojis = [emoji for emoji in emoji_results if emoji and not isinstance(emoji, Exception)]
        
        if self._dirty:
            self._save_cache()
            self._dirty = False
        return emojis
    
    async def cleanup_old_emojis(self):
        import time
        removed_count = 0
        current_time = int(time.time())
        one_month = 30 * 24 * 60 * 60
        
        for icon_hash, cache_entry in list(self.cache.items()):
            if isinstance(cache_entry, dict):
                last_used = cache_entry.get('last_used', 0)
                emoji_id = cache_entry.get('id')
            else:
                last_used = 0
                emoji_id = cache_entry
            
            if current_time - last_used > one_month:
                try:
                    if emoji_id:
                        emoji = await self.client.fetch_application_emoji(int(emoji_id))
                        if emoji:
                            await emoji.delete()
                            removed_count += 1
                    del self.cache[icon_hash]
                except discord.NotFound:
                    del self.cache[icon_hash]
                except Exception as e:
                    print(f"Error removing application emoji {emoji_id}: {e}")
        
        if removed_count > 0:
            self._save_cache()
            print(f"Cleaned up {removed_count} unused application emoji(s)")
        
        return removed_count
