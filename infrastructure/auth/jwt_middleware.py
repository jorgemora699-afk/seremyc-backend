from functools import wraps
from flask import jsonify
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from infrastructure.repositories.user_repository import UserRepository


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            verify_jwt_in_request()
            user_id = get_jwt_identity()
            repo = UserRepository()
            user = repo.find_by_id(int(user_id))

            if not user or not user.is_active:
                return jsonify({'error': 'Acceso no autorizado'}), 403

            return fn(*args, **kwargs)
        except Exception as e:
            return jsonify({'error': 'Token inválido o expirado'}), 401
    return wrapper