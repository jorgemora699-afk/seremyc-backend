from infrastructure.repositories.client_repository import ClientRepository
from infrastructure.database.models import ClientModel


class CreateClientUseCase:

    def __init__(self):
        self.client_repository = ClientRepository()

    def execute(self, data: dict) -> ClientModel:
        client = ClientModel(
            full_name=data.get('full_name'),
            phone=data.get('phone'),
            whatsapp=data.get('whatsapp'),
            email=data.get('email'),
            birth_date=data.get('birth_date'),
            address=data.get('address'),
            skin_type=data.get('skin_type'),
            allergies=data.get('allergies'),
            observations=data.get('observations')
        )
        return self.client_repository.save(client)