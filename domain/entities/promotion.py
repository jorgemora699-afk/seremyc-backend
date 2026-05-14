from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional


@dataclass
class PromotionEntity:
    id: Optional[int]
    name: str
    description: Optional[str]
    discount_type: str  # percentage, fixed
    discount_value: float
    code: Optional[str]
    start_date: date
    end_date: date
    is_active: bool = True
    created_at: Optional[datetime] = None