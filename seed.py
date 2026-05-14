import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import subprocess
import bcrypt
from infrastructure.web.flask_app import create_app
from infrastructure.database.db import db
from infrastructure.database.models import UserModel

app = create_app()

with app.app_context():
    # Correr migraciones
    print('Running migrations...')
    subprocess.run(['flask', '--app', 'wsgi.py', 'db', 'upgrade'], check=True)

    # Crear usuario admin
    existing = UserModel.query.filter_by(email='admin@seremyc.com').first()
    if not existing:
        password_hash = bcrypt.hashpw(
            'admin123'.encode('utf-8'),
            bcrypt.gensalt()
        ).decode('utf-8')
        user = UserModel(
            name='Administrador',
            email='admin@seremyc.com',
            password_hash=password_hash
        )
        db.session.add(user)
        db.session.commit()
        print('Usuario admin creado')
    else:
        print('Usuario ya existe')