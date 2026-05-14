from infrastructure.repositories.promotion_repository import PromotionRepository
from infrastructure.database.models import PromotionModel


class CreatePromotionUseCase:

    def __init__(self):
        self.promotion_repository = PromotionRepository()

    def execute(self, data: dict) -> PromotionModel:
        if data.get('code'):
            existing = self.promotion_repository.find_by_code(data.get('code'))
            if existing:
                raise ValueError('El código de promoción ya existe')

        promotion = PromotionModel(
            name=data.get('name'),
            description=data.get('description'),
            discount_type=data.get('discount_type'),
            discount_value=data.get('discount_value'),
            code=data.get('code'),
            start_date=data.get('start_date'),
            end_date=data.get('end_date')
        )
        return self.promotion_repository.save(promotion)