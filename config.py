import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'seremyc-secret-key')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'seremyc-jwt-secret')
    JWT_ACCESS_TOKEN_EXPIRES = 86400  # 24 horas
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB para imágenes
    ALLOWED_EMAILS = [
        email.strip()
        for email in os.getenv('ALLOWED_EMAILS', '').split(',')
        if email.strip()
    ]