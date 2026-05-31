from flask import Blueprint, request, jsonify
from datetime import datetime
from functools import wraps
import os

# BASE DE DATOS
from infrastructure.database.db import db

# MODELOS
from infrastructure.database.models import ClientModel, AppointmentModel, ServiceModel


agent_bp = Blueprint(
    'agent',
    __name__,
    url_prefix='/api/agent'
)


# ─────────────────────────────────────────
# Middleware API KEY
# ─────────────────────────────────────────
def require_agent_key(f):

    @wraps(f)
    def decorated(*args, **kwargs):

        key = request.headers.get('X-Agent-Key')

        if key != os.getenv('AGENT_API_KEY'):

            return jsonify({
                'error': 'No autorizado'
            }), 401

        return f(*args, **kwargs)

    return decorated


# ─────────────────────────────────────────
# GET SERVICES
# ─────────────────────────────────────────
@agent_bp.route('/services', methods=['GET'])
@require_agent_key
def get_services():

    services = ServiceModel.query.filter_by(
        is_active=True
    ).all()

    return jsonify([{
        'id':               s.id,
        'name':             s.name,
        'category':         s.category,
        'description':      s.description,
        'duration_minutes': s.duration,
        'price':            float(s.price)
    } for s in services])


# ─────────────────────────────────────────
# GET AVAILABILITY
# ─────────────────────────────────────────
@agent_bp.route('/availability', methods=['GET'])
@require_agent_key
def get_availability():

    date_str = request.args.get('date')

    if not date_str:

        return jsonify({
            'error': 'El parámetro date es requerido'
        }), 400

    try:

        date = datetime.strptime(
            date_str,
            '%Y-%m-%d'
        ).date()

    except ValueError:

        return jsonify({
            'error': 'Formato inválido. Usa YYYY-MM-DD'
        }), 400

    # Horario laboral
    work_hours = [
        8, 9, 10, 11,
        12, 13, 14,
        15, 16, 17, 18
    ]

    appointments = AppointmentModel.query.filter(
        db.func.date(AppointmentModel.scheduled_at) == date,
        AppointmentModel.status != 'cancelled'
    ).all()

    booked_hours = {
        a.scheduled_at.hour
        for a in appointments
    }

    available_slots = []

    for hour in work_hours:

        if hour not in booked_hours:

            slot = datetime.combine(
                date,
                datetime.min.time()
            ).replace(hour=hour)

            available_slots.append({
                'datetime': slot.isoformat(),
                'label': f'{hour:02d}:00'
            })

    return jsonify({
        'date': date_str,
        'available': available_slots,
        'total_free': len(available_slots)
    })


# ─────────────────────────────────────────
# CREATE OR UPDATE CLIENT
# ─────────────────────────────────────────
@agent_bp.route('/clients', methods=['POST'])
@require_agent_key
def create_or_get_client():

    data = request.get_json()

    required = [
        'full_name',
        'phone'
    ]

    for field in required:

        if not data.get(field):

            return jsonify({
                'error': f'El campo {field} es requerido'
            }), 400

    client = ClientModel.query.filter_by(
        phone=data['phone']
    ).first()

    created = False

    if client:

        client.full_name = data.get(
            'full_name',
            client.full_name
        )

        client.email = data.get(
            'email',
            client.email
        )

        client.address = data.get(
            'address',
            client.address
        )

        client.skin_type = data.get(
            'skin_type',
            client.skin_type
        )

        client.allergies = data.get(
            'allergies',
            client.allergies
        )

        client.observations = data.get(
            'observations',
            client.observations
        )

        birth_date = _parse_date(
            data.get('birth_date')
        )

        if birth_date:
            client.birth_date = birth_date

    else:

        client = ClientModel(
            full_name=data['full_name'],
            phone=data['phone'],
            email=data.get('email'),
            birth_date=_parse_date(
                data.get('birth_date')
            ),
            address=data.get('address'),
            skin_type=data.get('skin_type'),
            allergies=data.get('allergies'),
            observations=data.get('observations'),
            source='whatsapp'
        )

        db.session.add(client)

        created = True

    db.session.commit()

    return jsonify({
        'client_id': client.id,
        'full_name': client.full_name,
        'created': created,
        'message': (
            'Cliente creado'
            if created
            else 'Cliente actualizado'
        )
    }), 201 if created else 200


# ─────────────────────────────────────────
# CREATE APPOINTMENT
# ─────────────────────────────────────────
@agent_bp.route('/appointments', methods=['POST'])
@require_agent_key
def create_appointment():

    data = request.get_json()

    required = [
        'client_id',
        'service_id',
        'scheduled_at'
    ]

    for field in required:

        if not data.get(field):

            return jsonify({
                'error': f'El campo {field} es requerido'
            }), 400

    client = ClientModel.query.get(
        data['client_id']
    )

    if not client:

        return jsonify({
            'error': 'Cliente no encontrado'
        }), 404

    service = ServiceModel.query.get(
        data['service_id']
    )

    if not service:

        return jsonify({
            'error': 'Servicio no encontrado'
        }), 404

    try:

        scheduled_at = datetime.fromisoformat(
            data['scheduled_at']
        )

    except ValueError:

        return jsonify({
            'error': 'Formato inválido'
        }), 400

    conflict = AppointmentModel.query.filter(
        AppointmentModel.scheduled_at == scheduled_at,
        AppointmentModel.status != 'cancelled'
    ).first()

    if conflict:

        return jsonify({
            'error': 'Horario ocupado'
        }), 409

    appointment = AppointmentModel(
        client_id=client.id,
        service_id=service.id,
        scheduled_at=scheduled_at,
        duration=service.duration,
        status='confirmed',
        notes=data.get('notes', ''),
        created_by='ai_agent'
    )

    db.session.add(appointment)
    db.session.commit()

    return jsonify({
        'appointment_id': appointment.id,
        'client': client.full_name,
        'service': service.name,
        'scheduled_at': scheduled_at.isoformat(),
        'price': float(service.price),
        'duration': service.duration_minutes,
        'status': 'confirmed',
        'message': '¡Cita agendada exitosamente!'
    }), 201


# ─────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────
def _parse_date(value):

    if not value:
        return None

    formats = [
        '%Y-%m-%d',
        '%d/%m/%Y',
        '%d-%m-%Y'
    ]

    for fmt in formats:

        try:

            return datetime.strptime(
                value,
                fmt
            ).date()

        except ValueError:
            continue

    return None