import bcrypt
from flask_jwt_extended import create_access_token
from infrastructure.repositories.user_repository import UserRepository


class LoginUseCase:

    def __init__(self):
        self.user_repository = UserRepository()

    def execute(self, email: str, password: str) -> dict:
        user = self.user_repository.find_by_email(email)

        if not user:
            raise ValueError('Credenciales inválidas')

        if not user.is_active:
            raise ValueError('Usuario inactivo')

        if not bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8')):
            raise ValueError('Credenciales inválidas')

        token = create_access_token(identity=str(user.id))

        return {
            'token': token,
            'user': {
                'id': user.id,
                'name': user.name,
                'email': user.email
            }
        }