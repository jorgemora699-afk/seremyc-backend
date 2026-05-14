from infrastructure.repositories.client_repository import ClientRepository


class GetClientsUseCase:

    def __init__(self):
        self.client_repository = ClientRepository()

    def execute(self, query: str = None) -> list:
        if query:
            return self.client_repository.search(query)
        return self.client_repository.find_all()

    def execute_by_id(self, client_id: int):
        client = self.client_repository.find_by_id(client_id)

        if not client:
            raise ValueError('Cliente no encontrado')

        return client