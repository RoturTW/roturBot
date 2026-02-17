"""
Global Memory System for roturbot
Manages per-server AI memories with fuzzy and semantic search capabilities.
"""

import os
import json
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path

from rapidfuzz import fuzz, process

MODULE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORIES_DIR = os.path.join(MODULE_DIR, "store", "memories")

# Ensure memories directory exists
os.makedirs(MEMORIES_DIR, exist_ok=True)


def _get_memory_file(guild_id: str) -> str:
    """Get the memory file path for a specific guild."""
    return os.path.join(MEMORIES_DIR, f"{guild_id}.json")


def _load_memories(guild_id: str) -> List[Dict[str, Any]]:
    """Load all memories for a guild."""
    file_path = _get_memory_file(guild_id)
    if not os.path.exists(file_path):
        return []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('memories', [])
    except (json.JSONDecodeError, IOError):
        return []


def _save_memories(guild_id: str, memories: List[Dict[str, Any]]) -> None:
    """Save memories for a guild."""
    file_path = _get_memory_file(guild_id)
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump({'memories': memories}, f)
    except IOError as e:
        print(f"[memory_system] Error saving memories for {guild_id}: {e}")


def _calculate_importance_score(memory: Dict[str, Any]) -> float:
    """Calculate dynamic importance score based on various factors."""
    base_importance = memory.get('importance', 5)
    access_count = memory.get('access_count', 0)
    
    # Boost score based on access frequency
    access_boost = min(access_count * 0.5, 3)  # Max +3 from access
    
    # Check if expired
    expires_at = memory.get('expires_at')
    if expires_at:
        expiry = datetime.fromisoformat(expires_at)
        now = datetime.now()
        if expiry < now:
            return 0  # Expired memories have no score
        # Slight boost for memories nearing expiry (urgency)
        days_until_expiry = (expiry - now).days
        if days_until_expiry < 2:
            urgency_boost = 1
        else:
            urgency_boost = 0
    else:
        urgency_boost = 0
    
    return base_importance + access_boost + urgency_boost


def _simple_embedding(text: str) -> List[float]:
    """
    Create a simple embedding for semantic search.
    Uses word frequency as a simple semantic representation.
    """
    # Simple bag-of-words embedding
    words = text.lower().split()
    # Create a simple vector based on word presence
    # This is a very basic approach - in production you'd use sentence-transformers
    embedding = {}
    for word in words:
        # Simple hash to get a consistent dimension
        dim = hash(word) % 100
        embedding[dim] = embedding.get(dim, 0) + 1
    
    # Convert to fixed-size vector
    vector = [embedding.get(i, 0) for i in range(100)]
    
    # Normalize
    magnitude = sum(x**2 for x in vector) ** 0.5
    if magnitude > 0:
        vector = [x / magnitude for x in vector]
    
    return vector


def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = sum(x**2 for x in vec1) ** 0.5
    magnitude2 = sum(x**2 for x in vec2) ** 0.5
    
    if magnitude1 == 0 or magnitude2 == 0:
        return 0
    
    return dot_product / (magnitude1 * magnitude2)


