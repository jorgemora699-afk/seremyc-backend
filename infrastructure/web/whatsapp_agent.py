"""
whatsapp_agent.py — Sere, agente de WhatsApp para Seremyc Sthetic
Versión corregida: historial persistente en PostgreSQL, estado de sesión robusto.
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

# ─── Caché de servicios (en RAM está bien, son datos estáticos) ──────────────
_cache_servicios: dict = {'data': [], 'ts': 0.0}
_CACHE_TTL = 300

MAX_HISTORIAL = 24   # turnos a cargar desde BD
CATEGORIAS = ['facial', 'corporal', 'capilar', 'sueroterapia', 'masaje']
MAPA_NUMEROS_CAT = {
    '1': 'facial', '2': 'corporal', '3': 'capilar',
    '4': 'sueroterapia', '5': 'masaje'
}


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
# PERSISTENCIA DE HISTORIAL EN POSTGRESQL
# ══════════════════════════════════════════════════════════════════════════════

def _cargar_historial(phone: str) -> list[dict]:
    """Carga los últimos MAX_HISTORIAL mensajes desde la BD."""
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
        # Invertir para orden cronológico
        return [{'role': r[0], 'content': r[1]} for r in reversed(rows)]
    except Exception as e:
        logger.error(f"Error cargando historial {phone}: {e}")
        return []


def _guardar_mensaje(phone: str, role: str, content: str) -> None:
    """Persiste un mensaje en la BD."""
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
    """Elimina el historial de conversación (al terminar un agendamiento)."""
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
# ESTADO DE SESIÓN EN POSTGRESQL
# ══════════════════════════════════════════════════════════════════════════════

def _cargar_estado(phone: str) -> dict:
    """Carga el estado de la sesión desde la BD."""
    try:
        from infrastructure.database.db import db
        from sqlalchemy import text
        row = db.session.execute(
            text("SELECT * FROM conversation_state WHERE phone = :phone"),
            {'phone': phone}
        ).fetchone()
        if row:
            return dict(row._mapping)
        return {}
    except Exception as e:
        logger.error(f"Error cargando estado {phone}: {e}")
        return {}


def _guardar_estado(phone: str, **kwargs) -> None:
    """Upsert del estado de la sesión."""
    try:
        from infrastructure.database.db import db
        from sqlalchemy import text

        if not kwargs:
            return

        cols = ', '.join(kwargs.keys())
        updates = ', '.join(f"{k} = :{k}" for k in kwargs)
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
    """Elimina el estado de sesión al terminar el flujo."""
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
        _cache_servicios['ts'] = time()
        return data
    except Exception as e:
        logger.error(f"Error obteniendo servicios: {e}")
        return _cache_servicios['data']


def _obtener_servicios_texto(servicios_raw: list) -> str:
    """Texto compacto de servicios para el system prompt."""
    if not servicios_raw:
        return "Servicios: consultar con asesora."
    categorias: dict[str, list] = {}
    for s in servicios_raw:
        cat = s.get('category', 'otro').lower().strip()
        mins = s['duration_minutes']
        dur = f"{mins//60}h{mins%60:02d}m" if mins >= 60 else f"{mins}min"
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


def _formatear_menu_categoria(categoria: str, servicios: list) -> str:
    if not servicios:
        return (
            f"Hmm, no encontré servicios de {categoria} disponibles 😔\n"
            f"¿Te interesa otra categoría? 🌸"
        )
    texto = f"🌸 *Servicios de {categoria.capitalize()}:*\n\n"
    for i, s in enumerate(servicios, 1):
        mins = s['duration_minutes']
        dur = f"{mins//60}h {mins%60:02d}min" if mins >= 60 else f"{mins}min"
        texto += f"{i}️⃣ *{s['name']}*\n   ⏱ {dur} · 💰 ${float(s['price']):,.0f}\n\n"
    texto += "¿Cuál te gustaría agendar? Escribe el número o el nombre 😊"
    return texto


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


def _formatear_slots(fecha: str, slots: list[str]) -> str:
    try:
        dt = datetime.strptime(fecha, '%Y-%m-%d')
        dias = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']
        meses = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
                 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
        fecha_legible = f"{dias[dt.weekday()]} {dt.day} de {meses[dt.month-1]} de {dt.year}"
    except ValueError:
        fecha_legible = fecha

    if not slots:
        return (
            f"😔 No hay horarios disponibles para el {fecha_legible}.\n"
            f"¿Te gustaría elegir otro día? 🗓"
        )

    emojis = ['1️⃣','2️⃣','3️⃣','4️⃣','5️⃣','6️⃣','7️⃣','8️⃣','9️⃣','🔟','1️⃣1️⃣']
    opciones = "\n".join(
        f"{emojis[i] if i < len(emojis) else '▪️'} {h}"
        for i, h in enumerate(slots)
    )
    return (
        f"📅 *Horarios disponibles — {fecha_legible}:*\n\n"
        f"{opciones}\n\n"
        f"¿Cuál te queda mejor? 😊"
    )


def _verificar_disponibilidad(fecha_cita: str) -> bool:
    try:
        dt = datetime.fromisoformat(fecha_cita)
        fecha = dt.strftime('%Y-%m-%d')
        hora_solicitada = dt.strftime('%H:00')
        slots = _slots_disponibles(fecha)
        return hora_solicitada in slots
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
5. Si hay un [CTX:SERVICIO] en el historial, ese ES el servicio seleccionado. No preguntes de nuevo.
6. Cuando detectes el día deseado, emite SOLO: CONSULTAR_DISPONIBILIDAD:{"fecha":"YYYY-MM-DD"}
7. Solo cuando el cliente confirme todos los datos, emite SOLO: AGENDAR_CITA:{...json...}
8. Si el cliente pide hablar con una persona: responde SOLO "CONTACTAR_ASESOR"

═══ FECHAS ═══
Hoy: {fecha_actual}
- Fechas de nacimiento → DD/MM/YYYY
- Fechas de cita → YYYY-MM-DDTHH:MM:00
- Interpreta siempre: "mañana", "el viernes", "la próxima semana", etc.

═══ FLUJO OBLIGATORIO ═══

[PASO 1 — BIENVENIDA]
Saluda con tu nombre y presenta:
"¿Qué tipo de servicio te interesa? 🌸
1️⃣ Facial  2️⃣ Corporal  3️⃣ Capilar  4️⃣ Sueroterapia  5️⃣ Masaje"

[PASO 2 — CONFIRMAR SERVICIO]
Al elegir categoría y servicio, confirma:
"¿Confirmás que querés agendar *[nombre servicio]*? 😊
💰 $[precio] · ⏱ [duración]"
Espera un "Sí" explícito antes de continuar.

[PASO 3 — RECOLECCIÓN DE DATOS]
Pide UNO por UNO. Cuando ya lo tienes en el historial, NO vuelvas a pedirlo:
① Nombre completo
② Correo electrónico
③ Fecha de nacimiento (DD/MM/YYYY)
④ Dirección
⑤ Tipo de piel (normal/seca/mixta/grasa/sensible)
⑥ Alergias (o "ninguna")
⑦ Observaciones para el terapeuta (o "ninguna")
⑧ Día deseado → emite CONSULTAR_DISPONIBILIDAD:{"fecha":"YYYY-MM-DD"}
⑨ Horario → el cliente elige de la lista que el sistema muestra

[PASO 4 — RESUMEN]
Muestra EXACTAMENTE lo que el cliente dio, sin cambiar nada:
"📋 *Resumen de tu cita:*
👤 [nombre]
📧 [correo]
🎂 [fecha nacimiento]
🏠 [dirección]
🧴 Piel: [tipo] · Alergias: [alergias]
📝 Obs: [observaciones]
💆 [nombre del servicio]
📅 [fecha y hora legibles]
💰 $[precio]

¿Todo correcto? ✅"

[PASO 5 — AGENDAR]
Solo si el cliente confirma ("sí", "correcto", "así es", "perfecto"):
AGENDAR_CITA:{"nombre":"...","correo":"...","fecha_nacimiento":"DD/MM/YYYY","direccion":"...","tipo_piel":"...","alergias":"...","observaciones":"...","servicio_id":NUMERO,"fecha_cita":"YYYY-MM-DDTHH:MM:00"}

═══ SERVICIOS DEL NEGOCIO ═══
{servicios}"""


