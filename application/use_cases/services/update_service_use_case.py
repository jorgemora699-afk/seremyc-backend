from infrastructure.repositories.service_repository import ServiceRepository


class UpdateServiceUseCase:

    def __init__(self):
        self.service_repository = ServiceRepository()

    def execute(self, service_id: int, data: dict):
        service = self.service_repository.find_by_id(service_id)

        if not service:
            raise ValueError('Servicio no encontrado')

        service.name = data.get('name', service.name)
        service.category = data.get('category', service.category)
        service.description = data.get('description', service.description)
        service.price = data.get('price', service.price)
        service.duration = data.get('duration', service.duration)
        service.image_url = data.get('image_url', service.image_url)
        service.is_active = data.get('is_active', service.is_active)

        return self.service_repository.update(service)