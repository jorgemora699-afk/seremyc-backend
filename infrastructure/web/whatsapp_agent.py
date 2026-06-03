"""
whatsapp_agent.py — Sere, agente de WhatsApp para Seremyc Sthetic
Versión con mensajes interactivos (botones y listas) para evitar ambigüedad.
"""

import os
import json
import logging
import requests
from groq import Groq
from datetime import datetime
from time import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

groq_client = Groq(api_key=os.getenv('GROQ_API_KEY'))

_cache_servicios: dict = {'data': [], 'ts': 0.0}
_CACHE_TTL = 300

MAX_HISTORIAL = 24
CATEGORIAS = ['facial', 'corporal', 'capilar', 'sueroterapia', 'masaje']


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS DE INFRAESTRUCTURA
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
        r = requests.get(
            f'{_base_url()}/api/agent/services',
            headers=_headers(),
            timeout=5
        )
        r.raise_for_status()
        data = r.json()
        _cache_servicios['data'] = data
        _cache_servicios['ts']   = time()
        return data
    except Exception as e:
        logger.error(f"Error obteniendo servicios: {e}")
        return _cache_servicios['data']


def _obtener_servicios_texto(servicios_raw: list) -> str:
    if not servicios_raw:
        return "Servicios: consultar con asesora."
    categorias: dict[str, list] = {}
    for s in servicios_raw:
        cat  = s.get('category', 'otro').lower().strip()
        mins = s['duration_minutes']
        dur  = f"{mins//60}h{mins%60:02d}m" if mins >= 60 else f"{mins}min"
        categorias.setdefault(cat, []).append(
            f"  [{s['id']}] {s['name']} · {dur} · ${float(s['price']):,.0f}"
        )
    texto = "CATÁLOGO DE SERVICIOS (ID | Nombre | Duración | Precio):\n"
    for cat, items in categorias.items():
        texto += f"\n{cat.upper()}:\n" + "\n".join(items) + "\n"
    return texto


def _servicios_de_categoria(categoria: str, servicios_raw: list) -> list:
    return [
        s for s in servicios_raw
        if s.get('category', '').lower().strip() == categoria
    ]


# ══════════════════════════════════════════════════════════════════════════════
# MENSAJES INTERACTIVOS
# ══════════════════════════════════════════════════════════════════════════════

def _enviar_menu_categorias(phone: str) -> None:
    """Menú principal con botones de categoría — se envía en dos tandas por límite de 3."""
    from infrastructure.web.whatsapp_sender import enviar_botones, enviar_lista

    # Primera fila: 3 categorías
    enviar_botones(
        phone,
        "¿Qué tipo de servicio te interesa? 🌸",
        [
            {'id': 'cat_facial',      'title': '🌸 Facial'},
            {'id': 'cat_corporal',    'title': '💆 Corporal'},
            {'id': 'cat_capilar',     'title': '💇 Capilar'},
        ]
    )
    # Segunda fila: 2 categorías restantes
    enviar_botones(
        phone,
        "O elige:",
        [
            {'id': 'cat_sueroterapia', 'title': '💉 Sueroterapia'},
            {'id': 'cat_masaje',       'title': '🤲 Masaje'},
        ]
    )


def _enviar_menu_servicios(phone: str, categoria: str, servicios: list) -> None:
    """Lista de servicios de una categoría."""
    from infrastructure.web.whatsapp_sender import enviar_lista

    if not servicios:
        from infrastructure.web.whatsapp_sender import enviar_mensaje
        enviar_mensaje(phone, f"No encontré servicios de {categoria} disponibles 😔\n¿Te interesa otra categoría? 🌸")
        return

    rows = []
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
        texto=f"🌸 *Servicios de {categoria.capitalize()}:*\n\nElige el que te interesa 👇",
        boton_label="Ver servicios",
        secciones=[{'title': categoria.capitalize(), 'rows': rows}]
    )


def _enviar_confirmacion_servicio(phone: str, servicio: dict) -> None:
    """Botones Sí/No para confirmar el servicio."""
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


