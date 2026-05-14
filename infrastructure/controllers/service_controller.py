from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from application.use_cases.services.create_service_use_case import CreateServiceUseCase
from application.use_cases.services.update_service_use_case import UpdateServiceUseCase
from application.use_cases.services.delete_service_use_case import DeleteServiceUseCase
from application.use_cases.services.get_services_use_case import GetServicesUseCase

service_bp = Blueprint('services', __name__)


def serialize_service(service):
    return {
        'id': service.id,
        'name': service.name,
        'category': service.category,
        'description': service.description,
        'price': float(service.price),
        'duration': service.duration,
        'image_url': service.image_url,
        'is_active': service.is_active,
        'created_at': service.created_at.isoformat() if service.created_at else None
    }


@service_bp.route('/', methods=['GET'])
@jwt_required()
def get_services():
    try:
        query = request.args.get('q')
        category = request.args.get('category')
        use_case = GetServicesUseCase()
        services = use_case.execute(query=query, category=category)
        return jsonify([serialize_service(s) for s in services]), 200
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500


@service_bp.route('/<int:service_id>', methods=['GET'])
@jwt_required()
def get_service(service_id):
    try:
        use_case = GetServicesUseCase()
        service = use_case.execute_by_id(service_id)
        return jsonify(serialize_service(service)), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500


@service_bp.route('/', methods=['POST'])
@jwt_required()
def create_service():
    try:
        data = request.get_json()

        if not data.get('name') or not data.get('price') or not data.get('duration'):
            return jsonify({'error': 'Nombre, precio y duración son requeridos'}), 400

        if data.get('category') not in ['facial', 'corporal', 'capilar', 'sueroterapia', 'masaje relajacion']:
            return jsonify({'error': 'Categoría inválida'}), 400

        use_case = CreateServiceUseCase()
        service = use_case.execute(data)
        return jsonify(serialize_service(service)), 201

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500


@service_bp.route('/<int:service_id>', methods=['PUT'])
@jwt_required()
def update_service(service_id):
    try:
        data = request.get_json()
        use_case = UpdateServiceUseCase()
        service = use_case.execute(service_id, data)
        return jsonify(serialize_service(service)), 200

    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500


@service_bp.route('/<int:service_id>', methods=['DELETE'])
@jwt_required()
def delete_service(service_id):
    try:
        use_case = DeleteServiceUseCase()
        use_case.execute(service_id)
        return jsonify({'message': 'Servicio eliminado exitosamente'}), 200

    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500