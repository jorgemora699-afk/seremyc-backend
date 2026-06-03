"""
whatsapp_agent.py — Sere, agente de WhatsApp para Seremyc Sthetic
Versión producción: botones interactivos + anti-alucinación + expiración de sesión.
"""

import os
import json
import logging
import requests
from groq import Groq
from datetime import datetime, timezone
from time import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

groq_client = Groq(api_key=os.getenv('GROQ_API_KEY'))

_cache_servicios: dict = {'data': [], 'ts': 0.0}
_CACHE_TTL    = 300   # segundos
MAX_HISTORIAL = 20    # mensajes máx al LLM
SESSION_HORAS = 2     # horas antes de expirar la sesión

MAPA_CAT = {
    'cat_facial':       'facial',
    'cat_corporal':     'corporal',
    'cat_capilar':      'capilar',
    'cat_sueroterapia': 'sueroterapia',
    'cat_masaje':       'masaje',
}

# Campos requeridos en orden
CAMPOS_REQUERIDOS = [
    ('nombre',           '¿Cuál es tu nombre completo? 🌸'),
    ('correo',           '¿Cuál es tu correo electrónico? 📧'),
    ('fecha_nacimiento', '¿Cuál es tu fecha de nacimiento? 🎂 (DD/MM/YYYY)'),
    ('direccion',        '¿Cuál es tu dirección? 🏠'),
    ('tipo_piel',        '¿Cuál es tu tipo de piel? 🧴\n_normal / seca / mixta / grasa / sensible_'),
    ('alergias',         '¿Tienes alguna alergia? Si no tienes, escribe *ninguna* 🌿'),
    ('observaciones',    '¿Alguna observación para la terapeuta? Si no tienes, escribe *ninguna* 📝'),
]


# ══════════════════════════════════════════════════════════════════════════════
# INFRAESTRUCTURA
# ══════════════════════════════════════════════════════════════════════════════

def _base_url() -> str:
    return os.getenv('API_BASE_URL', 'http://localhost:5000')


def _headers() -> dict:
    return {
        'X-Agent-Key':  os.getenv('AGENT_API_KEY'),
        'Content-Type': 'application/json',
    }


def _normalizar_numero(numero: str) -> str:
    return numero.replace('whatsapp:', '').strip()


# ══════════════════════════════════════════════════════════════════════════════
# HISTORIAL
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
# ESTADO DE SESIÓN
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


def _sesion_expirada(estado: dict) -> bool:
    """Retorna True si han pasado más de SESSION_HORAS desde la última actividad."""
    try:
        updated_at = estado.get('updated_at')
        if not updated_at:
            return False
        ahora = datetime.now(timezone.utc)
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        return (ahora - updated_at).total_seconds() / 3600 > SESSION_HORAS
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════════
# SERVICIOS
# ══════════════════════════════════════════════════════════════════════════════

def _obtener_servicios_raw() -> list:
    if time() - _cache_servicios['ts'] < _CACHE_TTL and _cache_servicios['data']:
        return _cache_servicios['data']
    try:
        r = requests.get(
            f'{_base_url()}/api/agent/services',
            headers=_headers(), timeout=5
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
    return [s for s in servicios_raw if s.get('category', '').lower().strip() == categoria]


# ══════════════════════════════════════════════════════════════════════════════
# MENSAJES INTERACTIVOS
# ══════════════════════════════════════════════════════════════════════════════

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
        "O elige:",
        [
            {'id': 'cat_sueroterapia', 'title': '💉 Sueroterapia'},
            {'id': 'cat_masaje',       'title': '🤲 Masaje'},
        ]
    )


