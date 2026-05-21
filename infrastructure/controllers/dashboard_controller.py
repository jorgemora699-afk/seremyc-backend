from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required
from datetime import datetime, date, timedelta
from infrastructure.database.db import db
from infrastructure.database.models import (
    AppointmentModel,
    ClientModel,
    FinanceModel,
    InventoryModel,
    ServiceModel
)

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/', methods=['GET'])
@jwt_required()
def get_dashboard():
    try:
        today = date.today()
        now = datetime.now()
        alert_date = today + timedelta(days=30)

        # ─── Citas de hoy ───────────────────────────────────────────
        today_appointments = AppointmentModel.query.filter(
            db.func.date(AppointmentModel.scheduled_at) == today
        ).order_by(AppointmentModel.scheduled_at).all()

        # ─── Próximas citas ─────────────────────────────────────────
        upcoming = AppointmentModel.query.filter(
            AppointmentModel.scheduled_at >= now,
            AppointmentModel.status.in_(['pending', 'confirmed'])
        ).order_by(AppointmentModel.scheduled_at).limit(10).all()

        # ─── Finanzas del día ───────────────────────────────────────
        today_finances = FinanceModel.query.filter_by(date=today).all()
        today_income = sum(float(f.amount) for f in today_finances if f.type == 'income')
        today_expense = sum(float(f.amount) for f in today_finances if f.type == 'expense')

        # ─── Finanzas del mes ───────────────────────────────────────
        month_finances = FinanceModel.query.filter(
            db.extract('year', FinanceModel.date) == now.year,
            db.extract('month', FinanceModel.date) == now.month
        ).all()
        month_income = sum(float(f.amount) for f in month_finances if f.type == 'income')
        month_expense = sum(float(f.amount) for f in month_finances if f.type == 'expense')

        # ─── Clientes recientes ─────────────────────────────────────
        recent_clients = ClientModel.query.filter_by(is_active=True)\
            .order_by(ClientModel.created_at.desc()).limit(5).all()

        # ─── Total clientes ─────────────────────────────────────────
        total_clients = ClientModel.query.filter_by(is_active=True).count()

        # ─── Productos con bajo stock ───────────────────────────────
        low_stock = InventoryModel.query.filter(
            InventoryModel.is_active == True,
            InventoryModel.quantity <= InventoryModel.min_stock
        ).all()

        # ─── Productos próximos a vencer ────────────────────────────
        expiring_soon = InventoryModel.query.filter(
            InventoryModel.is_active == True,
            InventoryModel.expiry_date != None,
            InventoryModel.expiry_date <= alert_date,
            InventoryModel.expiry_date >= today
        ).all()

        # ─── Productos vencidos ─────────────────────────────────────
        expired = InventoryModel.query.filter(
            InventoryModel.is_active == True,
            InventoryModel.expiry_date != None,
            InventoryModel.expiry_date < today
        ).all()

        # ─── Servicios más vendidos ─────────────────────────────────
        from sqlalchemy import func
        top_services = db.session.query(
            ServiceModel.name,
            func.count(AppointmentModel.id).label('total')
        ).join(AppointmentModel, AppointmentModel.service_id == ServiceModel.id)\
         .filter(AppointmentModel.status == 'finished')\
         .group_by(ServiceModel.name)\
         .order_by(func.count(AppointmentModel.id).desc())\
         .limit(5).all()

        # ─── Citas por estado hoy ───────────────────────────────────
        statuses = ['pending', 'confirmed', 'in_progress', 'finished', 'cancelled', 'no_show']
        appointments_by_status = {}
        for status in statuses:
            appointments_by_status[status] = AppointmentModel.query.filter(
                db.func.date(AppointmentModel.scheduled_at) == today,
                AppointmentModel.status == status
            ).count()

        # ─── Ingresos últimos 7 días ────────────────────────────────
        last_7_days = []
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            day_finances = FinanceModel.query.filter_by(date=day).all()
            day_income = sum(float(f.amount) for f in day_finances if f.type == 'income')
            day_expense = sum(float(f.amount) for f in day_finances if f.type == 'expense')
            last_7_days.append({
                'date': day.isoformat(),
                'day': day.strftime('%a'),
                'income': day_income,
                'expense': day_expense,
                'balance': day_income - day_expense
            })

        # ─── Response ───────────────────────────────────────────────
        return jsonify({
            'today': {
                'date': today.isoformat(),
                'appointments_count': len(today_appointments),
                'income': today_income,
                'expense': today_expense,
                'balance': today_income - today_expense,
                'appointments_by_status': appointments_by_status
            },
            'month': {
                'month': now.month,
                'year': now.year,
                'income': month_income,
                'expense': month_expense,
                'balance': month_income - month_expense
            },
            'upcoming_appointments': [
                {
                    'id': a.id,
                    'client_name': a.client.full_name if a.client else None,
                    'client_phone': a.client.phone if a.client else None,
                    'service_name': a.service.name if a.service else None,
                    'service_price': float(a.service.price) if a.service else None,
                    'final_price': float(a.final_price) if a.final_price else None,
                    'scheduled_at': a.scheduled_at.isoformat(),
                    'duration': a.duration,
                    'status': a.status,
                    'observations': a.observations
                } for a in upcoming
            ],
            'today_appointments': [
                {
                    'id': a.id,
                    'client_name': a.client.full_name if a.client else None,
                    'client_phone': a.client.phone if a.client else None,
                    'service_name': a.service.name if a.service else None,
                    'service_price': float(a.service.price) if a.service else None,
                    'final_price': float(a.final_price) if a.final_price else None,
                    'scheduled_at': a.scheduled_at.isoformat(),
                    'duration': a.duration,
                    'status': a.status,
                    'observations': a.observations
                } for a in today_appointments
            ],
            'recent_clients': [
                {
                    'id': c.id,
                    'full_name': c.full_name,
                    'phone': c.phone,
                    'whatsapp': c.whatsapp,
                    'created_at': c.created_at.isoformat() if c.created_at else None
                } for c in recent_clients
            ],
            'stats': {
                'total_clients': total_clients,
                'total_appointments_today': len(today_appointments),
                'top_services': [
                    {
                        'name': s.name,
                        'total': s.total
                    } for s in top_services
                ],
                'last_7_days': last_7_days
            },
            'alerts': {
                'low_stock': [
                    {
                        'id': i.id,
                        'name': i.name,
                        'quantity': float(i.quantity),
                        'min_stock': float(i.min_stock),
                        'unit': i.unit,
                        'deficit': float(i.min_stock) - float(i.quantity)
                    } for i in low_stock
                ],
                'expiring_soon': [
                    {
                        'id': i.id,
                        'name': i.name,
                        'expiry_date': i.expiry_date.isoformat(),
                        'days_remaining': (i.expiry_date - today).days,
                        'quantity': float(i.quantity),
                        'unit': i.unit
                    } for i in expiring_soon
                ],
                'expired': [
                    {
                        'id': i.id,
                        'name': i.name,
                        'expiry_date': i.expiry_date.isoformat(),
                        'quantity': float(i.quantity),
                        'unit': i.unit
                    } for i in expired
                ],
                'total_alerts': len(low_stock) + len(expiring_soon) + len(expired)
            }
        }), 200

    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500