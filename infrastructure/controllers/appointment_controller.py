from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from datetime import datetime
from application.use_cases.appointments.create_appointment_use_case import CreateAppointmentUseCase
from application.use_cases.appointments.update_appointment_use_case import UpdateAppointmentUseCase
from application.use_cases.appointments.get_appointments_use_case import GetAppointmentsUseCase

appointment_bp = Blueprint('appointments', __name__)


def serialize_appointment(appointment):
    return {
        'id': appointment.id,
        'client_id': appointment.client_id,
        'client_name': appointment.client.full_name if appointment.client else None,
        'service_id': appointment.service_id,
        'service_name': appointment.service.name if appointment.service else None,
        'service_price': float(appointment.service.price) if appointment.service else None,
        'scheduled_at': appointment.scheduled_at.isoformat() if appointment.scheduled_at else None,
        'duration': appointment.duration,
        'status': appointment.status,
        'observations': appointment.observations,
        'created_at': appointment.created_at.isoformat() if appointment.created_at else None
    }


@appointment_bp.route('/', methods=['GET'])
@jwt_required()
def get_appointments():
    try:
        date_str = request.args.get('date')
        client_id = request.args.get('client_id')
        status = request.args.get('status')

        target_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else None
        use_case = GetAppointmentsUseCase()
        appointments = use_case.execute(
            target_date=target_date,
            client_id=int(client_id) if client_id else None,
            status=status
        )
        return jsonify([serialize_appointment(a) for a in appointments]), 200
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500


@appointment_bp.route('/<int:appointment_id>', methods=['GET'])
@jwt_required()
def get_appointment(appointment_id):
    try:
        use_case = GetAppointmentsUseCase()
        appointment = use_case.execute_by_id(appointment_id)
        return jsonify(serialize_appointment(appointment)), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500


@appointment_bp.route('/', methods=['POST'])
@jwt_required()
def create_appointment():
    try:
        data = request.get_json()

        if not data.get('client_id') or not data.get('service_id') or not data.get('scheduled_at'):
            return jsonify({'error': 'Cliente, servicio y fecha son requeridos'}), 400

        data['scheduled_at'] = datetime.fromisoformat(data['scheduled_at'])

        use_case = CreateAppointmentUseCase()
        appointment = use_case.execute(data)
        return jsonify(serialize_appointment(appointment)), 201

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500


@appointment_bp.route('/<int:appointment_id>', methods=['PUT'])
@jwt_required()
def update_appointment(appointment_id):
    try:
        data = request.get_json()

        if data.get('scheduled_at'):
            data['scheduled_at'] = datetime.fromisoformat(data['scheduled_at'])

        use_case = UpdateAppointmentUseCase()
        appointment = use_case.execute(appointment_id, data)
        return jsonify(serialize_appointment(appointment)), 200

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500


@appointment_bp.route('/<int:appointment_id>', methods=['DELETE'])
@jwt_required()
def delete_appointment(appointment_id):
    try:
        from app.infrastructure.repositories.appointment_repository import AppointmentRepository
        repo = AppointmentRepository()
        appointment = repo.find_by_id(appointment_id)

        if not appointment:
            return jsonify({'error': 'Cita no encontrada'}), 404

        repo.delete(appointment)
        return jsonify({'message': 'Cita eliminada exitosamente'}), 200

    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500
    
@appointment_bp.route('/availability', methods=['GET'])
@jwt_required()
def check_availability():
    try:
        date_str = request.args.get('date')
        service_id = request.args.get('service_id')

        if not date_str or not service_id:
            return jsonify({'error': 'Fecha y servicio son requeridos'}), 400

        from infrastructure.repositories.service_repository import ServiceRepository
        from infrastructure.database.models import AppointmentModel
        from datetime import datetime, timedelta

        service = ServiceRepository().find_by_id(int(service_id))
        if not service:
            return jsonify({'error': 'Servicio no encontrado'}), 404

        target_date = datetime.strptime(date_str, '%Y-%m-%d')

        # Citas del día
        existing = AppointmentModel.query.filter(
            db.func.date(AppointmentModel.scheduled_at) == target_date.date(),
            AppointmentModel.status.notin_(['cancelled', 'no_show'])
        ).order_by(AppointmentModel.scheduled_at).all()

        # Generar slots disponibles 8am - 7pm cada 30 min
        slots = []
        current = target_date.replace(hour=8, minute=0, second=0)
        end_of_day = target_date.replace(hour=19, minute=0, second=0)

        while current + timedelta(minutes=service.duration) <= end_of_day:
            slot_end = current + timedelta(minutes=service.duration)
            is_available = True

            for apt in existing:
                apt_end = apt.scheduled_at + timedelta(minutes=apt.duration)
                if current < apt_end and slot_end > apt.scheduled_at:
                    is_available = False
                    break

            slots.append({
                'time': current.strftime('%H:%M'),
                'datetime': current.isoformat(),
                'available': is_available
            })
            current += timedelta(minutes=30)

        return jsonify({
            'date': date_str,
            'service': service.name,
            'duration': service.duration,
            'slots': slots
        }), 200

    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500