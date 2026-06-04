"""
whatsapp_agent.py — Sere, agente de WhatsApp para Seremyc Sthetic
Flujo simplificado: botones/listas para navegación, formulario único para datos personales.
El LLM solo interviene para extraer datos del formulario y generar el resumen.
"""

import os
import json
import logging
import requests
from anthropic import Anthropic
from datetime import datetime, timedelta
from time import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

anthropic_client = Anthropic(
    api_key=os.getenv('ANTHROPIC_API_KEY')
)

_cache_servicios: dict = {'data': [], 'ts': 0.0}
_CACHE_TTL = 300
MAX_HISTORIAL = 10  # Reducido — el flujo es más corto ahora


# ══════════════════════════════════════════════════════════════════════════════
# INFRAESTRUCTURA
# ══════════════════════════════════════════════════════════════════════════════

def _base_url() -> str:
    return os.getenv('API_BASE_URL', 'http://localhost:5000')


def _headers() -> dict:
    return {
        'X-Agent-Key': os.getenv('AGENT_API_KEY'),
        'Content-Type': 'application/json'
    }


def _normalizar_numero(numero: str) -> str:
    return numero.replace('whatsapp:', '').strip()


# ══════════════════════════════════════════════════════════════════════════════
# PERSISTENCIA — HISTORIAL
# ══════════════════════════════════════════════════════════════════════════════