def _construir_system(servicios_raw: list) -> str:
    fecha_actual = datetime.now().strftime('%A %d de %B de %Y')
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
            f"📲 Escríbenos directamente: wa.me/{numero_asesor}\n\n"
            f"También puedes seguir chateando conmigo si prefieres 💜"
        )
    return (
        f"¡Por supuesto! 😊 Una de nuestras asesoras te atenderá pronto.\n\n"
        f"También puedo seguir ayudándote por aquí si lo prefieres 💜"
    )


def _manejar_confirmacion_cita(numero: str, accion: str) -> str:
    try:
        phone = _normalizar_numero(numero)
        r = requests.get(
            f'{_base_url()}/api/agent/client-history',
            params={'phone': phone},
            headers=_headers(),
            timeout=5
        )
        data = r.json()
        if not data.get('exists'):
            return "No encontré citas asociadas a tu número 😔\n¿Quieres agendar una nueva? 🌸"

        citas = data.get('appointments', [])
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
            return (
                f"¡Claro {nombre}! Vamos a reagendar tu *{proxima['service']}* 🗓\n\n"
                f"¿Qué día te vendría mejor?"
            )
    except Exception as e:
        logger.error(f"Error manejando acción {accion}: {e}")
        return "Hubo un error procesando tu solicitud 😔 Por favor contáctanos directamente."


