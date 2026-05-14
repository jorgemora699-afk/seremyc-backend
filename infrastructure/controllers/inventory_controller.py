from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from datetime import datetime
from application.use_cases.inventory.create_inventory_use_case import CreateInventoryUseCase
from application.use_cases.inventory.get_inventory_use_case import GetInventoryUseCase
from infrastructure.repositories.inventory_repository import InventoryRepository

inventory_bp = Blueprint('inventory', __name__)


def serialize_item(item):
    return {
        'id': item.id,
        'name': item.name,
        'category': item.category,
        'quantity': float(item.quantity),
        'unit': item.unit,
        'purchase_price': float(item.purchase_price),
        'sale_price': float(item.sale_price) if item.sale_price else None,
        'expiry_date': item.expiry_date.isoformat() if item.expiry_date else None,
        'supplier': item.supplier,
        'min_stock': float(item.min_stock),
        'is_active': item.is_active,
        'is_low_stock': float(item.quantity) <= float(item.min_stock),
        'created_at': item.created_at.isoformat() if item.created_at else None
    }


@inventory_bp.route('/', methods=['GET'])
@jwt_required()
def get_inventory():
    try:
        query = request.args.get('q')
        low_stock = request.args.get('low_stock') == 'true'

        use_case = GetInventoryUseCase()
        items = use_case.execute(query=query, low_stock=low_stock)
        return jsonify([serialize_item(i) for i in items]), 200
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500


@inventory_bp.route('/<int:inventory_id>', methods=['GET'])
@jwt_required()
def get_item(inventory_id):
    try:
        use_case = GetInventoryUseCase()
        item = use_case.execute_by_id(inventory_id)
        return jsonify(serialize_item(item)), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500


@inventory_bp.route('/', methods=['POST'])
@jwt_required()
def create_item():
    try:
        data = request.get_json()

        if not data.get('name') or not data.get('quantity') or not data.get('unit'):
            return jsonify({'error': 'Nombre, cantidad y unidad son requeridos'}), 400

        if data.get('expiry_date'):
            data['expiry_date'] = datetime.strptime(data['expiry_date'], '%Y-%m-%d').date()

        use_case = CreateInventoryUseCase()
        item = use_case.execute(data)
        return jsonify(serialize_item(item)), 201

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500


@inventory_bp.route('/<int:inventory_id>', methods=['PUT'])
@jwt_required()
def update_item(inventory_id):
    try:
        data = request.get_json()
        repo = InventoryRepository()
        item = repo.find_by_id(inventory_id)

        if not item:
            return jsonify({'error': 'Producto no encontrado'}), 404

        if data.get('expiry_date'):
            data['expiry_date'] = datetime.strptime(data['expiry_date'], '%Y-%m-%d').date()

        item.name = data.get('name', item.name)
        item.category = data.get('category', item.category)
        item.quantity = data.get('quantity', item.quantity)
        item.unit = data.get('unit', item.unit)
        item.purchase_price = data.get('purchase_price', item.purchase_price)
        item.sale_price = data.get('sale_price', item.sale_price)
        item.expiry_date = data.get('expiry_date', item.expiry_date)
        item.supplier = data.get('supplier', item.supplier)
        item.min_stock = data.get('min_stock', item.min_stock)

        repo.update(item)
        return jsonify(serialize_item(item)), 200

    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500


@inventory_bp.route('/<int:inventory_id>', methods=['DELETE'])
@jwt_required()
def delete_item(inventory_id):
    try:
        repo = InventoryRepository()
        item = repo.find_by_id(inventory_id)

        if not item:
            return jsonify({'error': 'Producto no encontrado'}), 404

        repo.delete(item)
        return jsonify({'message': 'Producto eliminado exitosamente'}), 200

    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500


@inventory_bp.route('/alerts/expiry', methods=['GET'])
@jwt_required()
def get_expiry_alerts():
    try:
        from datetime import date, timedelta
        days = int(request.args.get('days', 30))
        today = date.today()
        alert_date = today + timedelta(days=days)

        from infrastructure.database.models import InventoryModel
        items = InventoryModel.query.filter(
            InventoryModel.is_active == True,
            InventoryModel.expiry_date != None,
            InventoryModel.expiry_date <= alert_date
        ).order_by(InventoryModel.expiry_date).all()

        return jsonify({
            'alert_days': days,
            'total': len(items),
            'items': [
                {
                    'id': i.id,
                    'name': i.name,
                    'category': i.category,
                    'quantity': float(i.quantity),
                    'unit': i.unit,
                    'expiry_date': i.expiry_date.isoformat(),
                    'days_remaining': (i.expiry_date - today).days,
                    'is_expired': i.expiry_date < today,
                    'supplier': i.supplier
                } for i in items
            ]
        }), 200
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500


@inventory_bp.route('/alerts/low-stock', methods=['GET'])
@jwt_required()
def get_low_stock_alerts():
    try:
        from infrastructure.database.models import InventoryModel
        items = InventoryModel.query.filter(
            InventoryModel.is_active == True,
            InventoryModel.quantity <= InventoryModel.min_stock
        ).order_by(InventoryModel.quantity).all()

        return jsonify({
            'total': len(items),
            'items': [
                {
                    'id': i.id,
                    'name': i.name,
                    'category': i.category,
                    'quantity': float(i.quantity),
                    'min_stock': float(i.min_stock),
                    'unit': i.unit,
                    'supplier': i.supplier,
                    'deficit': float(i.min_stock) - float(i.quantity)
                } for i in items
            ]
        }), 200
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500


@inventory_bp.route('/alerts/summary', methods=['GET'])
@jwt_required()
def get_alerts_summary():
    try:
        from datetime import date, timedelta
        from infrastructure.database.models import InventoryModel

        today = date.today()
        alert_date = today + timedelta(days=30)

        low_stock = InventoryModel.query.filter(
            InventoryModel.is_active == True,
            InventoryModel.quantity <= InventoryModel.min_stock
        ).count()

        expiring_soon = InventoryModel.query.filter(
            InventoryModel.is_active == True,
            InventoryModel.expiry_date != None,
            InventoryModel.expiry_date <= alert_date,
            InventoryModel.expiry_date >= today
        ).count()

        expired = InventoryModel.query.filter(
            InventoryModel.is_active == True,
            InventoryModel.expiry_date != None,
            InventoryModel.expiry_date < today
        ).count()

        return jsonify({
            'low_stock': low_stock,
            'expiring_soon': expiring_soon,
            'expired': expired,
            'total_alerts': low_stock + expiring_soon + expired
        }), 200
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500