from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional


@dataclass
class InventoryEntity:
    id: Optional[int]
    name: str
    category: str
    quantity: float
    unit: str
    purchase_price: float
    sale_price: Optional[float]
    expiry_date: Optional[date]
    supplier: Optional[str]
    min_stock: float
    is_active: bool = True
    created_at: Optional[datetime] = None