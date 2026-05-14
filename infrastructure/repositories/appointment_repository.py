from datetime import date, datetime
from infrastructure.database.db import db
from infrastructure.database.models import AppointmentModel


class AppointmentRepository:

    def find_all(self) -> list:
        return AppointmentModel.query.order_by(AppointmentModel.scheduled_at.desc()).all()

    def find_by_id(self, appointment_id: int) -> AppointmentModel | None:
        return AppointmentModel.query.filter_by(id=appointment_id).first()

    def find_by_date(self, target_date: date) -> list:
        return AppointmentModel.query.filter(
            db.func.date(AppointmentModel.scheduled_at) == target_date
        ).order_by(AppointmentModel.scheduled_at).all()

    def find_by_client(self, client_id: int) -> list:
        return AppointmentModel.query.filter_by(client_id=client_id)\
            .order_by(AppointmentModel.scheduled_at.desc()).all()

    def find_by_status(self, status: str) -> list:
        return AppointmentModel.query.filter_by(status=status)\
            .order_by(AppointmentModel.scheduled_at).all()

    def find_by_date_range(self, start: datetime, end: datetime) -> list:
        return AppointmentModel.query.filter(
            AppointmentModel.scheduled_at >= start,
            AppointmentModel.scheduled_at <= end
        ).order_by(AppointmentModel.scheduled_at).all()

    def save(self, appointment: AppointmentModel) -> AppointmentModel:
        db.session.add(appointment)
        db.session.commit()
        return appointment

    def update(self, appointment: AppointmentModel) -> AppointmentModel:
        db.session.commit()
        return appointment

    def delete(self, appointment: AppointmentModel) -> None:
        db.session.delete(appointment)
        db.session.commit()