from infrastructure.repositories.client_repository import ClientRepository


class UpdateClientUseCase:

    def __init__(self):
        self.client_repository = ClientRepository()

    def execute(self, client_id: int, data: dict):
        client = self.client_repository.find_by_id(client_id)

        if not client:
            raise ValueError('Cliente no encontrado')

        client.full_name = data.get('full_name', client.full_name)
        client.phone = data.get('phone', client.phone)
        client.whatsapp = data.get('whatsapp', client.whatsapp)
        client.email = data.get('email', client.email)
        client.birth_date = data.get('birth_date', client.birth_date)
        client.address = data.get('address', client.address)
        client.skin_type = data.get('skin_type', client.skin_type)
        client.allergies = data.get('allergies', client.allergies)
        client.observations = data.get('observations', client.observations)

        return self.client_repository.update(client)