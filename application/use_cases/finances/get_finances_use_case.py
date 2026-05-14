from datetime import date
from infrastructure.repositories.finance_repository import FinanceRepository
from infrastructure.database.models import FinanceModel
from infrastructure.database.db import db


class GetFinancesUseCase:

    def __init__(self):
        self.finance_repository = FinanceRepository()

    def execute(self, target_date: date = None, year: int = None, month: int = None) -> list:
        if target_date:
            return self.finance_repository.find_by_date(target_date)
        if year and month:
            return self.finance_repository.find_by_month(year, month)
        return self.finance_repository.find_all()

    def execute_summary(self, year: int, month: int) -> dict:
        records = self.finance_repository.find_by_month(year, month)
        incomes = sum(float(r.amount) for r in records if r.type == 'income')
        expenses = sum(float(r.amount) for r in records if r.type == 'expense')
        return {
            'incomes': incomes,
            'expenses': expenses,
            'balance': incomes - expenses
        }

    def execute_annual_summary(self, year: int) -> dict:
        months_data = []
        total_income = 0
        total_expense = 0

        month_names = [
            'Enero', 'Febrero', 'Marzo', 'Abril',
            'Mayo', 'Junio', 'Julio', 'Agosto',
            'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'
        ]

        for month in range(1, 13):
            records = self.finance_repository.find_by_month(year, month)
            income = sum(float(r.amount) for r in records if r.type == 'income')
            expense = sum(float(r.amount) for r in records if r.type == 'expense')
            total_income += income
            total_expense += expense

            months_data.append({
                'month': month,
                'month_name': month_names[month - 1],
                'income': income,
                'expense': expense,
                'balance': income - expense
            })

        # Categorías de gastos del año
        all_records = db.session.query(FinanceModel).filter(
            db.extract('year', FinanceModel.date) == year
        ).all()

        expense_by_category = {}
        for r in all_records:
            if r.type == 'expense':
                cat = r.category
                expense_by_category[cat] = expense_by_category.get(cat, 0) + float(r.amount)

        income_by_category = {}
        for r in all_records:
            if r.type == 'income':
                cat = r.category
                income_by_category[cat] = income_by_category.get(cat, 0) + float(r.amount)

        return {
            'year': year,
            'total_income': total_income,
            'total_expense': total_expense,
            'total_balance': total_income - total_expense,
            'months': months_data,
            'expense_by_category': expense_by_category,
            'income_by_category': income_by_category
        }