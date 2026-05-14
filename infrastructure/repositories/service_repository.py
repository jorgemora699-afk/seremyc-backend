from infrastructure.database.db import db
from infrastructure.database.models import ServiceModel


class ServiceRepository:

    def find_all(self) -> list:
        return ServiceModel.query.filter_by(is_active=True).order_by(ServiceModel.name).all()

    def find_by_id(self, service_id: int) -> ServiceModel | None:
        return ServiceModel.query.filter_by(id=service_id, is_active=True).first()

    def find_by_category(self, category: str) -> list:
        return ServiceModel.query.filter_by(category=category, is_active=True).all()

    def search(self, query: str) -> list:
        return ServiceModel.query.filter(
            ServiceModel.is_active == True,
            ServiceModel.name.ilike(f'%{query}%') |
            ServiceModel.category.ilike(f'%{query}%')
        ).all()

    def save(self, service: ServiceModel) -> ServiceModel:
        db.session.add(service)
        db.session.commit()
        return service

    def update(self, service: ServiceModel) -> ServiceModel:
        db.session.commit()
        return service

    def delete(self, service: ServiceModel) -> None:
        service.is_active = False
        db.session.commit()