def _cargar_historial(phone: str) -> list[dict]:
    try:
        from infrastructure.database.db import db
        from sqlalchemy import text
        rows = db.session.execute(
            text("""
                SELECT role, content FROM conversation_history
                WHERE phone = :phone
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            {'phone': phone, 'limit': MAX_HISTORIAL}
        ).fetchall()
        return [{'role': r[0], 'content': r[1]} for r in reversed(rows)]
    except Exception as e:
        logger.error(f"Error cargando historial {phone}: {e}")
        return []


def _guardar_mensaje(phone: str, role: str, content: str) -> None:
    try:
        from infrastructure.database.db import db
        from sqlalchemy import text
        db.session.execute(
            text("""
                INSERT INTO conversation_history (phone, role, content)
                VALUES (:phone, :role, :content)
            """),
            {'phone': phone, 'role': role, 'content': content}
        )
        db.session.commit()
    except Exception as e:
        logger.error(f"Error guardando mensaje {phone}: {e}")


def _limpiar_historial(phone: str) -> None:
    try:
        from infrastructure.database.db import db
        from sqlalchemy import text
        db.session.execute(
            text("DELETE FROM conversation_history WHERE phone = :phone"),
            {'phone': phone}
        )
        db.session.commit()
    except Exception as e:
        logger.error(f"Error limpiando historial {phone}: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# PERSISTENCIA — ESTADO DE SESIÓN
# ══════════════════════════════════════════════════════════════════════════════

def _cargar_estado(phone: str) -> dict:
    try:
        from infrastructure.database.db import db
        from sqlalchemy import text
        row = db.session.execute(
            text("SELECT * FROM conversation_state WHERE phone = :phone"),
            {'phone': phone}
        ).fetchone()
        return dict(row._mapping) if row else {}
    except Exception as e:
        logger.error(f"Error cargando estado {phone}: {e}")
        return {}


def _guardar_estado(phone: str, **kwargs) -> None:
    try:
        from infrastructure.database.db import db
        from sqlalchemy import text
        if not kwargs:
            return
        cols         = ', '.join(kwargs.keys())
        updates      = ', '.join(f"{k} = :{k}" for k in kwargs)
        placeholders = ', '.join(f":{k}" for k in kwargs)
        db.session.execute(
            text(f"""
                INSERT INTO conversation_state (phone, {cols}, updated_at)
                VALUES (:phone, {placeholders}, NOW())
                ON CONFLICT (phone) DO UPDATE
                SET {updates}, updated_at = NOW()
            """),
            {'phone': phone, **kwargs}
        )
        db.session.commit()
    except Exception as e:
        logger.error(f"Error guardando estado {phone}: {e}")


def _limpiar_estado(phone: str) -> None:
    try:
        from infrastructure.database.db import db
        from sqlalchemy import text
        db.session.execute(
            text("DELETE FROM conversation_state WHERE phone = :phone"),
            {'phone': phone}
        )
        db.session.commit()
    except Exception as e:
        logger.error(f"Error limpiando estado {phone}: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# SERVICIOS
# ══════════════════════════════════════════════════════════════════════════════

def _obtener_servicios_raw() -> list:
    if time() - _cache_servicios['ts'] < _CACHE_TTL and _cache_servicios['data']:
        return _cache_servicios['data']
    try:
        r = requests.get(f'{_base_url()}/api/agent/services', headers=_headers(), timeout=5)
        r.raise_for_status()
        data = r.json()
        _cache_servicios['data'] = data
        _cache_servicios['ts']   = time()
        return data
    except Exception as e:
        logger.error(f"Error obteniendo servicios: {e}")
        return _cache_servicios['data']


def _servicios_de_categoria(categoria: str, servicios_raw: list) -> list:
    return [s for s in servicios_raw if s.get('category', '').lower().strip() == categoria]


# ══════════════════════════════════════════════════════════════════════════════
# DISPONIBILIDAD
# ══════════════════════════════════════════════════════════════════════════════

def _slots_disponibles(fecha: str) -> list[str]:
    try:
        r = requests.get(
            f'{_base_url()}/api/agent/availability',
            params={'date': fecha},
            headers=_headers(),
            timeout=5
        )
        r.raise_for_status()
        return [s['label'] for s in r.json().get('available', [])]
    except Exception as e:
        logger.error(f"Error obteniendo slots {fecha}: {e}")
        return []


def _verificar_disponibilidad(fecha_cita: str) -> bool:
    try:
        dt    = datetime.fromisoformat(fecha_cita)
        slots = _slots_disponibles(dt.strftime('%Y-%m-%d'))
        return dt.strftime('%H:00') in slots
    except Exception as e:
        logger.error(f"Error verificando disponibilidad: {e}")
        return True


def _fecha_legible(fecha: str) -> str:
    try:
        dt    = datetime.strptime(fecha, '%Y-%m-%d')
        dias  = ['lunes','martes','miércoles','jueves','viernes','sábado','domingo']
        meses = ['enero','febrero','marzo','abril','mayo','junio',
                 'julio','agosto','septiembre','octubre','noviembre','diciembre']
        return f"{dias[dt.weekday()]} {dt.day} de {meses[dt.month-1]} de {dt.year}"
    except Exception:
        return fecha


def _parsear_fecha_natural(texto: str) -> str | None:
    """Convierte texto como 'mañana', '6 de junio', 'el viernes' a YYYY-MM-DD."""
    hoy = datetime.now().date()
    t   = texto.lower().strip()

    if 'mañana' in t:
        return (hoy + timedelta(days=1)).strftime('%Y-%m-%d')

    if 'pasado mañana' in t:
        return (hoy + timedelta(days=2)).strftime('%Y-%m-%d')

    dias_semana = ['lunes','martes','miércoles','jueves','viernes','sábado','domingo']
    for i, dia in enumerate(dias_semana):
        if dia in t:
            dias_hasta = (i - hoy.weekday()) % 7 or 7
            return (hoy + timedelta(days=dias_hasta)).strftime('%Y-%m-%d')

    meses = {
        'enero':1,'febrero':2,'marzo':3,'abril':4,'mayo':5,'junio':6,
        'julio':7,'agosto':8,'septiembre':9,'octubre':10,'noviembre':11,'diciembre':12
    }
    for nombre_mes, num_mes in meses.items():
        if nombre_mes in t:
            import re
            nums = re.findall(r'\d+', t)
            if nums:
                dia_num = int(nums[0])
                año     = hoy.year
                try:
                    fecha = datetime(año, num_mes, dia_num).date()
                    if fecha < hoy:
                        fecha = datetime(año + 1, num_mes, dia_num).date()
                    return fecha.strftime('%Y-%m-%d')
                except ValueError:
                    pass

    # Intentar parsear formato DD/MM/YYYY o YYYY-MM-DD
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y'):
        try:
            return datetime.strptime(texto.strip(), fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue

    return None


# ══════════════════════════════════════════════════════════════════════════════
# MENSAJES INTERACTIVOS
# ══════════════════════════════════════════════════════════════════════════════

MAPA_CAT = {
    'cat_facial':        'facial',
    'cat_corporal':      'corporal',
    'cat_capilar':       'capilar',
    'cat_sueroterapia':  'sueroterapia',
    'cat_masaje':        'masaje',
}

EMOJIS_CAT = {
    'facial': '🌸', 'corporal': '💆', 'capilar': '💇',
    'sueroterapia': '💉', 'masaje': '🤲'
}


def _enviar_menu_categorias(phone: str) -> None:
    from infrastructure.web.whatsapp_sender import enviar_botones
    enviar_botones(
        phone,
        "¿Qué tipo de servicio te interesa? 🌸",
        [
            {'id': 'cat_facial',   'title': '🌸 Facial'},
            {'id': 'cat_corporal', 'title': '💆 Corporal'},
            {'id': 'cat_capilar',  'title': '💇 Capilar'},
        ]
    )
    enviar_botones(
        phone,
        "¿O prefieres?",
        [
            {'id': 'cat_sueroterapia', 'title': '💉 Sueroterapia'},
            {'id': 'cat_masaje',       'title': '🤲 Masaje'},
        ]
    )


def _enviar_menu_servicios(phone: str, categoria: str, servicios: list) -> None:
    from infrastructure.web.whatsapp_sender import enviar_lista, enviar_mensaje
    if not servicios:
        enviar_mensaje(phone, f"No hay servicios de {categoria} disponibles 😔\n¿Te interesa otra categoría? 🌸")
        _enviar_menu_categorias(phone)
        return
    emoji = EMOJIS_CAT.get(categoria, '✨')
    rows  = []
    for s in servicios:
        mins = s['duration_minutes']
        dur  = f"{mins//60}h {mins%60:02d}min" if mins >= 60 else f"{mins}min"
        rows.append({
            'id':          f"svc_{s['id']}",
            'title':       s['name'][:24],
            'description': f"{dur} · ${float(s['price']):,.0f}"
        })
    enviar_lista(
        phone,
        texto=f"{emoji} *Servicios de {categoria.capitalize()}:*\n\nElige el que te interesa 👇",
        boton_label="Ver servicios",
        secciones=[{'title': categoria.capitalize(), 'rows': rows}]
    )


def _enviar_confirmacion_servicio(phone: str, servicio: dict) -> None:
    from infrastructure.web.whatsapp_sender import enviar_botones
    mins = servicio['duration_minutes']
    dur  = f"{mins//60}h {mins%60:02d}min" if mins >= 60 else f"{mins}min"
    enviar_botones(
        phone,
        f"¿Confirmás que querés agendar *{servicio['name']}*? 😊\n\n💰 ${float(servicio['price']):,.0f} · ⏱ {dur}",
        [
            {'id': 'confirmar_servicio', 'title': '✅ Sí, agendar'},
            {'id': 'cancelar_servicio',  'title': '❌ No, volver'},
        ]
    )


def _enviar_solicitud_fecha(phone: str) -> None:
    from infrastructure.web.whatsapp_sender import enviar_mensaje
    enviar_mensaje(
        phone,
        "📅 ¿Qué día te gustaría venir?\n\n"
        "Puedes escribir por ejemplo:\n"
        "• _mañana_\n"
        "• _el viernes_\n"
        "• _6 de junio_"
    )


def _enviar_menu_horarios(phone: str, fecha: str, slots: list[str]) -> None:
    from infrastructure.web.whatsapp_sender import enviar_lista, enviar_mensaje
    if not slots:
        enviar_mensaje(
            phone,
            f"😔 No hay horarios disponibles para el {_fecha_legible(fecha)}.\n"
            f"¿Te gustaría elegir otro día? 🗓"
        )
        _guardar_estado(phone, pending_date=None, current_step='eligiendo_fecha')
        _enviar_solicitud_fecha(phone)
        return
    rows = [
        {
            'id':          f"hora_{h.replace(':', '')}",
            'title':       h,
            'description': _fecha_legible(fecha)
        }
        for h in slots[:10]
    ]
    enviar_lista(
        phone,
        texto=f"📅 *Horarios disponibles — {_fecha_legible(fecha)}:*\n\nElige el que te quede mejor 👇",
        boton_label="Ver horarios",
        secciones=[{'title': 'Horarios disponibles', 'rows': rows}]
    )


def _enviar_formulario_datos(phone: str) -> None:
    from infrastructure.web.whatsapp_sender import enviar_mensaje
    enviar_mensaje(
        phone,
        "📋 *Necesito algunos datos para tu cita.*\n\n"
        "Por favor responde con tu información así:\n\n"
        "Nombre: \n"
        "Correo: \n"
        "Nacimiento: (DD/MM/AAAA)\n"
        "Dirección: \n"
        "Tipo de piel: (normal/seca/mixta/grasa/sensible)\n"
        "Alergias: (o escribe _ninguna_)\n"
        "Observaciones: (o escribe _ninguna_)"
    )


def _enviar_confirmacion_final(phone: str, estado: dict, datos: dict) -> None:
    from infrastructure.web.whatsapp_sender import enviar_botones

    try:
        dt    = datetime.fromisoformat(estado['pending_datetime'])
        dias  = ['lunes','martes','miércoles','jueves','viernes','sábado','domingo']
        meses = ['enero','febrero','marzo','abril','mayo','junio',
                 'julio','agosto','septiembre','octubre','noviembre','diciembre']
        fecha_hora = f"{dias[dt.weekday()]} {dt.day} de {meses[dt.month-1]} a las {dt.strftime('%H:%M')}"
    except Exception:
        fecha_hora = estado.get('pending_datetime', '')

    mins = estado.get('selected_service_duration', 0)
    dur  = f"{mins//60}h {mins%60:02d}min" if mins >= 60 else f"{mins}min"

    resumen = (
        f"📋 *Resumen de tu cita:*\n\n"
        f"👤 {datos.get('nombre', '')}\n"
        f"📧 {datos.get('correo', '')}\n"
        f"🎂 {datos.get('nacimiento', '')}\n"
        f"🏠 {datos.get('direccion', '')}\n"
        f"🧴 Piel: {datos.get('tipo_piel', '')} · Alergias: {datos.get('alergias', '')}\n"
        f"📝 {datos.get('observaciones', '')}\n\n"
        f"💆 *{estado.get('selected_service_name', '')}*\n"
        f"📅 {fecha_hora}\n"
        f"💰 ${float(estado.get('selected_service_price', 0)):,.0f} · ⏱ {dur}\n\n"
        f"¿Todo correcto? ✅"
    )

    enviar_botones(
        phone,
        resumen,
        [
            {'id': 'agendar_confirmar', 'title': '✅ Confirmar cita'},
            {'id': 'agendar_cancelar',  'title': '❌ Cancelar'},
        ]
    )


# ══════════════════════════════════════════════════════════════════════════════
# EXTRACCIÓN DE DATOS DEL FORMULARIO (único uso del LLM en el flujo)
# ══════════════════════════════════════════════════════════════════════════════

SYSTEM_EXTRACTOR = """Eres un extractor de datos. El usuario envió un formulario con sus datos personales.
Extrae exactamente los campos y devuelve SOLO un JSON válido, sin texto adicional, sin markdown.

Formato esperado:
{
  "nombre": "...",
  "correo": "...",
  "nacimiento": "DD/MM/YYYY",
  "direccion": "...",
  "tipo_piel": "...",
  "alergias": "...",
  "observaciones": "..."
}

Reglas:
- Copia los valores EXACTAMENTE como los escribió el usuario, sin corregir ni cambiar nada.
- Si un campo dice "ninguna" o está vacío, ponlo como "ninguna".
- La fecha de nacimiento debe estar en formato DD/MM/YYYY. Si el usuario escribió "4 de marzo de 1973", conviértela a "04/03/1973".
- Devuelve SOLO el JSON, nada más."""


def _extraer_datos_formulario(texto: str) -> dict | None:
    """Usa el LLM para extraer los campos del formulario enviado por el cliente."""
    try:
        respuesta = anthropic_client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=300,
            system=SYSTEM_EXTRACTOR,
            messages=[
                {
                    "role": "user",
                    "content": texto
                }
            ]
        )

        contenido = respuesta.content[0].text.strip()
        # Limpiar posibles backticks
        contenido = contenido.replace('```json', '').replace('```', '').strip()
        datos = json.loads(contenido)
        # Validar que tiene los campos mínimos
        if datos.get('nombre') and datos.get('correo'):
            return datos
        return None
    except Exception as e:
        logger.error(f"Error extrayendo datos formulario: {e}")
        return None


def _parece_formulario(texto: str) -> bool:
    """Detecta si el mensaje del cliente parece ser el formulario rellenado."""
    campos = ['nombre:', 'correo:', 'nacimiento:', 'dirección:', 'direccion:',
              'tipo de piel:', 'alergias:', 'observaciones:']
    texto_lower = texto.lower()
    coincidencias = sum(1 for c in campos if c in texto_lower)
    return coincidencias >= 3


# ══════════════════════════════════════════════════════════════════════════════
# AGENDAMIENTO
# ══════════════════════════════════════════════════════════════════════════════

def _agendar_cita(phone: str, estado: dict, datos: dict) -> str:
    try:
        fecha_cita = estado['pending_datetime']

        if not _verificar_disponibilidad(fecha_cita):
            dt    = datetime.fromisoformat(fecha_cita)
            slots = _slots_disponibles(dt.strftime('%Y-%m-%d'))
            from infrastructure.web.whatsapp_sender import enviar_mensaje
            enviar_mensaje(phone, f"😔 El horario {dt.strftime('%H:00')} ya está ocupado. Te muestro los disponibles:")
            _enviar_menu_horarios(phone, dt.strftime('%Y-%m-%d'), slots)
            _guardar_estado(phone, current_step='eligiendo_horario', pending_datetime=None)
            return ''

        # Crear cliente
        r_cliente = requests.post(
            f'{_base_url()}/api/agent/clients',
            json={
                'full_name':    datos['nombre'],
                'phone':        _normalizar_numero(phone),
                'email':        datos.get('correo', ''),
                'birth_date':   datos.get('nacimiento', ''),
                'address':      datos.get('direccion', ''),
                'skin_type':    datos.get('tipo_piel', ''),
                'allergies':    datos.get('alergias', ''),
                'observations': datos.get('observaciones', '')
            },
            headers=_headers(),
            timeout=10
        )
        r_cliente.raise_for_status()
        cliente_id = r_cliente.json()['client_id']

        # Crear cita
        r_cita = requests.post(
            f'{_base_url()}/api/agent/appointments',
            json={
                'client_id':    cliente_id,
                'service_id':   estado['selected_service_id'],
                'scheduled_at': fecha_cita,
                'observations': datos.get('observaciones', '')
            },
            headers=_headers(),
            timeout=10
        )
        r_cita.raise_for_status()
        cita = r_cita.json()

        try:
            dt    = datetime.fromisoformat(fecha_cita)
            dias  = ['lunes','martes','miércoles','jueves','viernes','sábado','domingo']
            meses = ['enero','febrero','marzo','abril','mayo','junio',
                     'julio','agosto','septiembre','octubre','noviembre','diciembre']
            fecha_fmt = f"{dias[dt.weekday()]} {dt.day} de {meses[dt.month-1]} de {dt.year} a las {dt.strftime('%H:%M')}"
        except Exception:
            fecha_fmt = fecha_cita

        confirmacion = (
            f"✅ *¡Tu cita está confirmada!* 🎉\n\n"
            f"👤 {cita['client']}\n"
            f"💆 {cita['service']}\n"
            f"📅 {fecha_fmt}\n"
            f"💰 ${float(cita['price']):,.0f}\n\n"
            f"¡Te esperamos con mucho cariño en Seremyc Sthetic! 💜"
        )

        _limpiar_historial(phone)
        _limpiar_estado(phone)
        return confirmacion

    except Exception as e:
        logger.error(f"Error agendando cita {phone}: {e}")
        return "Ocurrió un error al agendar 😔\nEscribe asesor para que te ayude una de nosotras 💜"


# ══════════════════════════════════════════════════════════════════════════════
# ASESOR
# ══════════════════════════════════════════════════════════════════════════════

def _manejar_asesor(numero: str) -> str:
    numero_asesor = os.getenv('ASESOR_WHATSAPP', '')
    if numero_asesor:
        return (
            f"¡Claro! 😊 Te conecto con una de nuestras asesoras.\n\n"
            f"📲 Escríbenos: wa.me/{numero_asesor}\n\n"
            f"También puedo seguir ayudándote por aquí 💜"
        )
    return "¡Por supuesto! 😊 Una de nuestras asesoras te atenderá pronto 💜"


# ══════════════════════════════════════════════════════════════════════════════
# FUNCIÓN PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def procesar_mensaje(numero: str, mensaje: str) -> str:
    """
    Retorna string con el mensaje a enviar, o '' si ya se envió un interactivo.
    """
    phone         = _normalizar_numero(numero)
    mensaje_lower = mensaje.lower().strip()

    # ── Solicitud de asesor ──────────────────────────────────────────────────
    palabras_asesor = ['asesor', 'asesora', 'humano', 'persona real',
                       'hablar con alguien', 'agente', 'representante']
    if any(p in mensaje_lower for p in palabras_asesor):
        return _manejar_asesor(phone)

    servicios_raw = _obtener_servicios_raw()
    estado        = _cargar_estado(phone)
    paso_actual   = estado.get('current_step', 'inicio')

    # ══════════════════════════════════════════════════════════════════════════
    # PASO 1 — BIENVENIDA
    # ══════════════════════════════════════════════════════════════════════════
    if paso_actual == 'inicio':
        # Verificar si es cliente conocido
        nombre_saludo = ''
        try:
            r = requests.get(
                f'{_base_url()}/api/agent/client-history',
                params={'phone': phone},
                headers=_headers(),
                timeout=5
            )
            data = r.json()
            if data.get('exists'):
                nombre_saludo = data['full_name'].split()[0]
        except Exception:
            pass

        saludo = (
            f"¡Hola {nombre_saludo}! 😊 Bienvenida a Seremyc Sthetic 💜"
            if nombre_saludo
            else "¡Hola! 😊 Bienvenida a Seremyc Sthetic 💜\nSoy Sere, tu asistente virtual 🌸"
        )

        from infrastructure.web.whatsapp_sender import enviar_mensaje
        enviar_mensaje(phone, saludo)
        _guardar_estado(phone, current_step='eligiendo_categoria')
        _enviar_menu_categorias(phone)
        return ''

    # ══════════════════════════════════════════════════════════════════════════
    # PASO 2 — SELECCIÓN DE CATEGORÍA
    # ══════════════════════════════════════════════════════════════════════════
    if paso_actual == 'eligiendo_categoria' and mensaje_lower in MAPA_CAT:
        categoria     = MAPA_CAT[mensaje_lower]
        servicios_cat = _servicios_de_categoria(categoria, servicios_raw)
        _guardar_estado(phone,
                        selected_category=categoria,
                        current_step='eligiendo_servicio')
        _enviar_menu_servicios(phone, categoria, servicios_cat)
        return ''

    # ══════════════════════════════════════════════════════════════════════════
    # PASO 3 — SELECCIÓN DE SERVICIO
    # ══════════════════════════════════════════════════════════════════════════
    if paso_actual == 'eligiendo_servicio' and mensaje_lower.startswith('svc_'):
        try:
            svc_id   = int(mensaje_lower.replace('svc_', ''))
            servicio = next((s for s in servicios_raw if s['id'] == svc_id), None)
            if servicio:
                _guardar_estado(phone,
                                selected_service_id=servicio['id'],
                                selected_service_name=servicio['name'],
                                selected_service_price=float(servicio['price']),
                                selected_service_duration=servicio['duration_minutes'],
                                current_step='confirmando_servicio')
                _enviar_confirmacion_servicio(phone, servicio)
                return ''
        except Exception as e:
            logger.error(f"Error seleccionando servicio: {e}")

    # ══════════════════════════════════════════════════════════════════════════
    # PASO 4 — CONFIRMAR SERVICIO
    # ══════════════════════════════════════════════════════════════════════════
    if paso_actual == 'confirmando_servicio':
        if mensaje_lower == 'confirmar_servicio':
            _guardar_estado(phone, current_step='eligiendo_fecha')
            _enviar_solicitud_fecha(phone)
            return ''

        if mensaje_lower == 'cancelar_servicio':
            _limpiar_estado(phone)
            _limpiar_historial(phone)
            _guardar_estado(phone, current_step='eligiendo_categoria')
            _enviar_menu_categorias(phone)
            return ''

    # ══════════════════════════════════════════════════════════════════════════
    # PASO 5 — SELECCIÓN DE FECHA
    # ══════════════════════════════════════════════════════════════════════════
    if paso_actual == 'eligiendo_fecha':
        fecha = _parsear_fecha_natural(mensaje)
        if fecha:
            slots = _slots_disponibles(fecha)
            _guardar_estado(phone, pending_date=fecha, current_step='eligiendo_horario')
            _enviar_menu_horarios(phone, fecha, slots)
            return ''
        else:
            from infrastructure.web.whatsapp_sender import enviar_mensaje
            enviar_mensaje(
                phone,
                "No entendí la fecha 😔 ¿Puedes escribirla así?\n\n"
                "• _mañana_\n• _el viernes_\n• _6 de junio_"
            )
            return ''

    # ══════════════════════════════════════════════════════════════════════════
    # PASO 6 — SELECCIÓN DE HORARIO
    # ══════════════════════════════════════════════════════════════════════════
    if paso_actual == 'eligiendo_horario' and mensaje_lower.startswith('hora_'):
        hora_str      = mensaje_lower.replace('hora_', '')       # '0800'
        hora_fmt      = f"{hora_str[:2]}:{hora_str[2:]}:00"      # '08:00:00'
        fecha         = estado.get('pending_date', '')
        pending_dt    = f"{fecha}T{hora_fmt}"
        _guardar_estado(phone,
                        pending_datetime=pending_dt,
                        current_step='llenando_datos')
        _enviar_formulario_datos(phone)
        return ''

    # ══════════════════════════════════════════════════════════════════════════
    # PASO 7 — FORMULARIO DE DATOS PERSONALES
    # ══════════════════════════════════════════════════════════════════════════
    if paso_actual == 'llenando_datos':
        if _parece_formulario(mensaje):
            datos = _extraer_datos_formulario(mensaje)
            if datos:
                # Guardar datos en el estado
                _guardar_estado(
                    phone,
                    collected_data=json.dumps(datos),
                    current_step='confirmando_cita'
                )
                estado_actualizado = _cargar_estado(phone)
                _enviar_confirmacion_final(phone, estado_actualizado, datos)
                return ''
            else:
                from infrastructure.web.whatsapp_sender import enviar_mensaje
                enviar_mensaje(
                    phone,
                    "No pude leer tus datos 😔 Por favor asegúrate de incluir al menos Nombre y Correo."
                )
                _enviar_formulario_datos(phone)
                return ''
        else:
            # El cliente escribió algo que no es el formulario
            from infrastructure.web.whatsapp_sender import enviar_mensaje
            enviar_mensaje(
                phone,
                "Por favor completa el formulario con tus datos 😊\nRecuerda incluir todos los campos:"
            )
            _enviar_formulario_datos(phone)
            return ''

    # ══════════════════════════════════════════════════════════════════════════
    # PASO 8 — CONFIRMACIÓN FINAL
    # ══════════════════════════════════════════════════════════════════════════
    if paso_actual == 'confirmando_cita':
        if mensaje_lower == 'agendar_confirmar':
            datos = json.loads(
                estado.get('collected_data', '{}')
            )
            return _agendar_cita(phone, estado, datos)

        if mensaje_lower == 'agendar_cancelar':
            _limpiar_estado(phone)
            _limpiar_historial(phone)
            from infrastructure.web.whatsapp_sender import enviar_mensaje
            enviar_mensaje(phone, "Entendido 😊 Cuando quieras agendar, aquí estaré 🌸")
            return ''

    # ══════════════════════════════════════════════════════════════════════════
    # FALLBACK — mensaje fuera de flujo
    # ══════════════════════════════════════════════════════════════════════════
    from infrastructure.web.whatsapp_sender import enviar_mensaje
    enviar_mensaje(
        phone,
        "¡Hola! 😊 Soy Sere, asistente de Seremyc Sthetic 💜\n"
        "¿En qué puedo ayudarte hoy?"
    )
    _guardar_estado(phone, current_step='eligiendo_categoria')
    _enviar_menu_categorias(phone)
    return ''