def _guardar_calificacion(numero: str, calificacion: int) -> str | None:
    try:
        phone = _normalizar_numero(numero)
        r = requests.get(
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
            return (
                f"¡Gracias {nombre}! 🌟 Nos alegra saber que tuviste una gran experiencia.\n\n"
                f"¿Quieres dejarnos algún comentario? 😊\n_(Escribe NO si prefieres no hacerlo)_"
            )
        else:
            return (
                f"Gracias por tu honestidad {nombre} 🙏\n\n"
                f"Nos importa mucho mejorar. ¿Qué podríamos hacer mejor para ti? 💜"
            )
    except Exception as e:
        logger.error(f"Error guardando calificación: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# MANEJO DE DISPONIBILIDAD Y AGENDAMIENTO
# ══════════════════════════════════════════════════════════════════════════════

def _manejar_consulta_disponibilidad(phone: str, texto_llm: str, system: str, historial: list) -> str:
    try:
        json_str = _extraer_token(texto_llm, 'CONSULTAR_DISPONIBILIDAD:')
        if not json_str:
            raise ValueError("Token no encontrado")
        datos = json.loads(json_str)
        fecha = datos['fecha']
    except Exception as e:
        logger.error(f"CONSULTAR_DISPONIBILIDAD malformado: {e} — {texto_llm}")
        msg = "Tuve un problema consultando la disponibilidad 😔 ¿Me repites el día que prefieres?"
        _guardar_mensaje(phone, 'assistant', msg)
        return msg

    slots = _slots_disponibles(fecha)
    slots_texto = _formatear_slots(fecha, slots)

    # Guardar en estado la fecha pendiente y los slots disponibles
    _guardar_estado(phone, pending_date=fecha)

    # Reemplazar el token en historial por algo legible para el LLM
    msg_sistema = (
        f"[SISTEMA] Disponibilidad consultada para {fecha}. "
        f"Slots disponibles: {', '.join(slots) if slots else 'ninguno'}. "
        f"Muestra exactamente estos horarios al cliente sin inventar ninguno."
    )

    # Respuesta final que ve el cliente: directamente los slots formateados
    # Sin pasar por el LLM para evitar que invente o omita horarios
    _guardar_mensaje(phone, 'assistant', slots_texto)
    _guardar_mensaje(phone, 'user', msg_sistema)   # contexto para el próximo turno
    return slots_texto


def _agendar_cita(phone: str, texto_llm: str) -> str:
    try:
        json_str = _extraer_token(texto_llm, 'AGENDAR_CITA:')
        if not json_str:
            raise ValueError("Token no encontrado")
        datos = json.loads(json_str)
        datos['servicio_id'] = int(datos['servicio_id'])

        # Verificar disponibilidad antes de crear
        if not _verificar_disponibilidad(datos['fecha_cita']):
            dt = datetime.fromisoformat(datos['fecha_cita'])
            fecha = dt.strftime('%Y-%m-%d')
            slots = _slots_disponibles(fecha)
            slots_texto = ', '.join(slots[:5]) if slots else 'ninguno disponible'
            msg = (
                f"😔 El horario {dt.strftime('%H:00')} del {dt.strftime('%d/%m/%Y')} ya está ocupado.\n\n"
                f"⏰ Horarios libres ese día: {slots_texto}\n\n"
                f"¿Cuál te viene mejor?"
            )
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

        # Formatear fecha legible para el mensaje de confirmación
        try:
            dt = datetime.fromisoformat(datos['fecha_cita'])
            dias = ['lunes','martes','miércoles','jueves','viernes','sábado','domingo']
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
            f"¡Te esperamos con mucho cariño en Seremyc Sthetic! 💜\n"
            f"Si necesitas algo más, aquí estaré 🌸"
        )

        # Limpiar todo el estado de esta conversación
        _limpiar_historial(phone)
        _limpiar_estado(phone)

        return confirmacion

    except json.JSONDecodeError as e:
        logger.error(f"JSON inválido AGENDAR_CITA: {e} — {texto_llm}")
        return "Hubo un problema procesando tu cita 😔 ¿Intentamos de nuevo?"
    except Exception as e:
        logger.error(f"Error agendando cita {phone}: {e}")
        return (
            "Ocurrió un error al agendar 😔\n"
            "Por favor escribe *asesor* para que te ayude una de nosotras 💜"
        )


# ══════════════════════════════════════════════════════════════════════════════
# FUNCIÓN PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def procesar_mensaje(numero: str, mensaje: str) -> str:

    phone = _normalizar_numero(numero)
    mensaje_lower = mensaje.lower().strip()

    # ── Acciones especiales directas ────────────────────────────────────────
    if mensaje_lower in ['confirmar', 'cancelar', 'reagendar']:
        return _manejar_confirmacion_cita(phone, mensaje_lower)

    palabras_asesor = ['asesor', 'asesora', 'humano', 'persona real',
                       'hablar con alguien', 'agente', 'representante']
    if any(p in mensaje_lower for p in palabras_asesor):
        return _manejar_asesor(phone)

    # ── Calificación de encuesta ─────────────────────────────────────────────
    if mensaje_lower in ['1', '2', '3', '4', '5']:
        resultado_encuesta = _guardar_calificacion(phone, int(mensaje_lower))
        if resultado_encuesta:
            return resultado_encuesta
        # Si no era encuesta, continúa el flujo normal

    # ── Cargar datos persistentes ────────────────────────────────────────────
    servicios_raw = _obtener_servicios_raw()
    historial = _cargar_historial(phone)
    estado = _cargar_estado(phone)

    es_primer_mensaje = len(historial) == 0

    # ── Primer mensaje: inyectar contexto del cliente si ya existe ───────────
    if es_primer_mensaje:
        try:
            r = requests.get(
                f'{_base_url()}/api/agent/client-history',
                params={'phone': phone},
                headers=_headers(),
                timeout=5
            )
            data_cliente = r.json()
            if data_cliente.get('exists'):
                citas = data_cliente.get('appointments', [])
                ultimo_servicio = citas[0]['service'] if citas else None
                ctx = (
                    f"[CTX:CLIENTE_CONOCIDO] "
                    f"Nombre: {data_cliente['full_name']} | "
                    f"Último servicio: {ultimo_servicio or 'ninguno'} | "
                    f"Salúdala por su nombre de forma natural y pregunta en qué le puedes ayudar."
                )
                _guardar_mensaje(phone, 'user', ctx)
                historial = _cargar_historial(phone)
        except Exception as e:
            logger.error(f"Error obteniendo historial cliente {phone}: {e}")

    # ── Detección de categoría (números 1-5 sin servicio previo) ────────────
    #    Solo aplica si el estado NO tiene un servicio ya seleccionado
    if not estado.get('selected_service_id'):
        categoria_detectada = None

        if mensaje_lower.strip() in MAPA_NUMEROS_CAT:
            categoria_detectada = MAPA_NUMEROS_CAT[mensaje_lower.strip()]
        elif mensaje_lower.strip() in CATEGORIAS:
            categoria_detectada = mensaje_lower.strip()

        if categoria_detectada:
            servicios_cat = _servicios_de_categoria(categoria_detectada, servicios_raw)
            _guardar_estado(phone,
                            selected_category=categoria_detectada,
                            current_step='eligiendo_servicio')
            respuesta = _formatear_menu_categoria(categoria_detectada, servicios_cat)
            _guardar_mensaje(phone, 'user', mensaje)
            _guardar_mensaje(phone, 'assistant', respuesta)
            return respuesta

    # ── Detección de servicio por número (dentro de una categoría) ──────────
    if (mensaje_lower.strip().isdigit()
            and estado.get('selected_category')
            and not estado.get('selected_service_id')):

        categoria = estado['selected_category']
        servicios_cat = _servicios_de_categoria(categoria, servicios_raw)
        idx = int(mensaje_lower.strip()) - 1

        if 0 <= idx < len(servicios_cat):
            servicio = servicios_cat[idx]
            mins = servicio.get('duration_minutes', 0)
            dur = f"{mins//60}h {mins%60:02d}min" if mins >= 60 else f"{mins}min"

            # Persistir el servicio seleccionado en el estado
            _guardar_estado(phone,
                            selected_service_id=servicio['id'],
                            selected_service_name=servicio['name'],
                            selected_service_price=float(servicio['price']),
                            selected_service_duration=mins,
                            current_step='confirmando_servicio')

            respuesta = (
                f"¿Confirmás que querés agendar *{servicio['name']}*? 😊\n\n"
                f"💰 ${float(servicio['price']):,.0f} · ⏱ {dur}"
            )

            # Inyectar contexto del servicio en el historial para el LLM
            ctx_servicio = (
                f"[CTX:SERVICIO_SELECCIONADO] "
                f"Nombre: {servicio['name']} | ID: {servicio['id']} | "
                f"Precio: ${float(servicio['price']):,.0f} | Duración: {mins}min | "
                f"El cliente ha elegido ESTE servicio. No preguntes de nuevo."
            )
            _guardar_mensaje(phone, 'user', ctx_servicio)
            _guardar_mensaje(phone, 'assistant', respuesta)
            return respuesta

    # ── Flujo LLM para el resto de la conversación ──────────────────────────

    # Enriquecer el system prompt con el estado actual si hay servicio seleccionado
    system = _construir_system(servicios_raw)

    if estado.get('selected_service_id'):
        mins = estado.get('selected_service_duration', 0)
        dur = f"{mins//60}h {mins%60:02d}min" if mins >= 60 else f"{mins}min"
        system += (
            f"\n\n═══ SERVICIO ACTIVO EN ESTA SESIÓN ═══\n"
            f"El cliente ya eligió: *{estado['selected_service_name']}* "
            f"(ID: {estado['selected_service_id']}) · "
            f"${float(estado['selected_service_price']):,.0f} · {dur}\n"
            f"NO preguntes de nuevo por el servicio. Continúa con los datos del cliente."
        )

    # Recargar historial actualizado y agregar mensaje del usuario
    historial = _cargar_historial(phone)
    _guardar_mensaje(phone, 'user', mensaje)
    historial.append({'role': 'user', 'content': mensaje})

    texto_respuesta = _llamar_llm(system, historial)

    # ── Interceptar tokens especiales ────────────────────────────────────────

    if 'CONTACTAR_ASESOR' in texto_respuesta:
        respuesta_asesor = _manejar_asesor(phone)
        _guardar_mensaje(phone, 'assistant', respuesta_asesor)
        return respuesta_asesor

    if 'CONSULTAR_DISPONIBILIDAD:' in texto_respuesta:
        return _manejar_consulta_disponibilidad(phone, texto_respuesta, system, historial)

    if 'AGENDAR_CITA:' in texto_respuesta:
        return _agendar_cita(phone, texto_respuesta)

    _guardar_mensaje(phone, 'assistant', texto_respuesta)
    return texto_respuesta