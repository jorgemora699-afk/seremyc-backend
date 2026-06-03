import os
import logging
import requests

logger = logging.getLogger(__name__)

PROVIDER = os.getenv('WHATSAPP_PROVIDER', 'twilio')


# ─────────────────────────────────────────
# Enviar texto — punto de entrada único
# ─────────────────────────────────────────
def enviar_mensaje(numero: str, texto: str) -> bool:
    if PROVIDER == 'meta':
        return _enviar_meta(numero, texto)
    return _enviar_twilio(numero, texto)


# ─────────────────────────────────────────
# Enviar botones (hasta 3 opciones)
# ─────────────────────────────────────────
def enviar_botones(numero: str, texto: str, botones: list[dict]) -> bool:
    """
    botones = [
        {'id': 'facial', 'title': '🌸 Facial'},
        {'id': 'corporal', 'title': '💆 Corporal'},
    ]
    """
    if PROVIDER != 'meta':
        # Fallback texto para Twilio
        opciones = '\n'.join(f"• {b['title']}" for b in botones)
        return _enviar_twilio(numero, f"{texto}\n\n{opciones}")

    try:
        phone_number_id = os.getenv('META_PHONE_NUMBER_ID')
        access_token    = os.getenv('META_ACCESS_TOKEN')
        numero_limpio   = numero.replace('whatsapp:', '').strip()

        r = requests.post(
            f'https://graph.facebook.com/v23.0/{phone_number_id}/messages',
            headers={
                'Authorization': f'Bearer {access_token}',
                'Content-Type':  'application/json'
            },
            json={
                'messaging_product': 'whatsapp',
                'to':   numero_limpio,
                'type': 'interactive',
                'interactive': {
                    'type': 'button',
                    'body': {'text': texto},
                    'action': {
                        'buttons': [
                            {
                                'type': 'reply',
                                'reply': {
                                    'id':    b['id'],
                                    'title': b['title'][:20]  # Meta limita a 20 chars
                                }
                            }
                            for b in botones[:3]  # Meta permite máx 3
                        ]
                    }
                }
            },
            timeout=10
        )
        logger.info(f"Meta botones response: {r.status_code} - {r.text}")
        r.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Error Meta botones a {numero}: {e}")
        return False


# ─────────────────────────────────────────
# Enviar lista (hasta 10 opciones)
# ─────────────────────────────────────────
def enviar_lista(numero: str, texto: str, boton_label: str, secciones: list[dict]) -> bool:
    """
    secciones = [
        {
            'title': 'Servicios Faciales',
            'rows': [
                {'id': 'svc_1', 'title': 'Skin Booster', 'description': '1h 30min · $280,000'},
                {'id': 'svc_2', 'title': 'Toxina botulínica', 'description': '1h 30min · $102,000'},
            ]
        }
    ]
    """
    if PROVIDER != 'meta':
        # Fallback texto para Twilio
        filas = '\n'.join(
            f"• {r['title']}"
            for s in secciones
            for r in s['rows']
        )
        return _enviar_twilio(numero, f"{texto}\n\n{filas}")

    try:
        phone_number_id = os.getenv('META_PHONE_NUMBER_ID')
        access_token    = os.getenv('META_ACCESS_TOKEN')
        numero_limpio   = numero.replace('whatsapp:', '').strip()

        r = requests.post(
            f'https://graph.facebook.com/v23.0/{phone_number_id}/messages',
            headers={
                'Authorization': f'Bearer {access_token}',
                'Content-Type':  'application/json'
            },
            json={
                'messaging_product': 'whatsapp',
                'to':   numero_limpio,
                'type': 'interactive',
                'interactive': {
                    'type': 'list',
                    'body': {'text': texto},
                    'action': {
                        'button': boton_label[:20],
                        'sections': [
                            {
                                'title': s['title'][:24],
                                'rows': [
                                    {
                                        'id':          row['id'][:200],
                                        'title':       row['title'][:24],
                                        'description': row.get('description', '')[:72]
                                    }
                                    for row in s['rows']
                                ]
                            }
                            for s in secciones
                        ]
                    }
                }
            },
            timeout=10
        )
        logger.info(f"Meta lista response: {r.status_code} - {r.text}")
        r.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Error Meta lista a {numero}: {e}")
        return False


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
# Meta WhatsApp Business API — texto simple
# ─────────────────────────────────────────
def _enviar_meta(numero: str, texto: str) -> bool:
    try:
        phone_number_id = os.getenv('META_PHONE_NUMBER_ID')
        access_token    = os.getenv('META_ACCESS_TOKEN')
        numero_limpio   = numero.replace('whatsapp:', '').strip()

        r = requests.post(
            f'https://graph.facebook.com/v23.0/{phone_number_id}/messages',
            headers={
                'Authorization': f'Bearer {access_token}',
                'Content-Type':  'application/json'
            },
            json={
                'messaging_product': 'whatsapp',
                'to':   numero_limpio,
                'type': 'text',
                'text': {'body': texto}
            },
            timeout=10
        )
        logger.info(f"Meta response: {r.status_code} - {r.text}")
        r.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Error Meta enviando a {numero}: {e}")
        return False