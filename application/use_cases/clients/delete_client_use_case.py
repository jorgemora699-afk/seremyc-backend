from infrastructure.repositories.client_repository import ClientRepository


class DeleteClientUseCase:

    def __init__(self):
        self.client_repository = ClientRepository()

    def execute(self, client_id: int) -> None:
        client = self.client_repository.find_by_id(client_id)

        if not client:
            raise ValueError('Cliente no encontrado')

        self.client_repository.delete(client)