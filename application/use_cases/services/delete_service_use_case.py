from infrastructure.repositories.service_repository import ServiceRepository


class DeleteServiceUseCase:

    def __init__(self):
        self.service_repository = ServiceRepository()

    def execute(self, service_id: int) -> None:
        service = self.service_repository.find_by_id(service_id)

        if not service:
            raise ValueError('Servicio no encontrado')

        self.service_repository.delete(service)