def _enviar_menu_horarios(phone: str, fecha: str, slots: list[str]) -> None:
    """Lista de horarios disponibles."""
    from infrastructure.web.whatsapp_sender import enviar_lista, enviar_mensaje

    try:
        dt     = datetime.strptime(fecha, '%Y-%m-%d')
        dias   = ['lunes','martes','miércoles','jueves','viernes','sábado','domingo']
        meses  = ['enero','febrero','marzo','abril','mayo','junio',
                  'julio','agosto','septiembre','octubre','noviembre','diciembre']
        fecha_legible = f"{dias[dt.weekday()]} {dt.day} de {meses[dt.month-1]} de {dt.year}"
    except ValueError:
        fecha_legible = fecha

    if not slots:
        enviar_mensaje(phone, f"😔 No hay horarios disponibles para el {fecha_legible}.\n¿Te gustaría elegir otro día? 🗓")
        return

    rows = [
        {'id': f"hora_{h.replace(':', '')}", 'title': h, 'description': fecha_legible}
        for h in slots
    ]

    enviar_lista(
        phone,
        texto=f"📅 *Horarios disponibles — {fecha_legible}:*\n\nElige el que te quede mejor 👇",
        boton_label="Ver horarios",
        secciones=[{'title': 'Horarios disponibles', 'rows': rows}]
    )


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
        logger.error(f"Error obteniendo slots para {fecha}: {e}")
        return []


def _verificar_disponibilidad(fecha_cita: str) -> bool:
    try:
        dt   = datetime.fromisoformat(fecha_cita)
        slots = _slots_disponibles(dt.strftime('%Y-%m-%d'))
        return dt.strftime('%H:00') in slots
    except Exception as e:
        logger.error(f"Error verificando disponibilidad: {e}")
        return True


# ══════════════════════════════════════════════════════════════════════════════
# SYSTEM PROMPT
# ══════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """Eres Sere, asistente virtual de Seremyc Sthetic 💜 — centro de bienestar y estética.

═══ PERSONALIDAD ═══
- Cálida, empática y profesional. Como una amiga experta en bienestar.
- Mensajes cortos (máx 120 palabras). Uno o dos emojis por mensaje.
- Siempre en español colombiano. Natural, nunca robótica.

═══ REGLAS ABSOLUTAS ═══
1. JAMÁS muestres los tokens CONSULTAR_DISPONIBILIDAD ni AGENDAR_CITA al cliente.
2. JAMÁS inventes horarios, fechas, precios ni datos del cliente.
3. JAMÁS cambies ni "corrijas" datos que el cliente proporcionó — guárdalos exactamente.
4. NUNCA repitas preguntas que ya hiciste en esta conversación.
5. Si hay un [CTX:SERVICIO_SELECCIONADO] en el historial, ese ES el servicio. No preguntes de nuevo.
6. Cuando detectes el día deseado, emite SOLO: CONSULTAR_DISPONIBILIDAD:{"fecha":"YYYY-MM-DD"}
7. Solo cuando el cliente confirme todos los datos, emite SOLO: AGENDAR_CITA:{...json...}
8. Si el cliente pide hablar con una persona: responde SOLO "CONTACTAR_ASESOR"
9. NO muestres menús de categorías ni servicios — el sistema los envía como botones interactivos.

═══ FECHAS ═══
Hoy: {fecha_actual}
- Fechas de nacimiento → DD/MM/YYYY
- Fechas de cita → YYYY-MM-DDTHH:MM:00
- Interpreta: "mañana", "el viernes", "la próxima semana", etc.

═══ FLUJO ═══

[PASO 1 — BIENVENIDA]
Saluda brevemente. El sistema ya envía el menú de categorías como botones.

[PASO 2 — CONFIRMAR SERVICIO]
El sistema envía botones de confirmación. Espera "confirmar_servicio" antes de continuar.

[PASO 3 — RECOLECCIÓN DE DATOS]
Pide UNO por UNO (solo si no está ya en el historial):
① Nombre completo
② Correo electrónico
③ Fecha de nacimiento (DD/MM/YYYY)
④ Dirección
⑤ Tipo de piel (normal/seca/mixta/grasa/sensible)
⑥ Alergias (o "ninguna")
⑦ Observaciones para el terapeuta (o "ninguna")
⑧ Día deseado → emite CONSULTAR_DISPONIBILIDAD:{"fecha":"YYYY-MM-DD"}
⑨ El sistema muestra horarios como lista interactiva. Cuando el cliente elija, recibirás "hora_HHMM".

