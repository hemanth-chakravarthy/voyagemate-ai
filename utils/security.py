import re
import time
from typing import Tuple

def sanitize_input(text: str) -> str:
    """Basic sanitization: remove potentially dangerous characters and trim."""
    if not text:
        return ""
    # Remove any non-printable characters
    text = "".join(char for char in text if char.isprintable())
    return text.strip()

def check_safety(text: str) -> Tuple[bool, str]:
    """
    Check for potential prompt injections or inappropriate content.
    Returns (is_safe, reason).
    """
    if not text:
        return False, "Empty query"
    
    if len(text) > 800:
        return False, "Query too long (max 800 characters)"

    # Basic prompt injection detection patterns
    injection_patterns = [
        r"ignore (?:all )?previous instructions",
        r"system prompt",
        r"you are now (?!a travel agent)",
        r"disregard (?:all )?instructions",
        r"new rule",
        r"reveal your secrets",
        r"show your prompt"
    ]
    
    for pattern in injection_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return False, "Potential security threat detected"
            
    return True, ""

class RateLimiter:
    """Simple in-memory sliding window rate limiter."""
    def __init__(self, requests_per_minute: int = 10):
        self.limit = requests_per_minute
        self.requests = {} # user_id -> [timestamps]

    def is_allowed(self, user_id: str) -> bool:
        now = time.time()
        user_requests = self.requests.get(user_id, [])
        
        # Filter requests within the last minute
        user_requests = [ts for ts in user_requests if now - ts < 60]
        self.requests[user_id] = user_requests
        
        if len(user_requests) >= self.limit:
            return False
            
        self.requests[user_id].append(now)
        return True
