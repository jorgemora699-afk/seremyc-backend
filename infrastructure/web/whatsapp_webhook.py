from flask import Blueprint, request
from twilio.twiml.messaging_response import MessagingResponse
from infrastructure.web.whatsapp_agent import procesar_mensaje

whatsapp_bp = Blueprint('whatsapp', __name__, url_prefix='/webhook')


@whatsapp_bp.route('/whatsapp', methods=['POST'])
def whatsapp_webhook():

    mensaje_entrante = request.form.get('Body', '').strip()
    numero_cliente  = request.form.get('From', '').strip()

    respuesta_texto = procesar_mensaje(
        numero=numero_cliente,
        mensaje=mensaje_entrante
    )

    resp = MessagingResponse()
    resp.message(respuesta_texto)

    return str(resp), 200, {'Content-Type': 'text/xml'}