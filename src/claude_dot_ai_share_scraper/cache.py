"""
Cache management for Claude.ai share URL scraper.
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

from .utils import generate_cache_dir_name, hash_content


class CacheManager:
    """Manages caching of Claude share conversations in human-readable hierarchy."""
    
    def __init__(self, cache_dir: str = "cache"):
        """
        Initialize cache manager.
        
        Args:
            cache_dir: Root cache directory path
        """
        self.cache_dir = Path(cache_dir)
        self.conversations_dir = self.cache_dir / "conversations"
        self.index_file = self.cache_dir / "index.json"
        
        # Ensure directories exist
        self.cache_dir.mkdir(exist_ok=True)
        self.conversations_dir.mkdir(exist_ok=True)
        
        # Load or initialize index
        self.index = self._load_index()
    
    def _load_index(self) -> Dict[str, Any]:
        """Load cache index from file."""
        if self.index_file.exists():
            try:
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        
        # Return default index structure
        return {
            "version": "1.0",
            "conversations": {},
            "last_updated": datetime.now().isoformat()
        }
    
    def _save_index(self) -> None:
        """Save cache index to file."""
        self.index["last_updated"] = datetime.now().isoformat()
        try:
            with open(self.index_file, 'w', encoding='utf-8') as f:
                json.dump(self.index, f, indent=2, ensure_ascii=False)
        except IOError as e:
            print(f"Warning: Could not save cache index: {e}")
    
    def conversation_exists(self, share_id: str) -> bool:
        """
        Check if conversation is already cached.
        
        Args:
            share_id: Claude share ID
            
        Returns:
            True if conversation exists in cache
        """
        return share_id in self.index["conversations"]
    
    def get_conversation_path(self, share_id: str) -> Optional[Path]:
        """
        Get path to cached conversation directory.
        
        Args:
            share_id: Claude share ID
            
        Returns:
            Path to conversation directory or None if not cached
        """
        if not self.conversation_exists(share_id):
            return None
            
        entry = self.index["conversations"][share_id]
        return self.conversations_dir / entry["directory"]
    
    def create_conversation_entry(self, share_id: str, title: str, url: str, 
                                 conversation_date: Optional[datetime] = None) -> Path:
        """
        Create new conversation cache entry.
        
        Args:
            share_id: Claude share ID
            title: Conversation title
            url: Original share URL
            conversation_date: Date of conversation (defaults to now)
            
        Returns:
            Path to created conversation directory
        """
        if conversation_date is None:
            conversation_date = datetime.now()
        
        # Generate human-readable directory name
        dir_name = generate_cache_dir_name(title, share_id, conversation_date)
        conv_dir = self.conversations_dir / dir_name
        
        # Create directory
        conv_dir.mkdir(exist_ok=True)
        
        # Add to index
        self.index["conversations"][share_id] = {
            "directory": dir_name,
            "title": title,
            "url": url,
            "date": conversation_date.isoformat(),
            "cached_at": datetime.now().isoformat(),
            "files": {}
        }
        
        self._save_index()
        return conv_dir
    
    def save_raw_html(self, share_id: str, html_content: str) -> Path:
        """
        Save raw HTML content to cache.
        
        Args:
            share_id: Claude share ID
            html_content: Raw HTML content
            
        Returns:
            Path to saved HTML file
        """
        conv_dir = self.get_conversation_path(share_id)
        if not conv_dir:
            raise ValueError(f"Conversation {share_id} not in cache")
        
        html_file = conv_dir / "raw.html"
        
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        # Update index
        self.index["conversations"][share_id]["files"]["raw_html"] = {
            "filename": "raw.html",
            "size": len(html_content),
            "hash": hash_content(html_content),
            "saved_at": datetime.now().isoformat()
        }
        
        self._save_index()
        return html_file
    
    def save_metadata(self, share_id: str, metadata: Dict[str, Any]) -> Path:
        """
        Save conversation metadata to cache.
        
        Args:
            share_id: Claude share ID
            metadata: Metadata dictionary
            
        Returns:
            Path to saved metadata file
        """
        conv_dir = self.get_conversation_path(share_id)
        if not conv_dir:
            raise ValueError(f"Conversation {share_id} not in cache")
        
        metadata_file = conv_dir / "metadata.json"
        
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        # Update index
        metadata_str = json.dumps(metadata)
        self.index["conversations"][share_id]["files"]["metadata"] = {
            "filename": "metadata.json",
            "size": len(metadata_str),
            "hash": hash_content(metadata_str),
            "saved_at": datetime.now().isoformat()
        }
        
        self._save_index()
        return metadata_file
    
    def save_markdown(self, share_id: str, markdown_content: str) -> Path:
        """
        Save markdown conversation to cache.
        
        Args:
            share_id: Claude share ID
            markdown_content: Formatted markdown content
            
        Returns:
            Path to saved markdown file
        """
        conv_dir = self.get_conversation_path(share_id)
        if not conv_dir:
            raise ValueError(f"Conversation {share_id} not in cache")
        
        md_file = conv_dir / "conversation.md"
        
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        
        # Update index
        self.index["conversations"][share_id]["files"]["markdown"] = {
            "filename": "conversation.md",
            "size": len(markdown_content),
            "hash": hash_content(markdown_content),
            "saved_at": datetime.now().isoformat()
        }
        
        self._save_index()
        return md_file
    
    def get_cached_conversations(self) -> List[Dict[str, Any]]:
        """
        Get list of all cached conversations.
        
        Returns:
            List of conversation info dictionaries
        """
        conversations = []
        for share_id, entry in self.index["conversations"].items():
            conversations.append({
                "share_id": share_id,
                "title": entry["title"],
                "url": entry["url"],
                "date": entry["date"],
                "cached_at": entry["cached_at"],
                "directory": entry["directory"],
                "files": list(entry["files"].keys())
            })
        
        return conversations
    
    def cleanup_empty_directories(self) -> int:
        """
        Remove empty conversation directories and orphaned index entries.
        
        Returns:
            Number of directories cleaned up
        """
        cleaned = 0
        to_remove = []
        
        for share_id, entry in self.index["conversations"].items():
            conv_dir = self.conversations_dir / entry["directory"]
            
            # Check if directory exists and has files
            if not conv_dir.exists() or not any(conv_dir.iterdir()):
                to_remove.append(share_id)
                if conv_dir.exists():
                    conv_dir.rmdir()
                cleaned += 1
        
        # Remove from index
        for share_id in to_remove:
            del self.index["conversations"][share_id]
        
        if to_remove:
            self._save_index()
        
        return cleaned
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        total_conversations = len(self.index["conversations"])
        total_size = 0
        file_counts = {"raw_html": 0, "metadata": 0, "markdown": 0}
        
        for entry in self.index["conversations"].values():
            for file_type, file_info in entry["files"].items():
                total_size += file_info.get("size", 0)
                if file_type in file_counts:
                    file_counts[file_type] += 1
        
        return {
            "total_conversations": total_conversations,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "file_counts": file_counts,
            "cache_directory": str(self.cache_dir),
            "last_updated": self.index.get("last_updated")
        }