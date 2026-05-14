from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional


@dataclass
class FinanceEntity:
    id: Optional[int]
    type: str  # income, expense
    category: str  # productos, servicios, arriendo, nomina, marketing, otros
    amount: float
    description: Optional[str]
    date: date
    appointment_id: Optional[int]
    created_at: Optional[datetime] = None