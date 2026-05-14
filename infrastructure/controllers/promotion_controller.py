from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from datetime import datetime
from application.use_cases.promotions.create_promotion_use_case import CreatePromotionUseCase
from application.use_cases.promotions.get_promotions_use_case import GetPromotionsUseCase
from infrastructure.repositories.promotion_repository import PromotionRepository

promotion_bp = Blueprint('promotions', __name__)


def serialize_promotion(promotion):
    return {
        'id': promotion.id,
        'name': promotion.name,
        'description': promotion.description,
        'discount_type': promotion.discount_type,
        'discount_value': float(promotion.discount_value),
        'code': promotion.code,
        'start_date': promotion.start_date.isoformat() if promotion.start_date else None,
        'end_date': promotion.end_date.isoformat() if promotion.end_date else None,
        'is_active': promotion.is_active,
        'created_at': promotion.created_at.isoformat() if promotion.created_at else None
    }


@promotion_bp.route('/', methods=['GET'])
@jwt_required()
def get_promotions():
    try:
        active_only = request.args.get('active') == 'true'
        use_case = GetPromotionsUseCase()
        promotions = use_case.execute(active_only=active_only)
        return jsonify([serialize_promotion(p) for p in promotions]), 200
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500


@promotion_bp.route('/<int:promotion_id>', methods=['GET'])
@jwt_required()
def get_promotion(promotion_id):
    try:
        use_case = GetPromotionsUseCase()
        promotion = use_case.execute_by_id(promotion_id)
        return jsonify(serialize_promotion(promotion)), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500


@promotion_bp.route('/', methods=['POST'])
@jwt_required()
def create_promotion():
    try:
        data = request.get_json()

        if not data.get('name') or not data.get('discount_value'):
            return jsonify({'error': 'Nombre y valor del descuento son requeridos'}), 400

        data['start_date'] = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
        data['end_date'] = datetime.strptime(data['end_date'], '%Y-%m-%d').date()

        use_case = CreatePromotionUseCase()
        promotion = use_case.execute(data)
        return jsonify(serialize_promotion(promotion)), 201

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500


@promotion_bp.route('/<int:promotion_id>', methods=['PUT'])
@jwt_required()
def update_promotion(promotion_id):
    try:
        data = request.get_json()
        repo = PromotionRepository()
        promotion = repo.find_by_id(promotion_id)

        if not promotion:
            return jsonify({'error': 'Promoción no encontrada'}), 404

        if data.get('start_date'):
            data['start_date'] = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
        if data.get('end_date'):
            data['end_date'] = datetime.strptime(data['end_date'], '%Y-%m-%d').date()

        promotion.name = data.get('name', promotion.name)
        promotion.description = data.get('description', promotion.description)
        promotion.discount_type = data.get('discount_type', promotion.discount_type)
        promotion.discount_value = data.get('discount_value', promotion.discount_value)
        promotion.code = data.get('code', promotion.code)
        promotion.start_date = data.get('start_date', promotion.start_date)
        promotion.end_date = data.get('end_date', promotion.end_date)
        promotion.is_active = data.get('is_active', promotion.is_active)

        repo.update(promotion)
        return jsonify(serialize_promotion(promotion)), 200

    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500


@promotion_bp.route('/<int:promotion_id>', methods=['DELETE'])
@jwt_required()
def delete_promotion(promotion_id):
    try:
        repo = PromotionRepository()
        promotion = repo.find_by_id(promotion_id)

        if not promotion:
            return jsonify({'error': 'Promoción no encontrada'}), 404

        repo.delete(promotion)
        return jsonify({'message': 'Promoción eliminada exitosamente'}), 200

    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500