from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional


@dataclass
class ClientEntity:
    id: Optional[int]
    full_name: str
    phone: str
    whatsapp: Optional[str]
    email: Optional[str]
    birth_date: Optional[date]
    address: Optional[str]
    skin_type: Optional[str]
    allergies: Optional[str]
    observations: Optional[str]
    is_active: bool = True
    created_at: Optional[datetime] = None