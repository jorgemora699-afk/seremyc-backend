from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from datetime import datetime
from application.use_cases.clients.create_client_use_case import CreateClientUseCase
from application.use_cases.clients.update_client_use_case import UpdateClientUseCase
from application.use_cases.clients.delete_client_use_case import DeleteClientUseCase
from application.use_cases.clients.get_clients_use_case import GetClientsUseCase

client_bp = Blueprint('clients', __name__)


def serialize_client(client):
    return {
        'id': client.id,
        'full_name': client.full_name,
        'phone': client.phone,
        'whatsapp': client.whatsapp,
        'email': client.email,
        'birth_date': client.birth_date.isoformat() if client.birth_date else None,
        'address': client.address,
        'skin_type': client.skin_type,
        'allergies': client.allergies,
        'observations': client.observations,
        'is_active': client.is_active,
        'created_at': client.created_at.isoformat() if client.created_at else None
    }


@client_bp.route('/', methods=['GET'])
@jwt_required()
def get_clients():
    try:
        query = request.args.get('q')
        use_case = GetClientsUseCase()
        clients = use_case.execute(query=query)
        return jsonify([serialize_client(c) for c in clients]), 200
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500


@client_bp.route('/<int:client_id>', methods=['GET'])
@jwt_required()
def get_client(client_id):
    try:
        use_case = GetClientsUseCase()
        client = use_case.execute_by_id(client_id)
        return jsonify(serialize_client(client)), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500


@client_bp.route('/', methods=['POST'])
@jwt_required()
def create_client():
    try:
        data = request.get_json()

        if not data.get('full_name') or not data.get('phone'):
            return jsonify({'error': 'Nombre y teléfono son requeridos'}), 400

        if data.get('birth_date'):
            try:
                data['birth_date'] = datetime.strptime(
                    data['birth_date'],
                    '%Y-%m-%d'
                ).date()
            except ValueError:
                data['birth_date'] = datetime.strptime(
                    data['birth_date'],
                    '%d/%m/%Y'
                ).date()

        use_case = CreateClientUseCase()
        client = use_case.execute(data)
        return jsonify(serialize_client(client)), 201

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500


@client_bp.route('/<int:client_id>', methods=['PUT'])
@jwt_required()
def update_client(client_id):
    try:
        data = request.get_json()

        if data.get('birth_date'):
            data['birth_date'] = datetime.strptime(data['birth_date'], '%Y-%m-%d').date()

        use_case = UpdateClientUseCase()
        client = use_case.execute(client_id, data)
        return jsonify(serialize_client(client)), 200

    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500


@client_bp.route('/<int:client_id>', methods=['DELETE'])
@jwt_required()
def delete_client(client_id):
    try:
        use_case = DeleteClientUseCase()
        use_case.execute(client_id)
        return jsonify({'message': 'Cliente eliminado exitosamente'}), 200

    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500
    
@client_bp.route('/<int:client_id>/appointments', methods=['GET'])
@jwt_required()
def get_client_appointments(client_id):
    try:
        from infrastructure.repositories.appointment_repository import AppointmentRepository
        repo = AppointmentRepository()
        appointments = repo.find_by_client(client_id)
        return jsonify([
            {
                'id': a.id,
                'service_name': a.service.name if a.service else None,
                'service_price': float(a.service.price) if a.service else None,
                'scheduled_at': a.scheduled_at.isoformat(),
                'duration': a.duration,
                'status': a.status,
                'observations': a.observations
            } for a in appointments
        ]), 200
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500


@client_bp.route('/<int:client_id>/payments', methods=['GET'])
@jwt_required()
def get_client_payments(client_id):
    try:
        from infrastructure.database.db import db
        from infrastructure.database.models import FinanceModel, AppointmentModel
        payments = FinanceModel.query.join(
            AppointmentModel,
            FinanceModel.appointment_id == AppointmentModel.id
        ).filter(
            AppointmentModel.client_id == client_id,
            FinanceModel.type == 'income'
        ).order_by(FinanceModel.date.desc()).all()

        total = sum(float(p.amount) for p in payments)

        return jsonify({
            'total_spent': total,
            'payments': [
                {
                    'id': p.id,
                    'amount': float(p.amount),
                    'description': p.description,
                    'date': p.date.isoformat(),
                    'category': p.category
                } for p in payments
            ]
        }), 200
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500