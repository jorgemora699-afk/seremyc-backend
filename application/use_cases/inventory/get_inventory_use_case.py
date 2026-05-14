from infrastructure.repositories.inventory_repository import InventoryRepository


class GetInventoryUseCase:

    def __init__(self):
        self.inventory_repository = InventoryRepository()

    def execute(self, query: str = None, low_stock: bool = False) -> list:
        if low_stock:
            return self.inventory_repository.find_low_stock()
        if query:
            return self.inventory_repository.search(query)
        return self.inventory_repository.find_all()

    def execute_by_id(self, inventory_id: int):
        item = self.inventory_repository.find_by_id(inventory_id)

        if not item:
            raise ValueError('Producto no encontrado')

        return item