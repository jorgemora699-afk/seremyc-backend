from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from infrastructure.database.db import db
from infrastructure.database.models import BeforeAfterPhotoModel

photo_bp = Blueprint('photos', __name__)


def serialize_photo(photo):
    return {
        'id': photo.id,
        'client_id': photo.client_id,
        'before_url': photo.before_url,
        'after_url': photo.after_url,
        'treatment': photo.treatment,
        'notes': photo.notes,
        'created_at': photo.created_at.isoformat() if photo.created_at else None
    }


@photo_bp.route('/by-client/<int:client_id>', methods=['GET'])
@jwt_required()
def get_photos(client_id):
    try:
        photos = BeforeAfterPhotoModel.query.filter_by(client_id=client_id)\
            .order_by(BeforeAfterPhotoModel.created_at.desc()).all()
        return jsonify([serialize_photo(p) for p in photos]), 200
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500


@photo_bp.route('/', methods=['POST'])
@jwt_required()
def create_photo():
    try:
        data = request.get_json()

        if not data.get('client_id'):
            return jsonify({'error': 'Cliente es requerido'}), 400

        photo = BeforeAfterPhotoModel(
            client_id=data.get('client_id'),
            before_url=data.get('before_url'),
            after_url=data.get('after_url'),
            treatment=data.get('treatment'),
            notes=data.get('notes')
        )
        db.session.add(photo)
        db.session.commit()
        return jsonify(serialize_photo(photo)), 201

    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500


@photo_bp.route('/<int:photo_id>', methods=['PUT'])
@jwt_required()
def update_photo(photo_id):
    try:
        data = request.get_json()
        photo = BeforeAfterPhotoModel.query.get(photo_id)

        if not photo:
            return jsonify({'error': 'Foto no encontrada'}), 404

        photo.before_url = data.get('before_url', photo.before_url)
        photo.after_url = data.get('after_url', photo.after_url)
        photo.treatment = data.get('treatment', photo.treatment)
        photo.notes = data.get('notes', photo.notes)

        db.session.commit()
        return jsonify(serialize_photo(photo)), 200

    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500


@photo_bp.route('/<int:photo_id>', methods=['DELETE'])
@jwt_required()
def delete_photo(photo_id):
    try:
        photo = BeforeAfterPhotoModel.query.get(photo_id)

        if not photo:
            return jsonify({'error': 'Foto no encontrada'}), 404

        db.session.delete(photo)
        db.session.commit()
        return jsonify({'message': 'Foto eliminada exitosamente'}), 200

    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500