class MemorySystem:
    """Main memory system class."""
    
    @staticmethod
    def save_memory(
        guild_id: str,
        content: str,
        tags: Optional[List[str]] = None,
        importance: int = 5,
        ttl_days: int = 30,
        source_message_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Save a new memory.
        
        Args:
            guild_id: Discord server ID
            content: What to remember
            tags: Categorical tags for filtering
            importance: 1-10 rating of importance
            ttl_days: How many days to keep this memory
            source_message_id: Original Discord message ID
        
        Returns:
            The created memory object
        """
        memories = _load_memories(guild_id)
        
        memory = {
            'id': str(uuid.uuid4()),
            'content': content,
            'tags': tags or [],
            'importance': max(1, min(10, importance)),
            'created_at': datetime.now().isoformat(),
            'expires_at': (datetime.now() + timedelta(days=ttl_days)).isoformat(),
            'access_count': 0,
            'last_accessed': None,
            'embedding': _simple_embedding(content),
            'source_message_id': source_message_id
        }
        
        memories.append(memory)
        _save_memories(guild_id, memories)
        
        return memory
    
    @staticmethod
    def search_memories(
        guild_id: str,
        query: str,
        tags_filter: Optional[List[str]] = None,
        min_importance: int = 1,
        limit: int = 5,
        use_semantic: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant memories.
        
        First tries fuzzy search. If no good results and use_semantic=True,
        falls back to semantic search.
        
        Args:
            guild_id: Discord server ID
            query: Search query
            tags_filter: Optional tags to filter by
            min_importance: Minimum importance score
            limit: Maximum results to return
            use_semantic: Whether to try semantic search if fuzzy fails
        
        Returns:
            List of matching memories sorted by relevance
        """
        memories = _load_memories(guild_id)
        
        # Filter out expired memories
        now = datetime.now()
        active_memories = [
            m for m in memories 
            if datetime.fromisoformat(m['expires_at']) > now
        ]
        
        # Filter by tags if specified
        if tags_filter:
            active_memories = [
                m for m in active_memories
                if any(tag in m['tags'] for tag in tags_filter)
            ]
        
        # Filter by minimum importance
        active_memories = [
            m for m in active_memories
            if m['importance'] >= min_importance
        ]
        
        if not active_memories:
            return []
        
        # Try fuzzy search first
        results = []
        
        # Use rapidfuzz for fast fuzzy matching
        memory_contents = [(m, m['content']) for m in active_memories]
        if not process:
            return []
    
        matches = process.extract(
            query, 
            memory_contents, 
            processor=lambda x: x[1],
            scorer=fuzz.partial_ratio,
            limit=limit * 2
        )
        
        for match, score, _ in matches:
            if score >= 60:  # Minimum fuzzy match threshold
                memory = match[0]
                results.append((memory, score / 100))
        
        # If fuzzy search didn't find enough results, try semantic search
        if len(results) < 3 and use_semantic:
            query_embedding = _simple_embedding(query)
            
            semantic_results = []
            for memory in active_memories:
                memory_embedding = memory.get('embedding', [])
                if memory_embedding:
                    similarity = _cosine_similarity(query_embedding, memory_embedding)
                    if similarity > 0.3:  # Minimum semantic similarity threshold
                        semantic_results.append((memory, similarity))
            
            # Combine results, avoiding duplicates
            existing_ids = {r[0]['id'] for r in results}
            for memory, score in semantic_results:
                if memory['id'] not in existing_ids:
                    results.append((memory, score))
        
        # Sort by score and take top results
        results.sort(key=lambda x: x[1], reverse=True)
        top_results = results[:limit]
        
        # Update access statistics
        memories_to_update = []
        for memory, _ in top_results:
            memory['access_count'] = memory.get('access_count', 0) + 1
            memory['last_accessed'] = datetime.now().isoformat()
            memories_to_update.append(memory)
        
        if memories_to_update:
            # Update the memories in the full list
            memory_dict = {m['id']: m for m in memories}
            for memory in memories_to_update:
                memory_dict[memory['id']] = memory
            _save_memories(guild_id, list(memory_dict.values()))
        
        # Return just the memory objects
        return [r[0] for r in top_results]
    
    @staticmethod
    def update_memory(
        guild_id: str,
        memory_id: str,
        action: str,
        new_ttl_days: Optional[int] = None,
        importance_boost: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Update an existing memory.
        
        Args:
            guild_id: Discord server ID
            memory_id: Memory UUID
            action: 'extend', 'delete', or 'increase_importance'
            new_ttl_days: For 'extend', new expiration from now
            importance_boost: For 'increase_importance', amount to add
        
        Returns:
            Updated memory or None if not found
        """
        memories = _load_memories(guild_id)
        
        memory = None
        for m in memories:
            if m['id'] == memory_id:
                memory = m
                break
        
        if not memory:
            return None
        
        if action == 'delete':
            memories = [m for m in memories if m['id'] != memory_id]
            _save_memories(guild_id, memories)
            return None
        
        elif action == 'extend':
            if new_ttl_days:
                memory['expires_at'] = (datetime.now() + timedelta(days=new_ttl_days)).isoformat()
        
        elif action == 'increase_importance':
            if importance_boost:
                memory['importance'] = min(10, memory.get('importance', 5) + importance_boost)
        
        _save_memories(guild_id, memories)
        return memory
    
    @staticmethod
    def cleanup_expired(guild_id: Optional[str] = None) -> int:
        """
        Remove expired memories.
        
        Args:
            guild_id: If specified, only clean that guild. Otherwise clean all.
        
        Returns:
            Number of memories deleted
        """
        now = datetime.now()
        deleted_count = 0
        
        if guild_id:
            guild_ids = [guild_id]
        else:
            # Get all guild memory files
            if os.path.exists(MEMORIES_DIR):
                guild_ids = [
                    f.replace('.json', '') 
                    for f in os.listdir(MEMORIES_DIR) 
                    if f.endswith('.json')
                ]
            else:
                guild_ids = []
        
        for gid in guild_ids:
            memories = _load_memories(gid)
            original_count = len(memories)
            
            # Keep only non-expired memories
            active_memories = [
                m for m in memories 
                if datetime.fromisoformat(m['expires_at']) > now
            ]
            
            deleted = original_count - len(active_memories)
            if deleted > 0:
                _save_memories(gid, active_memories)
                deleted_count += deleted
        
        return deleted_count
    
    @staticmethod
    def get_stats(guild_id: str) -> Dict[str, Any]:
        """Get memory statistics for a guild."""
        memories = _load_memories(guild_id)
        now = datetime.now()
        
        total = len(memories)
        expired = sum(1 for m in memories if datetime.fromisoformat(m['expires_at']) <= now)
        active = total - expired
        
        # Calculate average importance
        avg_importance = sum(m['importance'] for m in memories) / total if total > 0 else 0
        
        # Count by tags
        tag_counts = {}
        for m in memories:
            for tag in m.get('tags', []):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        
        return {
            'total_memories': total,
            'active_memories': active,
            'expired_memories': expired,
            'average_importance': round(avg_importance, 2),
            'top_tags': sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        }


# Global instance for easy access
memory_system = MemorySystem()
