import os
import logging
import requests
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


def _obtener_modo(phone: str) -> str:
    try:
        base_url = os.getenv('API_BASE_URL', 'http://localhost:5000')
        headers  = {'X-Agent-Key': os.getenv('AGENT_API_KEY')}
        r = requests.get(
            f'{base_url}/api/agent/conversation-mode/{phone}',
            headers=headers,
            timeout=3
        )
        return r.json().get('mode', 'bot')
    except Exception:
        return 'bot'  # por defecto siempre responde el bot


def _handle_meta():
    data = request.get_json()
    try:
        entry    = data['entry'][0]
        change   = entry['changes'][0]['value']
        messages = change.get('messages', [])

        if not messages:
            return jsonify({'status': 'ok'}), 200

        # Ignorar mensajes viejos
        timestamp = int(messages[0].get('timestamp', 0))
        ahora = int(datetime.now().timestamp())
        if ahora - timestamp > 30:
            return jsonify({'status': 'ok'}), 200

        # Deduplicar
        message_id = messages[0].get('id')
        if message_id in mensajes_procesados:
            return jsonify({'status': 'ok'}), 200
        mensajes_procesados.add(message_id)

        # Solo mensajes de texto
        if messages[0].get('type') != 'text':
            return jsonify({'status': 'ok'}), 200

        mensaje_entrante = messages[0]['text']['body'].strip()
        numero_cliente   = messages[0]['from']

        # ── Verificar modo ──────────────────────────────
        modo = _obtener_modo(numero_cliente)

        if modo == 'human':
            # No responde el bot, solo registra que llegó el mensaje
            logger.info(f"Mensaje en modo HUMAN de {numero_cliente}: {mensaje_entrante}")
            return jsonify({'status': 'ok'}), 200

        # ── Modo bot: responder normalmente ─────────────
        respuesta_texto = procesar_mensaje(
            numero=numero_cliente,
            mensaje=mensaje_entrante
        )

        # Si el cliente pidió asesor, cambiar modo a human
        if respuesta_texto == 'SOLICITA_ASESOR':
            _cambiar_modo(numero_cliente, 'human')
            respuesta_texto = _manejar_asesor_webhook(numero_cliente)

        enviar_mensaje(numero_cliente, respuesta_texto)

    except (KeyError, IndexError) as e:
        logger.error(f"Error procesando webhook Meta: {e}")

    return jsonify({'status': 'ok'}), 200


def _cambiar_modo(phone: str, mode: str) -> None:
    try:
        base_url = os.getenv('API_BASE_URL', 'http://localhost:5000')
        headers  = {
            'X-Agent-Key':  os.getenv('AGENT_API_KEY'),
            'Content-Type': 'application/json'
        }
        requests.put(
            f'{base_url}/api/agent/conversation-mode/{phone}',
            json={'mode': mode, 'updated_by': 'bot'},
            headers=headers,
            timeout=3
        )
    except Exception as e:
        logger.error(f"Error cambiando modo: {e}")


def _manejar_asesor_webhook(phone: str) -> str:
    numero_asesor = os.getenv('ASESOR_WHATSAPP', '')
    if numero_asesor:
        return (
            f"¡Claro! 😊 Te conecto con una de nuestras asesoras ahora mismo.\n\n"
            f"📲 También puedes escribirnos aquí: wa.me/{numero_asesor}\n\n"
            f"En breve alguien de nuestro equipo te atenderá 💜"
        )
    return (
        f"¡Claro! 😊 Te voy a conectar con una de nuestras asesoras.\n\n"
        f"En breve alguien de nuestro equipo te atenderá personalmente 💜"
    )

# ─────────────────────────────────────────
# Verificación GET para Meta
# ─────────────────────────────────────────
@whatsapp_bp.route('/whatsapp', methods=['GET'])
def whatsapp_verify():
    token = request.args.get('hub.verify_token')
    expected = os.getenv('META_VERIFY_TOKEN')
    if token == expected:
        return request.args.get('hub.challenge'), 200
    return 'Token inválido', 403