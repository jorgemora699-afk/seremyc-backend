from infrastructure.repositories.promotion_repository import PromotionRepository


class GetPromotionsUseCase:

    def __init__(self):
        self.promotion_repository = PromotionRepository()

    def execute(self, active_only: bool = False) -> list:
        if active_only:
            return self.promotion_repository.find_active()
        return self.promotion_repository.find_all()

    def execute_by_id(self, promotion_id: int):
        promotion = self.promotion_repository.find_by_id(promotion_id)

        if not promotion:
            raise ValueError('Promoción no encontrada')

        return promotion