import bcrypt
from flask import current_app
from infrastructure.repositories.user_repository import UserRepository
from infrastructure.database.models import UserModel


class RegisterUseCase:

    def __init__(self):
        self.user_repository = UserRepository()

    def execute(self, name: str, email: str, password: str) -> UserModel:
        # Verificar si el correo está autorizado
        allowed_emails = current_app.config.get('ALLOWED_EMAILS', [])
        if allowed_emails and email not in allowed_emails:
            raise ValueError('Este correo no está autorizado para registrarse')

        existing = self.user_repository.find_by_email(email)
        if existing:
            raise ValueError('El correo ya está registrado')

        password_hash = bcrypt.hashpw(
            password.encode('utf-8'),
            bcrypt.gensalt()
        ).decode('utf-8')

        user = UserModel(
            name=name,
            email=email,
            password_hash=password_hash
        )

        return self.user_repository.save(user)