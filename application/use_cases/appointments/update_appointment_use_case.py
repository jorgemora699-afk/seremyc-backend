from datetime import datetime, timedelta
from infrastructure.repositories.appointment_repository import AppointmentRepository
from infrastructure.database.models import AppointmentModel
from infrastructure.database.db import db

VALID_STATUSES = ['pending', 'confirmed', 'in_progress', 'finished', 'cancelled', 'no_show']


class UpdateAppointmentUseCase:

    def __init__(self):
        self.appointment_repository = AppointmentRepository()

    def execute(self, appointment_id: int, data: dict):
        appointment = self.appointment_repository.find_by_id(appointment_id)

        if not appointment:
            raise ValueError('Cita no encontrada')

        if 'status' in data and data['status'] not in VALID_STATUSES:
            raise ValueError('Estado inválido')

        # Si se cancela la cita — borrar ingreso asociado
        if data.get('status') == 'cancelled' and appointment.status != 'cancelled':
            self._delete_associated_income(appointment_id)
            # Si estaba pagada, marcar como no pagada
            appointment.is_paid = False
            appointment.payment_method = None
            appointment.receipt_url = None

        # Reagendamiento — validar nuevo horario
        if 'scheduled_at' in data and data['scheduled_at'] != appointment.scheduled_at:
            self._validate_availability(
                data['scheduled_at'],
                appointment.duration,
                exclude_id=appointment_id
            )

        # Si se finaliza la cita — registrar pago automáticamente
        if data.get('status') == 'finished' and appointment.status != 'finished':
            self._register_payment(appointment)

        appointment.scheduled_at = data.get('scheduled_at', appointment.scheduled_at)
        appointment.status = data.get('status', appointment.status)
        appointment.observations = data.get('observations', appointment.observations)

        return self.appointment_repository.update(appointment)

    def _delete_associated_income(self, appointment_id: int):
        from infrastructure.database.models import FinanceModel
        from infrastructure.database.db import db
        finance = FinanceModel.query.filter_by(appointment_id=appointment_id).first()
        if finance:
            db.session.delete(finance)
            db.session.commit()

    def _validate_availability(self, scheduled_at: datetime, duration: int, exclude_id: int = None):
        end_time = scheduled_at + timedelta(minutes=duration)

        query = AppointmentModel.query.filter(
            AppointmentModel.status.notin_(['cancelled', 'no_show']),
            AppointmentModel.scheduled_at < end_time,
            db.func.cast(AppointmentModel.scheduled_at, db.DateTime) +
            db.func.cast(
                db.func.concat(AppointmentModel.duration, ' minutes'),
                db.Interval
            ) > scheduled_at
        )

        if exclude_id:
            query = query.filter(AppointmentModel.id != exclude_id)

        existing = query.first()

        if existing:
            raise ValueError(
                f'Ya existe una cita en ese horario. '
                f'Próximo horario disponible: '
                f'{(existing.scheduled_at + timedelta(minutes=existing.duration)).strftime("%H:%M")}'
            )

    def _discount_stock(self, appointment):
        from infrastructure.database.models import InventoryModel
        service = appointment.service
        if not service:
            return

    def _register_payment(self, appointment):
        from infrastructure.database.models import FinanceModel
        from datetime import date

        existing_payment = FinanceModel.query.filter_by(
            appointment_id=appointment.id
        ).first()

        if existing_payment:
            return

        price = float(appointment.final_price) if appointment.final_price else float(appointment.service.price)

        payment = FinanceModel(
            type='income',
            category='servicios',
            amount=price,
            description=f'Pago por {appointment.service.name if appointment.service else "servicio"}',
            date=date.today(),
            appointment_id=appointment.id
        )
        db.session.add(payment)
        db.session.commit()