from infrastructure.repositories.inventory_repository import InventoryRepository
from infrastructure.database.models import InventoryModel


class CreateInventoryUseCase:

    def __init__(self):
        self.inventory_repository = InventoryRepository()

    def execute(self, data: dict) -> InventoryModel:
        item = InventoryModel(
            name=data.get('name'),
            category=data.get('category'),
            quantity=data.get('quantity'),
            unit=data.get('unit'),
            purchase_price=data.get('purchase_price'),
            sale_price=data.get('sale_price'),
            expiry_date=data.get('expiry_date'),
            supplier=data.get('supplier'),
            min_stock=data.get('min_stock', 0)
        )
        return self.inventory_repository.save(item)