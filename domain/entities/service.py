from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ServiceEntity:
    id: Optional[int]
    name: str
    category: str  # facial, corporal, capilar, sueroterapia
    description: Optional[str]
    price: float
    duration: int  # en minutos
    image_url: Optional[str]
    is_active: bool = True
    created_at: Optional[datetime] = None