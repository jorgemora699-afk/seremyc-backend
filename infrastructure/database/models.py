from datetime import datetime
from infrastructure.database.db import db


class UserModel(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ClientModel(db.Model):
    __tablename__ = 'clients'

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    whatsapp = db.Column(db.String(20))
    email = db.Column(db.String(120))
    birth_date = db.Column(db.Date)
    address = db.Column(db.String(255))
    skin_type = db.Column(db.String(50))
    allergies = db.Column(db.Text)
    observations = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    source = db.Column(db.String(20), default='manual')

    appointments = db.relationship('AppointmentModel', backref='client', lazy=True)
    photos = db.relationship('BeforeAfterPhotoModel', backref='client', lazy=True)


class ServiceModel(db.Model):
    __tablename__ = 'services'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(50), nullable=False)  # facial, corporal, capilar, sueroterapia
    description = db.Column(db.Text)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    duration = db.Column(db.Integer, nullable=False)  # minutos
    image_url = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    appointments = db.relationship('AppointmentModel', backref='service', lazy=True)


class AppointmentModel(db.Model):
    __tablename__ = 'appointments'

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=False)
    scheduled_at = db.Column(db.DateTime, nullable=False)
    duration = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='pending')
    observations = db.Column(db.Text)
    promotion_id = db.Column(db.Integer, db.ForeignKey('promotions.id'), nullable=True)
    discount_applied = db.Column(db.Numeric(10, 2), default=0)
    final_price = db.Column(db.Numeric(10, 2), nullable=True)
    is_paid = db.Column(db.Boolean, default=False)
    payment_method = db.Column(db.String(20), nullable=True)  # cash, transfer
    receipt_url = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.String(20), default='user')
    reminder_sent = db.Column(db.Boolean, default=False)

    payment = db.relationship('FinanceModel', backref='appointment', lazy=True)
    promotion = db.relationship('PromotionModel', backref='appointments', lazy=True)



class FinanceModel(db.Model):
    __tablename__ = 'finances'

    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(10), nullable=False)  # income, expense
    category = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    description = db.Column(db.Text)
    date = db.Column(db.Date, nullable=False)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class InventoryModel(db.Model):
    __tablename__ = 'inventory'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Numeric(10, 2), nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    purchase_price = db.Column(db.Numeric(10, 2), nullable=False)
    sale_price = db.Column(db.Numeric(10, 2))
    expiry_date = db.Column(db.Date)
    supplier = db.Column(db.String(150))
    min_stock = db.Column(db.Numeric(10, 2), default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PromotionModel(db.Model):
    __tablename__ = 'promotions'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    discount_type = db.Column(db.String(20), nullable=False)
    discount_value = db.Column(db.Numeric(10, 2), nullable=False)
    code = db.Column(db.String(50), unique=True)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    max_uses = db.Column(db.Integer, nullable=True)
    current_uses = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class BeforeAfterPhotoModel(db.Model):
    __tablename__ = 'before_after_photos'

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    before_url = db.Column(db.Text)
    after_url = db.Column(db.Text)
    treatment = db.Column(db.String(150))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