def _enviar_menu_servicios(phone: str, categoria: str, servicios: list) -> None:
    from infrastructure.web.whatsapp_sender import enviar_lista, enviar_mensaje
    if not servicios:
        enviar_mensaje(phone, f"No encontré servicios de {categoria} disponibles 😔\n¿Te interesa otra categoría? 🌸")
        return
    rows = []
    for s in servicios:
        mins = s['duration_minutes']
        dur  = f"{mins//60}h {mins%60:02d}min" if mins >= 60 else f"{mins}min"
        rows.append({
            'id':          f"svc_{s['id']}",
            'title':       s['name'][:24],
            'description': f"{dur} · ${float(s['price']):,.0f}",
        })
    enviar_lista(
        phone,
        texto=f"🌸 *Servicios de {categoria.capitalize()}:*\n\nElige el que te interesa 👇",
        boton_label="Ver servicios",
        secciones=[{'title': categoria.capitalize(), 'rows': rows}]
    )


def _enviar_confirmacion_servicio(phone: str, servicio: dict) -> None:
    from infrastructure.web.whatsapp_sender import enviar_botones
    mins = servicio['duration_minutes']
    dur  = f"{mins//60}h {mins%60:02d}min" if mins >= 60 else f"{mins}min"
    enviar_botones(
        phone,
        f"¿Confirmás que querés agendar *{servicio['name']}*? 😊\n\n"
        f"💰 ${float(servicio['price']):,.0f} · ⏱ {dur}",
        [
            {'id': 'confirmar_servicio', 'title': '✅ Sí, agendar'},
            {'id': 'cancelar_servicio',  'title': '❌ No, volver'},
        ]
    )


def _enviar_menu_horarios(phone: str, fecha: str, slots: list[str]) -> None:
    from infrastructure.web.whatsapp_sender import enviar_lista, enviar_mensaje
    try:
        dt    = datetime.strptime(fecha, '%Y-%m-%d')
        dias  = ['lunes','martes','miércoles','jueves','viernes','sábado','domingo']
        meses = ['enero','febrero','marzo','abril','mayo','junio',
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
            headers=_headers(), timeout=5
        )
        r.raise_for_status()
        return [s['label'] for s in r.json().get('available', [])]
    except Exception as e:
        logger.error(f"Error obteniendo slots para {fecha}: {e}")
        return []


def _verificar_disponibilidad(fecha_cita: str) -> bool:
    try:
        dt    = datetime.fromisoformat(fecha_cita)
        slots = _slots_disponibles(dt.strftime('%Y-%m-%d'))
        return dt.strftime('%H:00') in slots
    except Exception as e:
        logger.error(f"Error verificando disponibilidad: {e}")
        return True


# ══════════════════════════════════════════════════════════════════════════════
# RECOLECCIÓN DE DATOS — FLUJO DETERMINISTA
# ══════════════════════════════════════════════════════════════════════════════

def _extraer_datos_del_historial(historial: list[dict]) -> dict:
    """
    Extrae los datos recolectados del historial de forma determinista,
    buscando patrones [DATO:campo=valor] que el LLM guarda.
    """
    datos: dict = {}
    for msg in historial:
        if msg['role'] == 'user' and msg['content'].startswith('[DATO:'):
            try:
                # Formato: [DATO:campo=valor]
                inner = msg['content'][6:-1]  # quita '[DATO:' y ']'
                campo, valor = inner.split('=', 1)
                datos[campo.strip()] = valor.strip()
            except Exception:
                pass
    return datos


def _siguiente_campo_faltante(datos: dict) -> tuple[str, str] | None:
    """Retorna (campo, pregunta) del próximo dato que falta, o None si están todos."""
    for campo, pregunta in CAMPOS_REQUERIDOS:
        if not datos.get(campo):
            return campo, pregunta
    return None


def _guardar_dato(phone: str, campo: str, valor: str) -> None:
    """Guarda un dato recolectado en el historial con formato especial."""
    _guardar_mensaje(phone, 'user', f"[DATO:{campo}={valor}]")


# ══════════════════════════════════════════════════════════════════════════════
# SYSTEM PROMPT
# ══════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """Eres Sere, asistente virtual de Seremyc Sthetic 💜 — centro de bienestar y estética.

