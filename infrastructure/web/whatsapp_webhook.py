import os
import logging
from flask import Blueprint, request, jsonify
from infrastructure.web.whatsapp_agent import procesar_mensaje
from infrastructure.web.whatsapp_sender import enviar_mensaje

logger = logging.getLogger(__name__)

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
mensajes_procesados: set = set()


def _handle_meta():
    data = request.get_json()
    try:
        entry    = data['entry'][0]
        change   = entry['changes'][0]['value']
        messages = change.get('messages', [])

        if not messages:
            return jsonify({'status': 'ok'}), 200

        mensaje = messages[0]

        # Ignorar mensajes que no sean de texto (audio, imagen, etc.)
        if mensaje.get('type') != 'text':
            logger.info(f"[META] Mensaje no-texto ignorado: {mensaje.get('type')}")
            return jsonify({'status': 'ok'}), 200

        # Deduplicar por message_id
        wamid = mensaje.get('id', '')
        if wamid in mensajes_procesados:
            logger.info(f"[META] Duplicado ignorado: {wamid}")
            return jsonify({'status': 'ok'}), 200
        mensajes_procesados.add(wamid)

        # Limpiar el set si crece mucho
        if len(mensajes_procesados) > 1000:
            mensajes_procesados.clear()

        mensaje_entrante = mensaje['text']['body'].strip()
        numero_cliente   = mensaje['from']

        logger.info(f"[META] Mensaje de {numero_cliente}: {mensaje_entrante[:60]}")

        respuesta_texto = procesar_mensaje(
            numero=numero_cliente,
            mensaje=mensaje_entrante
        )

        logger.info(f"[META] Respuesta generada para {numero_cliente}: {respuesta_texto[:80]}")

        exito = enviar_mensaje(numero_cliente, respuesta_texto)
        if not exito:
            logger.error(f"[META] FALLO al enviar respuesta a {numero_cliente}")

    except Exception as e:
        # ← antes era (KeyError, IndexError): pass — tragaba errores silenciosamente
        logger.error(f"[META] Error inesperado: {e}", exc_info=True)

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