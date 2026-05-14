from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class AppointmentEntity:
    id: Optional[int]
    client_id: int
    service_id: int
    scheduled_at: datetime
    duration: int  # en minutos
    status: str  # pending, confirmed, in_progress, finished, cancelled, no_show
    observations: Optional[str]
    created_at: Optional[datetime] = None