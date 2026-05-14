from infrastructure.database.db import db
from infrastructure.database.models import UserModel
from domain.entities.user import UserEntity


class UserRepository:

    def find_by_email(self, email: str) -> UserModel | None:
        return UserModel.query.filter_by(email=email).first()

    def find_by_id(self, user_id: int) -> UserModel | None:
        return UserModel.query.filter_by(id=user_id, is_active=True).first()

    def save(self, user: UserModel) -> UserModel:
        db.session.add(user)
        db.session.commit()
        return user

    def update(self, user: UserModel) -> UserModel:
        db.session.commit()
        return user