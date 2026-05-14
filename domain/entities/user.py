from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class UserEntity:
    id: Optional[int]
    name: str
    email: str
    password_hash: str
    is_active: bool = True
    created_at: Optional[datetime] = None