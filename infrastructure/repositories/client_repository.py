from infrastructure.database.db import db
from infrastructure.database.models import ClientModel


class ClientRepository:

    def find_all(self) -> list:
        return ClientModel.query.filter_by(is_active=True).order_by(ClientModel.full_name).all()

    def find_by_id(self, client_id: int) -> ClientModel | None:
        return ClientModel.query.filter_by(id=client_id, is_active=True).first()

    def search(self, query: str) -> list:
        return ClientModel.query.filter(
            ClientModel.is_active == True,
            ClientModel.full_name.ilike(f'%{query}%') |
            ClientModel.phone.ilike(f'%{query}%') |
            ClientModel.email.ilike(f'%{query}%')
        ).all()

    def save(self, client: ClientModel) -> ClientModel:
        db.session.add(client)
        db.session.commit()
        return client

    def update(self, client: ClientModel) -> ClientModel:
        db.session.commit()
        return client

    def delete(self, client: ClientModel) -> None:
        client.is_active = False
        db.session.commit()