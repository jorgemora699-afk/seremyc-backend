from datetime import datetime, timedelta
from infrastructure.repositories.appointment_repository import AppointmentRepository
from infrastructure.repositories.service_repository import ServiceRepository
from infrastructure.repositories.client_repository import ClientRepository
from infrastructure.repositories.promotion_repository import PromotionRepository
from infrastructure.database.models import AppointmentModel
from infrastructure.database.db import db


class CreateAppointmentUseCase:

    def __init__(self):
        self.appointment_repository = AppointmentRepository()
        self.service_repository = ServiceRepository()
        self.client_repository = ClientRepository()
        self.promotion_repository = PromotionRepository()

    def execute(self, data: dict) -> AppointmentModel:
        # Validar cliente
        client = self.client_repository.find_by_id(data.get('client_id'))
        if not client:
            raise ValueError('Cliente no encontrado')

        # Validar servicio
        service = self.service_repository.find_by_id(data.get('service_id'))
        if not service:
            raise ValueError('Servicio no encontrado')

        scheduled_at = data.get('scheduled_at')
        duration = service.duration

        # Validar disponibilidad de horario
        self._validate_availability(scheduled_at, duration)

        # Calcular precio con promoción
        final_price, discount_applied, promotion_id = self._apply_promotion(
            service.price,
            data.get('promotion_code')
        )

        appointment = AppointmentModel(
            client_id=data.get('client_id'),
            service_id=data.get('service_id'),
            scheduled_at=scheduled_at,
            duration=duration,
            status='pending',
            observations=data.get('observations'),
            promotion_id=promotion_id,
            discount_applied=discount_applied,
            final_price=final_price
        )

        return self.appointment_repository.save(appointment)

    def _validate_availability(self, scheduled_at: datetime, duration: int):
        end_time = scheduled_at + timedelta(minutes=duration)

        existing = AppointmentModel.query.filter(
            AppointmentModel.status.notin_(['cancelled', 'no_show']),
            AppointmentModel.scheduled_at < end_time,
            db.func.cast(AppointmentModel.scheduled_at, db.DateTime) +
            db.func.cast(
                db.func.concat(AppointmentModel.duration, ' minutes'),
                db.Interval
            ) > scheduled_at
        ).first()

        if existing:
            raise ValueError(
                f'Ya existe una cita en ese horario. '
                f'Próximo horario disponible: '
                f'{(existing.scheduled_at + timedelta(minutes=existing.duration)).strftime("%H:%M")}'
            )

    def _apply_promotion(self, price, promotion_code: str = None):
        if not promotion_code:
            return float(price), 0, None

        promotion = self.promotion_repository.find_by_code(promotion_code)

        if not promotion:
            raise ValueError('Código de promoción inválido')

        if not promotion.is_active:
            raise ValueError('La promoción no está activa')

        from datetime import date
        today = date.today()
        if today < promotion.start_date or today > promotion.end_date:
            raise ValueError('La promoción está vencida')

        if promotion.max_uses and promotion.current_uses >= promotion.max_uses:
            raise ValueError('El cupón ha alcanzado su límite de usos')

        # Calcular descuento
        price = float(price)
        if promotion.discount_type == 'percentage':
            discount = price * (float(promotion.discount_value) / 100)
        else:
            discount = float(promotion.discount_value)

        final_price = max(0, price - discount)

        # Incrementar uso del cupón
        promotion.current_uses += 1
        from infrastructure.database.db import db
        db.session.commit()

        return final_price, discount, promotion.id