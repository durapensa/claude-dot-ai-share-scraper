"""
Utility functions for Claude.ai share URL scraper.
"""

import re
import hashlib
from urllib.parse import urlparse
from datetime import datetime
from typing import Optional


def extract_share_id(url: str) -> Optional[str]:
    """
    Extract the share ID from a Claude.ai share URL.
    
    Args:
        url: Claude.ai share URL like https://claude.ai/share/75a3648c-8bfa-4730-b3c9-57c8a964051b
        
    Returns:
        Share ID string or None if URL is invalid
    """
    pattern = r'claude\.ai/share/([a-f0-9-]+)'
    match = re.search(pattern, url)
    return match.group(1) if match else None


def is_valid_claude_share_url(url: str) -> bool:
    """
    Validate if a URL is a Claude.ai share URL.
    
    Args:
        url: URL to validate
        
    Returns:
        True if valid Claude.ai share URL, False otherwise
    """
    try:
        parsed = urlparse(url)
        return (
            parsed.netloc == 'claude.ai' and 
            parsed.path.startswith('/share/') and
            extract_share_id(url) is not None
        )
    except Exception:
        return False


def sanitize_filename(text: str, max_length: int = 50) -> str:
    """
    Sanitize text for use as filename/directory name.
    
    Args:
        text: Text to sanitize
        max_length: Maximum length for the result
        
    Returns:
        Sanitized filename-safe string
    """
    # Remove or replace invalid filename characters
    text = re.sub(r'[<>:"/\\|?*]', '', text)
    # Replace spaces and multiple whitespace with hyphens
    text = re.sub(r'\s+', '-', text.strip())
    # Remove non-alphanumeric except hyphens and underscores
    text = re.sub(r'[^a-zA-Z0-9\-_]', '', text)
    # Remove multiple consecutive hyphens
    text = re.sub(r'-+', '-', text)
    # Trim hyphens from start/end
    text = text.strip('-')
    
    # Truncate to max length
    if len(text) > max_length:
        text = text[:max_length].rstrip('-')
    
    return text or 'untitled'


def generate_cache_dir_name(title: str, share_id: str, date: Optional[datetime] = None) -> str:
    """
    Generate a human-readable cache directory name.
    
    Format: YYYY-MM-DD_sanitized-title_short-id
    
    Args:
        title: Conversation title
        share_id: Claude share ID
        date: Conversation date (defaults to current date)
        
    Returns:
        Directory name string
    """
    if date is None:
        date = datetime.now()
    
    date_str = date.strftime('%Y-%m-%d')
    sanitized_title = sanitize_filename(title, max_length=30)
    short_id = share_id[:8] if share_id else 'unknown'
    
    return f"{date_str}_{sanitized_title}_{short_id}"


def hash_content(content: str) -> str:
    """
    Generate SHA-256 hash of content for duplicate detection.
    
    Args:
        content: Content to hash
        
    Returns:
        Hex digest of SHA-256 hash
    """
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def get_user_agent() -> str:
    """
    Get a current user agent string for web requests.
    
    Returns:
        User agent string
    """
    return (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate text to specified length with optional suffix.
    
    Args:
        text: Text to truncate
        max_length: Maximum length including suffix
        suffix: Suffix to append when truncating
        
    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text
    
    truncate_length = max_length - len(suffix)
    return text[:truncate_length] + suffix


def parse_iso_date(date_str: str) -> Optional[datetime]:
    """
    Parse ISO format date string to datetime object.
    
    Args:
        date_str: ISO format date string
        
    Returns:
        datetime object or None if parsing fails
    """
    try:
        # Handle various ISO formats
        formats = [
            '%Y-%m-%dT%H:%M:%S.%fZ',
            '%Y-%m-%dT%H:%M:%SZ', 
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d'
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
                
        return None
    except Exception:
        return None