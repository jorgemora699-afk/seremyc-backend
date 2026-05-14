from infrastructure.repositories.service_repository import ServiceRepository
from infrastructure.database.models import ServiceModel


class CreateServiceUseCase:

    def __init__(self):
        self.service_repository = ServiceRepository()

    def execute(self, data: dict) -> ServiceModel:
        service = ServiceModel(
            name=data.get('name'),
            category=data.get('category'),
            description=data.get('description'),
            price=data.get('price'),
            duration=data.get('duration'),
            image_url=data.get('image_url'),
        )
        return self.service_repository.save(service)