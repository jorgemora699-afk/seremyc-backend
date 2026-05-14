from flask import Blueprint, request, jsonify
from application.use_cases.auth.login_use_case import LoginUseCase
from application.use_cases.auth.register_use_case import RegisterUseCase

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()

        if not data.get('email') or not data.get('password'):
            return jsonify({'error': 'Email y contraseña son requeridos'}), 400

        use_case = LoginUseCase()
        result = use_case.execute(data['email'], data['password'])

        return jsonify(result), 200

    except ValueError as e:
        return jsonify({'error': str(e)}), 401
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500


@auth_bp.route('/register', methods=['POST'])
def register():
    try:
        data = request.get_json()

        if not data.get('name') or not data.get('email') or not data.get('password'):
            return jsonify({'error': 'Nombre, email y contraseña son requeridos'}), 400

        use_case = RegisterUseCase()
        user = use_case.execute(data['name'], data['email'], data['password'])

        return jsonify({
            'message': 'Usuario creado exitosamente',
            'user': {
                'id': user.id,
                'name': user.name,
                'email': user.email
            }
        }), 201

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500