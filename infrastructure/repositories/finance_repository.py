from datetime import date
from infrastructure.database.db import db
from infrastructure.database.models import FinanceModel


class FinanceRepository:

    def find_all(self) -> list:
        return FinanceModel.query.order_by(FinanceModel.date.desc()).all()

    def find_by_id(self, finance_id: int) -> FinanceModel | None:
        return FinanceModel.query.filter_by(id=finance_id).first()

    def find_by_date(self, target_date: date) -> list:
        return FinanceModel.query.filter_by(date=target_date)\
            .order_by(FinanceModel.created_at.desc()).all()

    def find_by_month(self, year: int, month: int) -> list:
        return FinanceModel.query.filter(
            db.extract('year', FinanceModel.date) == year,
            db.extract('month', FinanceModel.date) == month
        ).order_by(FinanceModel.date.desc()).all()

    def find_by_type(self, type: str) -> list:
        return FinanceModel.query.filter_by(type=type)\
            .order_by(FinanceModel.date.desc()).all()

    def save(self, finance: FinanceModel) -> FinanceModel:
        db.session.add(finance)
        db.session.commit()
        return finance

    def update(self, finance: FinanceModel) -> FinanceModel:
        db.session.commit()
        return finance

    def delete(self, finance: FinanceModel) -> None:
        db.session.delete(finance)
        db.session.commit()