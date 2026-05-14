from infrastructure.repositories.finance_repository import FinanceRepository
from infrastructure.database.models import FinanceModel


class CreateFinanceUseCase:

    def __init__(self):
        self.finance_repository = FinanceRepository()

    def execute(self, data: dict) -> FinanceModel:
        finance = FinanceModel(
            type=data.get('type'),
            category=data.get('category'),
            amount=data.get('amount'),
            description=data.get('description'),
            date=data.get('date'),
            appointment_id=data.get('appointment_id')
        )
        return self.finance_repository.save(finance)