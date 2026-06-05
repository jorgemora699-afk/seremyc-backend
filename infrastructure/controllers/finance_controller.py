from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from datetime import datetime
from flask import send_file
import io
from application.use_cases.finances.create_finance_use_case import CreateFinanceUseCase
from application.use_cases.finances.get_finances_use_case import GetFinancesUseCase

finance_bp = Blueprint('finances', __name__)


def serialize_finance(finance):
    return {
        'id': finance.id,
        'type': finance.type,
        'category': finance.category,
        'amount': float(finance.amount),
        'description': finance.description,
        'date': finance.date.isoformat() if finance.date else None,
        'appointment_id': finance.appointment_id,
        'created_at': finance.created_at.isoformat() if finance.created_at else None
    }


@finance_bp.route('/', methods=['GET'])
@jwt_required()
def get_finances():
    try:
        date_str = request.args.get('date')
        year = request.args.get('year')
        month = request.args.get('month')

        target_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else None

        use_case = GetFinancesUseCase()
        finances = use_case.execute(
            target_date=target_date,
            year=int(year) if year else None,
            month=int(month) if month else None
        )
        return jsonify([serialize_finance(f) for f in finances]), 200
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500


@finance_bp.route('/summary', methods=['GET'])
@jwt_required()
def get_summary():
    try:
        year = request.args.get('year', datetime.now().year)
        month = request.args.get('month', datetime.now().month)

        use_case = GetFinancesUseCase()
        summary = use_case.execute_summary(int(year), int(month))
        return jsonify(summary), 200
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500


@finance_bp.route('/', methods=['POST'])
@jwt_required()
def create_finance():
    try:
        data = request.get_json()

        if not data.get('type') or not data.get('amount') or not data.get('date'):
            return jsonify({'error': 'Tipo, monto y fecha son requeridos'}), 400

        if data['type'] not in ['income', 'expense']:
            return jsonify({'error': 'Tipo inválido'}), 400

        data['date'] = datetime.strptime(data['date'], '%Y-%m-%d').date()

        use_case = CreateFinanceUseCase()
        finance = use_case.execute(data)
        return jsonify(serialize_finance(finance)), 201

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500
    
@finance_bp.route('/<int:finance_id>', methods=['DELETE'])
@jwt_required()
def delete_finance(finance_id):
    try:
        from infrastructure.repositories.finance_repository import FinanceRepository
        repo = FinanceRepository()
        finance = repo.find_by_id(finance_id)

        if not finance:
            return jsonify({'error': 'Registro no encontrado'}), 404

        repo.delete(finance)
        return jsonify({'message': 'Registro eliminado exitosamente'}), 200

    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500    
    
@finance_bp.route('/annual', methods=['GET'])
@jwt_required()
def get_annual():
    try:
        year = request.args.get('year', datetime.now().year)
        use_case = GetFinancesUseCase()
        summary = use_case.execute_annual_summary(int(year))
        return jsonify(summary), 200
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500


@finance_bp.route('/report/pdf', methods=['GET'])
@jwt_required()
def export_pdf():
    try:
        from infrastructure.utils.report_generator import generate_finance_pdf
        report_type = request.args.get('type', 'monthly')
        year = int(request.args.get('year', datetime.now().year))
        month = int(request.args.get('month', datetime.now().month))

        use_case = GetFinancesUseCase()

        if report_type == 'annual':
            data = use_case.execute_annual_summary(year)
        else:
            records = use_case.execute(year=year, month=month)
            summary = use_case.execute_summary(year, month)
            data = {
                **summary,
                'records': [serialize_finance(r) for r in records]
            }

        pdf_bytes = generate_finance_pdf(data, report_type)

        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'reporte_{report_type}_{year}.pdf'
        )
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500


@finance_bp.route('/report/excel', methods=['GET'])
@jwt_required()
def export_excel():
    try:
        from infrastructure.utils.report_generator import generate_finance_excel
        report_type = request.args.get('type', 'monthly')
        year = int(request.args.get('year', datetime.now().year))
        month = int(request.args.get('month', datetime.now().month))

        use_case = GetFinancesUseCase()

        if report_type == 'annual':
            data = use_case.execute_annual_summary(year)
        else:
            records = use_case.execute(year=year, month=month)
            summary = use_case.execute_summary(year, month)
            data = {
                **summary,
                'records': [serialize_finance(r) for r in records]
            }

        excel_bytes = generate_finance_excel(data, report_type)

        return send_file(
            io.BytesIO(excel_bytes),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'reporte_{report_type}_{year}.xlsx'
        )
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500