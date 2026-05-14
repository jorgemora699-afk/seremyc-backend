from infrastructure.repositories.service_repository import ServiceRepository


class GetServicesUseCase:

    def __init__(self):
        self.service_repository = ServiceRepository()

    def execute(self, query: str = None, category: str = None) -> list:
        if query:
            return self.service_repository.search(query)
        if category:
            return self.service_repository.find_by_category(category)
        return self.service_repository.find_all()

    def execute_by_id(self, service_id: int):
        service = self.service_repository.find_by_id(service_id)

        if not service:
            raise ValueError('Servicio no encontrado')

        return service