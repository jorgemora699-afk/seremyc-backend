import os
import logging
import requests

logger = logging.getLogger(__name__)

PROVIDER = os.getenv('WHATSAPP_PROVIDER', 'twilio')


# ─────────────────────────────────────────
# Enviar mensaje — punto de entrada único
# ─────────────────────────────────────────
def enviar_mensaje(numero: str, texto: str) -> bool:
    if PROVIDER == 'meta':
        return _enviar_meta(numero, texto)
    return _enviar_twilio(numero, texto)


# ─────────────────────────────────────────
# Twilio
# ─────────────────────────────────────────
def _enviar_twilio(numero: str, texto: str) -> bool:
    try:
        from twilio.rest import Client
        client = Client(
            os.getenv('TWILIO_ACCOUNT_SID'),
            os.getenv('TWILIO_AUTH_TOKEN')
        )
        to = f'whatsapp:{numero}' if not numero.startswith('whatsapp:') else numero
        client.messages.create(
            from_=os.getenv('TWILIO_WHATSAPP_NUMBER'),
            to=to,
            body=texto
        )
        return True
    except Exception as e:
        logger.error(f"Error Twilio enviando a {numero}: {e}")
        return False


# ─────────────────────────────────────────
# Meta WhatsApp Business API
# ─────────────────────────────────────────
def _enviar_meta(numero: str, texto: str) -> bool:
    try:
        phone_number_id = os.getenv('META_PHONE_NUMBER_ID')
        access_token    = os.getenv('META_ACCESS_TOKEN')

        # Limpiar número — Meta no acepta el prefijo whatsapp:
        numero_limpio = numero.replace('whatsapp:', '').strip()

        r = requests.post(
            f'https://graph.facebook.com/v23.0/{phone_number_id}/messages',
            headers={
                'Authorization': f'Bearer {access_token}',
                'Content-Type':  'application/json'
            },
            json={
                'messaging_product': 'whatsapp',
                'to':                numero_limpio,
                'type':              'text',
                'text':              {'body': texto}
            },
            timeout=10
        )
        r.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Error Meta enviando a {numero}: {e}")
        return False