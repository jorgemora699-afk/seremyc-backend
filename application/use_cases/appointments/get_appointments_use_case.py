from datetime import datetime, date
from infrastructure.repositories.appointment_repository import AppointmentRepository


class GetAppointmentsUseCase:

    def __init__(self):
        self.appointment_repository = AppointmentRepository()

    def execute(self, target_date: date = None, client_id: int = None, status: str = None) -> list:
        if target_date:
            return self.appointment_repository.find_by_date(target_date)
        if client_id:
            return self.appointment_repository.find_by_client(client_id)
        if status:
            return self.appointment_repository.find_by_status(status)
        return self.appointment_repository.find_all()

    def execute_by_id(self, appointment_id: int):
        appointment = self.appointment_repository.find_by_id(appointment_id)

        if not appointment:
            raise ValueError('Cita no encontrada')

        return appointment

    def execute_by_range(self, start: datetime, end: datetime) -> list:
        return self.appointment_repository.find_by_date_range(start, end)