import os
from flask import Blueprint, request, jsonify
from infrastructure.web.whatsapp_agent import procesar_mensaje
from infrastructure.web.whatsapp_sender import enviar_mensaje

whatsapp_bp = Blueprint('whatsapp', __name__, url_prefix='/webhook')

PROVIDER = os.getenv('WHATSAPP_PROVIDER', 'twilio')


@whatsapp_bp.route('/whatsapp', methods=['POST'])
def whatsapp_webhook():

    if PROVIDER == 'meta':
        return _handle_meta()
    return _handle_twilio()


# ─────────────────────────────────────────
# Twilio
# ─────────────────────────────────────────
def _handle_twilio():
    from twilio.twiml.messaging_response import MessagingResponse

    mensaje_entrante = request.form.get('Body', '').strip()
    numero_cliente   = request.form.get('From', '').strip()

    if not mensaje_entrante or not numero_cliente:
        return '', 200

    respuesta_texto = procesar_mensaje(
        numero=numero_cliente,
        mensaje=mensaje_entrante
    )

    resp = MessagingResponse()
    resp.message(respuesta_texto)
    return str(resp), 200, {'Content-Type': 'text/xml'}


# ─────────────────────────────────────────
# Meta WhatsApp Business API
# ─────────────────────────────────────────
mensajes_procesados = set()

def _handle_meta():
    data = request.get_json()
    try:
        entry    = data['entry'][0]
        change   = entry['changes'][0]['value']
        messages = change.get('messages', [])

        if not messages:
            return jsonify({'status': 'ok'}), 200

        # Deduplicar por message_id
        message_id = messages[0].get('id')
        if message_id in mensajes_procesados:
            return jsonify({'status': 'ok'}), 200
        mensajes_procesados.add(message_id)

        mensaje_entrante = messages[0]['text']['body'].strip()
        numero_cliente   = messages[0]['from']

        respuesta_texto = procesar_mensaje(
            numero=numero_cliente,
            mensaje=mensaje_entrante
        )

        enviar_mensaje(numero_cliente, respuesta_texto)

    except (KeyError, IndexError):
        pass

    return jsonify({'status': 'ok'}), 200


# ─────────────────────────────────────────
# Verificación GET para Meta
# ─────────────────────────────────────────
@whatsapp_bp.route('/whatsapp', methods=['GET'])
def whatsapp_verify():
    token = request.args.get('hub.verify_token')
    expected = os.getenv('META_VERIFY_TOKEN')
    print(f"TOKEN RECIBIDO: {token}")
    print(f"TOKEN ESPERADO: {expected}")
    if token == expected:
        return request.args.get('hub.challenge'), 200
    return 'Token inválido', 403