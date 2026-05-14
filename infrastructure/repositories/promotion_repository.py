from datetime import date
from infrastructure.database.db import db
from infrastructure.database.models import PromotionModel


class PromotionRepository:

    def find_all(self) -> list:
        return PromotionModel.query.order_by(PromotionModel.start_date.desc()).all()

    def find_by_id(self, promotion_id: int) -> PromotionModel | None:
        return PromotionModel.query.filter_by(id=promotion_id).first()

    def find_active(self) -> list:
        today = date.today()
        return PromotionModel.query.filter(
            PromotionModel.is_active == True,
            PromotionModel.start_date <= today,
            PromotionModel.end_date >= today
        ).all()

    def find_by_code(self, code: str) -> PromotionModel | None:
        return PromotionModel.query.filter_by(code=code, is_active=True).first()

    def save(self, promotion: PromotionModel) -> PromotionModel:
        db.session.add(promotion)
        db.session.commit()
        return promotion

    def update(self, promotion: PromotionModel) -> PromotionModel:
        db.session.commit()
        return promotion

    def delete(self, promotion: PromotionModel) -> None:
        promotion.is_active = False
        db.session.commit()