═══ PERSONALIDAD ═══
- Cálida, empática y profesional. Como una amiga experta en bienestar.
- Mensajes cortos (máx 100 palabras). Uno o dos emojis por mensaje.
- Siempre en español colombiano. Natural, nunca robótica.

═══ REGLAS ABSOLUTAS ═══
1. JAMÁS muestres los tokens CONSULTAR_DISPONIBILIDAD ni AGENDAR_CITA al cliente.
2. JAMÁS inventes horarios, fechas, precios ni datos.
3. JAMÁS corrijas ni modifiques datos que el cliente proporcionó — guárdalos exactamente como los escribió.
4. NUNCA repitas preguntas que ya aparecen en el historial.
5. NO muestres menús ni listas de servicios — el sistema los envía como botones interactivos.
6. Si el cliente pide hablar con una persona: responde SOLO la palabra: CONTACTAR_ASESOR
7. Cuando detectes el día deseado, emite SOLO: CONSULTAR_DISPONIBILIDAD:{{"fecha":"YYYY-MM-DD"}}
8. Solo cuando el cliente confirme el resumen, emite SOLO: AGENDAR_CITA:{{...json...}}

═══ FECHA ACTUAL ═══
Hoy: {fecha_actual}
- Fechas de nacimiento → DD/MM/YYYY
- Fechas de cita → YYYY-MM-DDTHH:MM:00
- Interpreta correctamente: "mañana", "el viernes", "la próxima semana", etc.

═══ PASO ACTUAL: RECOLECCIÓN DE DATOS ═══
El cliente ya eligió el servicio. Tu única tarea ahora es hacer la siguiente pregunta:

SIGUIENTE PREGUNTA: {siguiente_pregunta}

DATOS YA RECOLECTADOS:
{datos_recolectados}

INSTRUCCIÓN CRÍTICA:
- Haz ÚNICAMENTE la pregunta indicada en SIGUIENTE PREGUNTA.
- Si el cliente ya respondió esa pregunta (está en DATOS YA RECOLECTADOS), pasa a la siguiente.
- NO hagas múltiples preguntas en un mismo mensaje.
- Si el cliente da un dato que no te pediste, acéptalo y continúa con el siguiente dato faltante.
- Cuando tengas TODOS los datos + horario elegido, muestra el resumen y pide confirmación.

═══ RESUMEN (cuando todos los datos estén completos) ═══
📋 *Resumen de tu cita:*
👤 [nombre] · 📧 [correo] · 🎂 [nacimiento]
🏠 [dirección] · 🧴 Piel: [tipo] · Alergias: [alergias]
📝 [observaciones]
💆 [servicio] · 📅 [fecha y hora] · 💰 $[precio]
¿Todo correcto? ✅

═══ AGENDAR (solo si el cliente confirma el resumen) ═══
AGENDAR_CITA:{{"nombre":"...","correo":"...","fecha_nacimiento":"DD/MM/YYYY","direccion":"...","tipo_piel":"...","alergias":"...","observaciones":"...","servicio_id":ID,"fecha_cita":"YYYY-MM-DDTHH:MM:00"}}