[PASO 4 — RESUMEN]
"📋 *Resumen de tu cita:*
👤 [nombre] · 📧 [correo] · 🎂 [nacimiento]
🏠 [dirección] · 🧴 Piel: [tipo] · Alergias: [alergias]
📝 [observaciones]
💆 [servicio] · 📅 [fecha y hora] · 💰 $[precio]
¿Todo correcto? ✅"

[PASO 5 — AGENDAR]
Solo si confirma:
AGENDAR_CITA:{"nombre":"...","correo":"...","fecha_nacimiento":"DD/MM/YYYY","direccion":"...","tipo_piel":"...","alergias":"...","observaciones":"...","servicio_id":ID,"fecha_cita":"YYYY-MM-DDTHH:MM:00"}

═══ SERVICIOS ═══
{servicios}"""


def _construir_system(servicios_raw: list) -> str:
    fecha_actual   = datetime.now().strftime('%A %d de %B de %Y')
    servicios_texto = _obtener_servicios_texto(servicios_raw)
    return (
        SYSTEM_PROMPT
        .replace('{fecha_actual}', fecha_actual)
        .replace('{servicios}', servicios_texto)
    )


# ══════════════════════════════════════════════════════════════════════════════
# LLM
# ══════════════════════════════════════════════════════════════════════════════

def _llamar_llm(system: str, mensajes: list, max_tokens: int = 500) -> str:
    respuesta = groq_client.chat.completions.create(
        model='llama-3.3-70b-versatile',
        max_tokens=max_tokens,
        messages=[{'role': 'system', 'content': system}] + mensajes
    )
    return respuesta.choices[0].message.content


def _extraer_token(texto: str, token: str) -> str | None:
    if token not in texto:
        return None
    parte = texto.split(token)[1].strip()
    if parte.startswith('{'):
        depth = 0
        for i, ch in enumerate(parte):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return parte[:i+1]
    return parte.split('\n')[0].strip()


# ══════════════════════════════════════════════════════════════════════════════
# ACCIONES ESPECIALES
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


def _manejar_confirmacion_cita(numero: str, accion: str) -> str:
    try:
        phone = _normalizar_numero(numero)
        r     = requests.get(
            f'{_base_url()}/api/agent/client-history',
            params={'phone': phone},
            headers=_headers(),
            timeout=5
        )
        data = r.json()
        if not data.get('exists'):
            return "No encontré citas asociadas a tu número 😔\n¿Quieres agendar una nueva? 🌸"

        citas   = data.get('appointments', [])
        proxima = next((c for c in citas if c['status'] == 'confirmed'), None)
        if not proxima:
            return "No tienes citas confirmadas próximas 😔\n¿Quieres agendar una? 🌸"

        nombre = data['full_name'].split()[0]

        if accion == 'confirmar':
            return (
                f"✅ ¡Perfecto {nombre}! Tu cita está confirmada.\n\n"
                f"💆 {proxima['service']}\n📅 {proxima['scheduled_at']}\n\n"
                f"¡Te esperamos! 💜"
            )
        elif accion == 'cancelar':
            requests.patch(
                f'{_base_url()}/api/agent/appointments/{proxima["id"]}/cancel',
                headers=_headers(), timeout=10
            )
            return (
                f"Entendido {nombre}, cancelamos tu cita 😔\n\n"
                f"💆 {proxima['service']}\n📅 {proxima['scheduled_at']}\n\n"
                f"Cuando quieras reagendar, aquí estaré 🌸"
            )
        elif accion == 'reagendar':
            return f"¡Claro {nombre}! Vamos a reagendar tu *{proxima['service']}* 🗓\n\n¿Qué día te vendría mejor?"
    except Exception as e:
        logger.error(f"Error manejando acción {accion}: {e}")
        return "Hubo un error procesando tu solicitud 😔 Por favor contáctanos directamente."


def _guardar_calificacion(numero: str, calificacion: int) -> str | None:
    try:
        phone = _normalizar_numero(numero)
        r     = requests.get(
            f'{_base_url()}/api/agent/client-history',
            params={'phone': phone},
            headers=_headers(), timeout=5
        )
        data = r.json()
        if not data.get('exists'):
            return None
        cita_encuesta = next(
            (c for c in data.get('appointments', [])
             if c.get('survey_sent') and not c.get('survey_rating')),
            None
        )
        if not cita_encuesta:
            return None
        requests.patch(
            f'{_base_url()}/api/agent/appointments/{cita_encuesta["id"]}/survey',
            json={'rating': calificacion},
            headers=_headers(), timeout=10
        )
        nombre = data['full_name'].split()[0]
        if calificacion >= 4:
            return f"¡Gracias {nombre}! 🌟 Nos alegra saber que tuviste una gran experiencia.\n\n¿Quieres dejarnos algún comentario? 😊"
        return f"Gracias por tu honestidad {nombre} 🙏\n\n¿Qué podríamos hacer mejor para ti? 💜"
    except Exception as e:
        logger.error(f"Error guardando calificación: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# MANEJO DE DISPONIBILIDAD Y AGENDAMIENTO
# ══════════════════════════════════════════════════════════════════════════════

def _manejar_consulta_disponibilidad(phone: str, texto_llm: str) -> str:
    try:
        json_str = _extraer_token(texto_llm, 'CONSULTAR_DISPONIBILIDAD:')
        if not json_str:
            raise ValueError("Token no encontrado")
        datos = json.loads(json_str)
        fecha = datos['fecha']
    except Exception as e:
        logger.error(f"CONSULTAR_DISPONIBILIDAD malformado: {e}")
        msg = "Tuve un problema consultando la disponibilidad 😔 ¿Me repites el día que prefieres?"
        _guardar_mensaje(phone, 'assistant', msg)
        return msg

    slots = _slots_disponibles(fecha)
    _guardar_estado(phone, pending_date=fecha)

    # Enviar lista interactiva de horarios directamente
    _enviar_menu_horarios(phone, fecha, slots)

    # Guardar contexto para el LLM
    ctx = (
        f"[SISTEMA] Disponibilidad consultada para {fecha}. "
        f"Slots: {', '.join(slots) if slots else 'ninguno'}. "
        f"Se enviaron como lista interactiva al cliente."
    )
    _guardar_mensaje(phone, 'assistant', f"[Horarios enviados para {fecha}]")
    _guardar_mensaje(phone, 'user', ctx)
    return ''  # Ya se envió directamente


def _agendar_cita(phone: str, texto_llm: str) -> str:
    try:
        json_str = _extraer_token(texto_llm, 'AGENDAR_CITA:')
        if not json_str:
            raise ValueError("Token no encontrado")
        datos = json.loads(json_str)
        datos['servicio_id'] = int(datos['servicio_id'])

        if not _verificar_disponibilidad(datos['fecha_cita']):
            dt    = datetime.fromisoformat(datos['fecha_cita'])
            slots = _slots_disponibles(dt.strftime('%Y-%m-%d'))
            _enviar_menu_horarios(phone, dt.strftime('%Y-%m-%d'), slots)
            msg = f"😔 El horario {dt.strftime('%H:00')} ya está ocupado. Te muestro los disponibles:"
            _guardar_mensaje(phone, 'assistant', msg)
            return msg

        # Crear cliente
        r_cliente = requests.post(
            f'{_base_url()}/api/agent/clients',
            json={
                'full_name':    datos['nombre'],
                'phone':        _normalizar_numero(phone),
                'email':        datos.get('correo', ''),
                'birth_date':   datos.get('fecha_nacimiento', ''),
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
                'service_id':   datos['servicio_id'],
                'scheduled_at': datos['fecha_cita'],
                'observations': datos.get('observaciones', '')
            },
            headers=_headers(),
            timeout=10
        )
        r_cita.raise_for_status()
        cita = r_cita.json()

        try:
            dt    = datetime.fromisoformat(datos['fecha_cita'])
            dias  = ['lunes','martes','miércoles','jueves','viernes','sábado','domingo']
            meses = ['enero','febrero','marzo','abril','mayo','junio',
                     'julio','agosto','septiembre','octubre','noviembre','diciembre']
            fecha_legible = f"{dias[dt.weekday()]} {dt.day} de {meses[dt.month-1]} de {dt.year} a las {dt.strftime('%H:%M')}"
        except Exception:
            fecha_legible = datos['fecha_cita']

        confirmacion = (
            f"✅ *¡Tu cita está confirmada!* 🎉\n\n"
            f"👤 {cita['client']}\n"
            f"💆 {cita['service']}\n"
            f"📅 {fecha_legible}\n"
            f"💰 ${float(cita['price']):,.0f}\n\n"
            f"¡Te esperamos con mucho cariño en Seremyc Sthetic! 💜"
        )

        _limpiar_historial(phone)
        _limpiar_estado(phone)
        return confirmacion

    except json.JSONDecodeError as e:
        logger.error(f"JSON inválido AGENDAR_CITA: {e}")
        return "Hubo un problema procesando tu cita 😔 ¿Intentamos de nuevo?"
    except Exception as e:
        logger.error(f"Error agendando cita {phone}: {e}")
        return "Ocurrió un error al agendar 😔\nEscribe *asesor* para que te ayude una de nosotras 💜"


# ══════════════════════════════════════════════════════════════════════════════
# FUNCIÓN PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def procesar_mensaje(numero: str, mensaje: str) -> str:
    phone         = _normalizar_numero(numero)
    mensaje_lower = mensaje.lower().strip()

    # ── Acciones de gestión de cita ──────────────────────────────────────────
    if mensaje_lower in ['confirmar', 'cancelar', 'reagendar']:
        return _manejar_confirmacion_cita(phone, mensaje_lower)

    # ── Solicitud de asesor ──────────────────────────────────────────────────
    palabras_asesor = ['asesor', 'asesora', 'humano', 'persona real',
                       'hablar con alguien', 'agente', 'representante']
    if any(p in mensaje_lower for p in palabras_asesor):
        return 'CONTACTAR_ASESOR'

    # ── Calificación de encuesta ─────────────────────────────────────────────
    if mensaje_lower in ['1', '2', '3', '4', '5']:
        resultado = _guardar_calificacion(phone, int(mensaje_lower))
        if resultado:
            return resultado

    # ── Cargar estado ────────────────────────────────────────────────────────
    servicios_raw = _obtener_servicios_raw()
    estado        = _cargar_estado(phone)
    historial     = _cargar_historial(phone)

    # ── Selección de categoría ───────────────────────────────────────────────
    MAPA_CAT = {
        'cat_facial':       'facial',
        'cat_corporal':     'corporal',
        'cat_capilar':      'capilar',
        'cat_sueroterapia': 'sueroterapia',
        'cat_masaje':       'masaje',
    }

    if mensaje_lower in MAPA_CAT and not estado.get('selected_service_id'):
        categoria     = MAPA_CAT[mensaje_lower]
        servicios_cat = _servicios_de_categoria(categoria, servicios_raw)
        _guardar_estado(phone, selected_category=categoria, current_step='eligiendo_servicio')
        _guardar_mensaje(phone, 'user', f"[Categoría elegida: {categoria}]")
        _enviar_menu_servicios(phone, categoria, servicios_cat)
        return ''

    # ── Selección de servicio ────────────────────────────────────────────────
    if mensaje_lower.startswith('svc_') and not estado.get('selected_service_id'):
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
                _guardar_mensaje(phone, 'user', (
                    f"[CTX:SERVICIO_SELECCIONADO] "
                    f"Nombre: {servicio['name']} | ID: {servicio['id']} | "
                    f"Precio: ${float(servicio['price']):,.0f} | "
                    f"Duración: {servicio['duration_minutes']}min"
                ))
                _enviar_confirmacion_servicio(phone, servicio)
                return ''
        except Exception as e:
            logger.error(f"Error seleccionando servicio {mensaje}: {e}")

    # ── Confirmación/cancelación de servicio ─────────────────────────────────
    if mensaje_lower == 'cancelar_servicio':
        _limpiar_estado(phone)
        _limpiar_historial(phone)
        # Saluda de nuevo y muestra categorías
        from infrastructure.web.whatsapp_sender import enviar_mensaje
        enviar_mensaje(phone, "¡Sin problema! 😊 Volvamos a empezar 🌸")
        _enviar_menu_categorias(phone)
        return ''

    if mensaje_lower == 'confirmar_servicio':
        _guardar_estado(phone, current_step='recolectando_datos')
        _guardar_mensaje(phone, 'user', '[Cliente confirmó el servicio]')
        historial = _cargar_historial(phone)
        # Cae al LLM para que pida el primer dato

    # ── Selección de horario ──────────────────────────────────────────────────
    if mensaje_lower.startswith('hora_') and estado.get('pending_date'):
        hora_str = mensaje_lower.replace('hora_', '')
        hora_fmt = f"{hora_str[:2]}:{hora_str[2:]}"
        fecha_dt = f"{estado['pending_date']}T{hora_fmt}:00"
        _guardar_mensaje(phone, 'user', f"[CTX:HORARIO_ELEGIDO] Fecha y hora: {fecha_dt}")
        _guardar_estado(phone, pending_date=None, current_step='resumen')

    # ── Recargar estado antes de decidir si mostrar menú ─────────────────────
    estado = _cargar_estado(phone)  # ← AGREGAR ESTA LÍNEA

    # ── Si no hay servicio confirmado aún, saluda y muestra categorías ────────
    if not estado.get('selected_service_id') and estado.get('current_step') not in ['recolectando_datos', 'resumen']:
        saludo = "¡Hola! 😊 Bienvenida a Seremyc Sthetic 💜\n\n¿Qué tipo de servicio te interesa hoy?"
        try:
            r = requests.get(
                f'{_base_url()}/api/agent/client-history',
                params={'phone': phone},
                headers=_headers(),
                timeout=5
            )
            data_cliente = r.json()
            if data_cliente.get('exists'):
                nombre = data_cliente['full_name'].split()[0]
                saludo = f"¡Hola {nombre}! 😊 Qué gusto verte de nuevo 💜\n\n¿Qué te gustaría agendar hoy?"
        except Exception:
            pass

        from infrastructure.web.whatsapp_sender import enviar_mensaje
        _guardar_mensaje(phone, 'user', mensaje)
        _guardar_mensaje(phone, 'assistant', saludo)
        enviar_mensaje(phone, saludo)
        _enviar_menu_categorias(phone)
        return ''

    # ── Flujo LLM — solo para recolección de datos y agendamiento ────────────
    system = _construir_system(servicios_raw)

    if estado.get('selected_service_id'):
        mins = estado.get('selected_service_duration', 0)
        dur  = f"{mins//60}h {mins%60:02d}min" if mins >= 60 else f"{mins}min"
        system += (
            f"\n\n═══ SERVICIO ACTIVO ═══\n"
            f"El cliente ya eligió: *{estado['selected_service_name']}* "
            f"(ID: {estado['selected_service_id']}) · "
            f"${float(estado['selected_service_price']):,.0f} · {dur}\n"
            f"NO preguntes de nuevo por el servicio."
        )

    _guardar_mensaje(phone, 'user', mensaje)
    historial = _cargar_historial(phone)  # recarga ya con el mensaje guardado

    texto_respuesta = _llamar_llm(system, historial)

    # ── Interceptar tokens ────────────────────────────────────────────────────
    if 'CONTACTAR_ASESOR' in texto_respuesta:
        respuesta_asesor = _manejar_asesor(phone)
        _guardar_mensaje(phone, 'assistant', respuesta_asesor)
        return respuesta_asesor

    if 'CONSULTAR_DISPONIBILIDAD:' in texto_respuesta:
        _manejar_consulta_disponibilidad(phone, texto_respuesta)
        return ''

    if 'AGENDAR_CITA:' in texto_respuesta:
        resultado = _agendar_cita(phone, texto_respuesta)
        if resultado:
            _guardar_mensaje(phone, 'assistant', resultado)
        return resultado

    _guardar_mensaje(phone, 'assistant', texto_respuesta)
    return texto_respuesta