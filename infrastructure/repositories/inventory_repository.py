from infrastructure.database.db import db
from infrastructure.database.models import InventoryModel


class InventoryRepository:

    def find_all(self) -> list:
        return InventoryModel.query.filter_by(is_active=True)\
            .order_by(InventoryModel.name).all()

    def find_by_id(self, inventory_id: int) -> InventoryModel | None:
        return InventoryModel.query.filter_by(id=inventory_id, is_active=True).first()

    def find_low_stock(self) -> list:
        return InventoryModel.query.filter(
            InventoryModel.is_active == True,
            InventoryModel.quantity <= InventoryModel.min_stock
        ).all()

    def search(self, query: str) -> list:
        return InventoryModel.query.filter(
            InventoryModel.is_active == True,
            InventoryModel.name.ilike(f'%{query}%') |
            InventoryModel.category.ilike(f'%{query}%') |
            InventoryModel.supplier.ilike(f'%{query}%')
        ).all()

    def save(self, item: InventoryModel) -> InventoryModel:
        db.session.add(item)
        db.session.commit()
        return item

    def update(self, item: InventoryModel) -> InventoryModel:
        db.session.commit()
        return item

    def delete(self, item: InventoryModel) -> None:
        item.is_active = False
        db.session.commit()