═══ SERVICIO ACTIVO ═══
{servicio_activo}"""


def _construir_system_recoleccion(servicios_raw: list, estado: dict, historial: list[dict]) -> str:
    """System prompt especializado para la fase de recolección de datos."""
    fecha_actual    = datetime.now().strftime('%A %d de %B de %Y')
    datos           = _extraer_datos_del_historial(historial)
    siguiente       = _siguiente_campo_faltante(datos)
    siguiente_preg  = siguiente[1] if siguiente else "Ya tienes todos los datos. Muestra el resumen."

    datos_txt = "\n".join(
        f"  ✅ {campo}: {valor}"
        for campo, valor in datos.items()
    ) if datos else "  (ninguno aún)"

    # Incluir también el horario si ya fue elegido
    for msg in historial:
        if msg['role'] == 'user' and '[CTX:HORARIO_ELEGIDO]' in msg['content']:
            datos_txt += f"\n  ✅ fecha_cita: {msg['content'].split('Fecha y hora: ')[-1]}"
            break

    mins = estado.get('selected_service_duration', 0)
    dur  = f"{mins//60}h {mins%60:02d}min" if mins >= 60 else f"{mins}min"
    servicio_activo = (
        f"Nombre: {estado.get('selected_service_name')} | "
        f"ID: {estado.get('selected_service_id')} | "
        f"Precio: ${float(estado.get('selected_service_price', 0)):,.0f} | "
        f"Duración: {dur}"
    )

    return (
        SYSTEM_PROMPT
        .replace('{fecha_actual}',       fecha_actual)
        .replace('{siguiente_pregunta}', siguiente_preg)
        .replace('{datos_recolectados}', datos_txt)
        .replace('{servicio_activo}',    servicio_activo)
    )


# ══════════════════════════════════════════════════════════════════════════════
# LLM
# ══════════════════════════════════════════════════════════════════════════════

def _llamar_llm(system: str, mensajes: list, max_tokens: int = 400) -> str:
    try:
        respuesta = groq_client.chat.completions.create(
            model='llama-3.3-70b-versatile',
            max_tokens=max_tokens,
            temperature=0.3,   # más determinista, menos alucinaciones
            messages=[{'role': 'system', 'content': system}] + mensajes
        )
        return respuesta.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Error llamando LLM: {e}")
        return "Tuve un problema técnico 😔 ¿Puedes repetir eso?"


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
                    return parte[:i + 1]
    return parte.split('\n')[0].strip()


# ══════════════════════════════════════════════════════════════════════════════
# ACCIONES ESPECIALES
# ══════════════════════════════════════════════════════════════════════════════

def _manejar_asesor(phone: str) -> str:
    numero_asesor = os.getenv('ASESOR_WHATSAPP', '')
    if numero_asesor:
        return (
            f"¡Claro! 😊 Te conecto con una de nuestras asesoras.\n\n"
            f"📲 Escríbenos: wa.me/{numero_asesor}\n\n"
            f"En breve alguien del equipo te atenderá 💜"
        )
    return "¡Por supuesto! 😊 Una de nuestras asesoras te atenderá pronto 💜"


def _manejar_confirmacion_cita(phone: str, accion: str) -> str:
    try:
        r    = requests.get(
            f'{_base_url()}/api/agent/client-history',
            params={'phone': phone}, headers=_headers(), timeout=5
        )
        data = r.json()
        if not data.get('exists'):
            return "No encontré citas asociadas a tu número 😔\n¿Quieres agendar una nueva? 🌸"

        proxima = next((c for c in data.get('appointments', []) if c['status'] == 'confirmed'), None)
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


def _guardar_calificacion(phone: str, calificacion: int) -> str | None:
    try:
        r    = requests.get(
            f'{_base_url()}/api/agent/client-history',
            params={'phone': phone}, headers=_headers(), timeout=5
        )
        data = r.json()
        if not data.get('exists'):
            return None
        cita = next(
            (c for c in data.get('appointments', [])
             if c.get('survey_sent') and not c.get('survey_rating')),
            None
        )
        if not cita:
            return None
        requests.patch(
            f'{_base_url()}/api/agent/appointments/{cita["id"]}/survey',
            json={'rating': calificacion}, headers=_headers(), timeout=10
        )
        nombre = data['full_name'].split()[0]
        if calificacion >= 4:
            return f"¡Gracias {nombre}! 🌟 Nos alegra saber que tuviste una gran experiencia.\n\n¿Quieres dejarnos algún comentario? 😊"
        return f"Gracias por tu honestidad {nombre} 🙏\n\n¿Qué podríamos hacer mejor para ti? 💜"
    except Exception as e:
        logger.error(f"Error guardando calificación: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# DISPONIBILIDAD Y AGENDAMIENTO
# ══════════════════════════════════════════════════════════════════════════════

def _manejar_consulta_disponibilidad(phone: str, texto_llm: str) -> None:
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
        from infrastructure.web.whatsapp_sender import enviar_mensaje
        enviar_mensaje(phone, msg)
        return

    slots = _slots_disponibles(fecha)
    _guardar_estado(phone, pending_date=fecha)
    _enviar_menu_horarios(phone, fecha, slots)
    _guardar_mensaje(phone, 'assistant', f"[Horarios enviados para {fecha}]")
    _guardar_mensaje(phone, 'user',
        f"[SISTEMA] Disponibilidad consultada para {fecha}. "
        f"Slots disponibles: {', '.join(slots) if slots else 'ninguno'}."
    )


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

        # Crear o actualizar cliente
        r_cliente = requests.post(
            f'{_base_url()}/api/agent/clients',
            json={
                'full_name':    datos['nombre'],
                'phone':        phone,
                'email':        datos.get('correo', ''),
                'birth_date':   datos.get('fecha_nacimiento', ''),
                'address':      datos.get('direccion', ''),
                'skin_type':    datos.get('tipo_piel', ''),
                'allergies':    datos.get('alergias', ''),
                'observations': datos.get('observaciones', ''),
            },
            headers=_headers(), timeout=10
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
                'observations': datos.get('observaciones', ''),
            },
            headers=_headers(), timeout=10
        )
        r_cita.raise_for_status()
        cita = r_cita.json()

        try:
            dt    = datetime.fromisoformat(datos['fecha_cita'])
            dias  = ['lunes','martes','miércoles','jueves','viernes','sábado','domingo']
            meses = ['enero','febrero','marzo','abril','mayo','junio',
                     'julio','agosto','septiembre','octubre','noviembre','diciembre']
            fecha_legible = (
                f"{dias[dt.weekday()]} {dt.day} de {meses[dt.month-1]} "
                f"de {dt.year} a las {dt.strftime('%H:%M')}"
            )
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
# BIENVENIDA
# ══════════════════════════════════════════════════════════════════════════════

def _saludo_bienvenida(phone: str) -> str:
    """Retorna el saludo personalizado si el cliente es conocido."""
    try:
        r    = requests.get(
            f'{_base_url()}/api/agent/client-history',
            params={'phone': phone}, headers=_headers(), timeout=5
        )
        data = r.json()
        if data.get('exists'):
            nombre = data['full_name'].split()[0]
            return f"¡Hola {nombre}! 😊 Qué gusto verte de nuevo 💜\n\n¿Qué te gustaría agendar hoy?"
    except Exception:
        pass
    return "¡Hola! 😊 Bienvenida a Seremyc Sthetic 💜\n\n¿Qué tipo de servicio te interesa hoy?"


# ══════════════════════════════════════════════════════════════════════════════
# FUNCIÓN PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def procesar_mensaje(numero: str, mensaje: str) -> str:
    """
    Retorna el texto a enviar al cliente,
    o '' si ya se envió un mensaje interactivo directamente.
    """
    phone         = _normalizar_numero(numero)
    mensaje_lower = mensaje.lower().strip()

    # ── 1. Gestión de cita existente ─────────────────────────────────────────
    if mensaje_lower in ['confirmar', 'cancelar', 'reagendar']:
        return _manejar_confirmacion_cita(phone, mensaje_lower)

    # ── 2. Solicitud de asesor ────────────────────────────────────────────────
    palabras_asesor = ['asesor', 'asesora', 'humano', 'persona real',
                       'hablar con alguien', 'agente', 'representante']
    if any(p in mensaje_lower for p in palabras_asesor):
        return 'CONTACTAR_ASESOR'

    # ── 3. Calificación de encuesta ───────────────────────────────────────────
    if mensaje_lower in ['1', '2', '3', '4', '5']:
        resultado = _guardar_calificacion(phone, int(mensaje_lower))
        if resultado:
            return resultado

    # ── 4. Cargar estado y verificar expiración ───────────────────────────────
    servicios_raw = _obtener_servicios_raw()
    estado        = _cargar_estado(phone)

    if estado and _sesion_expirada(estado):
        logger.info(f"Sesión expirada para {phone}, reiniciando.")
        _limpiar_estado(phone)
        _limpiar_historial(phone)
        estado = {}

    # ── 5. Selección de categoría (botón interactivo) ─────────────────────────
    if mensaje_lower in MAPA_CAT and not estado.get('selected_service_id'):
        categoria     = MAPA_CAT[mensaje_lower]
        servicios_cat = _servicios_de_categoria(categoria, servicios_raw)
        _guardar_estado(phone, selected_category=categoria, current_step='eligiendo_servicio')
        _guardar_mensaje(phone, 'user', f"[Categoría elegida: {categoria}]")
        _enviar_menu_servicios(phone, categoria, servicios_cat)
        return ''

    # ── 6. Selección de servicio (lista interactiva) ──────────────────────────
    if mensaje_lower.startswith('svc_') and not estado.get('selected_service_id'):
        try:
            svc_id   = int(mensaje_lower.replace('svc_', ''))
            servicio = next((s for s in servicios_raw if s['id'] == svc_id), None)
            if servicio:
                _guardar_estado(
                    phone,
                    selected_service_id=servicio['id'],
                    selected_service_name=servicio['name'],
                    selected_service_price=float(servicio['price']),
                    selected_service_duration=servicio['duration_minutes'],
                    current_step='confirmando_servicio'
                )
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

    # ── 7. Cancelar servicio ──────────────────────────────────────────────────
    if mensaje_lower == 'cancelar_servicio':
        _limpiar_estado(phone)
        _limpiar_historial(phone)
        from infrastructure.web.whatsapp_sender import enviar_mensaje
        enviar_mensaje(phone, "¡Sin problema! 😊 Volvamos a empezar 🌸")
        _enviar_menu_categorias(phone)
        return ''

    # ── 8. Confirmar servicio ─────────────────────────────────────────────────
    if mensaje_lower == 'confirmar_servicio':
        _guardar_estado(phone, current_step='recolectando_datos')
        _guardar_mensaje(phone, 'user', '[Cliente confirmó el servicio]')

    # ── 9. Selección de horario (lista interactiva) ───────────────────────────
    if mensaje_lower.startswith('hora_') and estado.get('pending_date'):
        hora_str = mensaje_lower.replace('hora_', '')
        hora_fmt = f"{hora_str[:2]}:{hora_str[2:]}"
        fecha_dt = f"{estado['pending_date']}T{hora_fmt}:00"
        _guardar_mensaje(phone, 'user', f"[CTX:HORARIO_ELEGIDO] Fecha y hora: {fecha_dt}")
        _guardar_estado(phone, pending_date=None, current_step='resumen')

    # ── 10. Recargar estado actualizado ──────────────────────────────────────
    estado = _cargar_estado(phone)

    # ── 11. Sin servicio seleccionado → bienvenida + categorías ──────────────
    if not estado.get('selected_service_id') and \
       estado.get('current_step') not in ['recolectando_datos', 'resumen']:
        from infrastructure.web.whatsapp_sender import enviar_mensaje
        saludo = _saludo_bienvenida(phone)
        _guardar_mensaje(phone, 'user',      mensaje)
        _guardar_mensaje(phone, 'assistant', saludo)
        enviar_mensaje(phone, saludo)
        _enviar_menu_categorias(phone)
        return ''

    # ── 12. Fase LLM: recolección de datos + resumen + agendamiento ───────────
    _guardar_mensaje(phone, 'user', mensaje)
    historial = _cargar_historial(phone)

    system          = _construir_system_recoleccion(servicios_raw, estado, historial)
    texto_respuesta = _llamar_llm(system, historial)

    # ── 13. Interceptar tokens del LLM ───────────────────────────────────────
    if 'CONTACTAR_ASESOR' in texto_respuesta:
        msg = _manejar_asesor(phone)
        _guardar_mensaje(phone, 'assistant', msg)
        return msg

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