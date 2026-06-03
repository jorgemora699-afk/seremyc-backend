import os
import json
import logging
import requests
from anthropic import Anthropic
from datetime import datetime
from time import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = Anthropic()

conversaciones: dict[str, list] = {}
ultima_categoria: dict[str, str] = {}
servicios_categoria: dict[str, list] = {}

MAX_HISTORIAL = 20

CATEGORIAS = ['facial', 'corporal', 'capilar', 'sueroterapia', 'masaje']

_cache_servicios: dict = {'data': [], 'ts': 0.0}
_CACHE_TTL = 300


def _obtener_servicios_raw() -> list:
    if time() - _cache_servicios['ts'] < _CACHE_TTL and _cache_servicios['data']:
        return _cache_servicios['data']
    try:
        r = requests.get(
            f'{_base_url()}/api/agent/services',
            headers=_obtener_headers(),
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
    if not servicios_raw:
        return "Servicios: consultar con asesora."

    categorias: dict[str, list] = {}
    for s in servicios_raw:
        cat = s.get('category', 'otro').lower().strip()
        categorias.setdefault(cat, [])
        mins = s['duration_minutes']
        duracion = f"{mins//60}h{mins%60:02d}m" if mins >= 60 else f"{mins}min"
        categorias[cat].append(
            f"- {s['name']} (ID:{s['id']}) {duracion} ${float(s['price']):,.0f}"
        )

    texto = "SERVICIOS:\n"
    for cat, items in categorias.items():
        texto += f"{cat.upper()}:\n" + "\n".join(items) + "\n"
    return texto


SYSTEM_PROMPT = """Eres Sere, asistente virtual de Seremyc Sthetic 💜 — centro de bienestar y estética.

═══ PERSONALIDAD ═══
- Cálida, empática, profesional. Como una amiga experta en bienestar.
- Mensajes cortos (máx 120 palabras). Uno o dos emojis por mensaje.
- Siempre en español. Nunca uses tecnicismos innecesarios.
- Si el cliente está indeciso, ayúdale con una recomendación amable.

═══ REGLAS ABSOLUTAS ═══
1. JAMÁS muestres "CONSULTAR_DISPONIBILIDAD:..." ni "AGENDAR_CITA:..." al cliente.
2. JAMÁS inventes horarios, fechas ni datos. Solo usa lo que el sistema provee.
3. JAMÁS omitas ni cambies datos que el cliente proporcionó.
4. Si el cliente pide hablar con un asesor humano, responde: "CONTACTAR_ASESOR"
5. Cuando detectes el día deseado para la cita, emite SOLO: CONSULTAR_DISPONIBILIDAD:{"fecha":"YYYY-MM-DD"}
6. Cuando tengas confirmación final, emite SOLO: AGENDAR_CITA:{...json...}

═══ FECHAS ═══
Hoy: {fecha_actual}
- Nacimiento → DD/MM/YYYY
- Cita → YYYY-MM-DDTHH:MM:00
- "mañana", "el viernes", "próxima semana" → calcula la fecha exacta

═══ FLUJO ═══

[PASO 1 - BIENVENIDA]
Saluda con tu nombre y presenta las opciones:
"¿Qué tipo de servicio te interesa? 🌸
1️⃣ Facial  2️⃣ Corporal  3️⃣ Capilar  4️⃣ Sueroterapia  5️⃣ Masaje
_(Escribe el número o el nombre)_"

[PASO 2 - CONFIRMAR SERVICIO]
Al elegir: "¿Confirmás que querés agendar *[servicio]*? 😊
💰 $[precio] · ⏱ [duración]"

[PASO 3 - DATOS] Pide uno por uno con naturalidad:
① Nombre completo
② Correo electrónico  
③ Fecha de nacimiento (DD/MM/YYYY)
④ Dirección
⑤ Tipo de piel (normal/seca/mixta/grasa/sensible)
⑥ Alergias (o "ninguna")
⑦ Observaciones (o "ninguna")
⑧ Día deseado → emite CONSULTAR_DISPONIBILIDAD:{"fecha":"YYYY-MM-DD"}
⑨ Cliente elige horario → guarda YYYY-MM-DDTHH:MM:00

[PASO 4 - RESUMEN]
Muestra EXACTAMENTE los datos que el cliente dio, sin cambiar nada:
"📋 *Resumen de tu cita:*
👤 [nombre exacto del cliente]
📧 [correo exacto]
🎂 [fecha nacimiento exacta]
🏠 [dirección exacta]
🧴 Piel: [tipo exacto] · Alergias: [exacto]
💆 [servicio]
📅 [fecha y hora]
💰 $[precio]

¿Todo correcto? ✅"

[PASO 5 - AGENDAR]
Solo si el cliente confirma, emite ÚNICAMENTE:
AGENDAR_CITA:{"nombre":"...","correo":"...","fecha_nacimiento":"...","direccion":"...","tipo_piel":"...","alergias":"...","observaciones":"...","servicio_id":ID,"fecha_cita":"YYYY-MM-DDTHH:MM:00"}

═══ CONTACTO ASESOR ═══
Si el cliente escribe "asesor", "humano", "persona", "hablar con alguien" o similar:
Responde SOLO: CONTACTAR_ASESOR

═══ DATOS DEL NEGOCIO ═══
📍 Seremyc Sthetic — Centro de bienestar y estética
📞 Para dudas adicionales puedes escribirnos directamente.

{servicios}"""


def _normalizar_numero(numero: str) -> str:
    return numero.replace('whatsapp:', '').strip()


def _obtener_headers() -> dict:
    return {
        'X-Agent-Key': os.getenv('AGENT_API_KEY'),
        'Content-Type': 'application/json'
    }


def _base_url() -> str:
    return os.getenv('API_BASE_URL', 'http://localhost:5000')


def _verificar_disponibilidad(fecha_cita: str) -> bool:
    try:
        dt = datetime.fromisoformat(fecha_cita)
        fecha = dt.strftime('%Y-%m-%d')
        hora_solicitada = dt.strftime('%H:00')
        r = requests.get(
            f'{_base_url()}/api/agent/availability',
            params={'date': fecha},
            headers=_obtener_headers(),
            timeout=5
        )
        r.raise_for_status()
        horas_libres = [s['label'] for s in r.json().get('available', [])]
        return hora_solicitada in horas_libres
    except Exception as e:
        logger.error(f"Error verificando disponibilidad: {e}")
        return True


def _respuesta_categoria(numero: str, categoria: str, servicios_raw: list) -> str:
    filtrados = [
        s for s in servicios_raw
        if s.get('category', '').lower().strip() == categoria
    ]

    if not filtrados:
        return (
            f"Hmm, no encontré servicios de {categoria} en este momento 😔\n"
            f"¿Te interesa otra categoría? Puedo mostrarte las opciones disponibles 🌸"
        )

    servicios_categoria[numero] = filtrados

    texto = f"🌸 *Servicios de {categoria.capitalize()}:*\n\n"
    for i, s in enumerate(filtrados, 1):
        mins = s['duration_minutes']
        duracion = f"{mins//60}h {mins%60:02d}min" if mins >= 60 else f"{mins} min"
        texto += f"{i}️⃣ *{s['name']}*\n   ⏱ {duracion} · 💰 ${float(s['price']):,.0f}\n\n"

    texto += "¿Cuál te gustaría agendar? Escribe el número o el nombre 😊"
    return texto


def _slots_disponibles(fecha: str) -> list[str]:
    try:
        r = requests.get(
            f'{_base_url()}/api/agent/availability',
            params={'date': fecha},
            headers=_obtener_headers(),
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
        fecha_legible = f"{dias[dt.weekday()]} {dt.day} de {meses[dt.month-1]}"
    except ValueError:
        fecha_legible = fecha

    if not slots:
        return (
            f"😔 No hay horarios disponibles para el {fecha_legible}.\n"
            f"¿Te gustaría elegir otro día? Puedo ayudarte a encontrar uno 🗓"
        )

    emojis = ['1️⃣','2️⃣','3️⃣','4️⃣','5️⃣','6️⃣','7️⃣','8️⃣','9️⃣','🔟']
    opciones = "\n".join(
        f"{emojis[i] if i < len(emojis) else '▪️'} {h}"
        for i, h in enumerate(slots)
    )
    return (
        f"📅 *Horarios disponibles — {fecha_legible}:*\n\n"
        f"{opciones}\n\n"
        f"¿Cuál te queda mejor? 😊"
    )


def _agregar_mensaje(numero: str, role: str, content: str) -> None:
    conversaciones.setdefault(numero, [])
    conversaciones[numero].append({'role': role, 'content': content})
    if len(conversaciones[numero]) > MAX_HISTORIAL:
        conversaciones[numero] = conversaciones[numero][-MAX_HISTORIAL:]


def _obtener_historial_cliente(numero: str) -> dict:
    try:
        phone = _normalizar_numero(numero)
        r = requests.get(
            f'{_base_url()}/api/agent/client-history',
            params={'phone': phone},
            headers=_obtener_headers(),
            timeout=5
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error(f"Error obteniendo historial: {e}")
        return {'exists': False}


def _manejar_asesor(numero: str) -> str:
    """Respuesta cuando el cliente quiere hablar con un asesor humano."""
    numero_asesor = os.getenv('ASESOR_WHATSAPP', '')
    if numero_asesor:
        return (
            f"¡Claro! 😊 Te conecto con una de nuestras asesoras.\n\n"
            f"📲 Escríbenos directamente aquí:\n"
            f"wa.me/{numero_asesor}\n\n"
            f"También puedes seguir chateando conmigo si prefieres 💜"
        )
    return (
        f"¡Por supuesto! 😊 Una de nuestras asesoras estará encantada de ayudarte.\n\n"
        f"📲 Escríbenos directamente y te atendemos de inmediato.\n\n"
        f"También puedo seguir ayudándote por aquí si lo prefieres 💜"
    )


def _manejar_confirmacion_cita(numero: str, accion: str) -> str:
    try:
        phone = _normalizar_numero(numero)
        r = requests.get(
            f'{_base_url()}/api/agent/client-history',
            params={'phone': phone},
            headers=_obtener_headers(),
            timeout=5
        )
        data = r.json()

        if not data.get('exists'):
            return (
                "No encontré citas asociadas a tu número 😔\n"
                "¿Quieres agendar una nueva cita? Con gusto te ayudo 🌸"
            )

        citas = data.get('appointments', [])
        proxima = next((c for c in citas if c['status'] == 'confirmed'), None)

        if not proxima:
            return (
                "No tienes citas confirmadas próximas 😔\n"
                "¿Quieres agendar una? 🌸"
            )

        nombre = data['full_name'].split()[0]

        if accion == 'confirmar':
            return (
                f"✅ ¡Perfecto {nombre}! Tu cita está confirmada.\n\n"
                f"💆 {proxima['service']}\n"
                f"📅 {proxima['scheduled_at']}\n\n"
                f"¡Te esperamos con mucho cariño! 💜"
            )
        elif accion == 'cancelar':
            requests.patch(
                f'{_base_url()}/api/agent/appointments/{proxima.get("id")}/cancel',
                headers=_obtener_headers(),
                timeout=10
            )
            return (
                f"Entendido {nombre}, cancelamos tu cita 😔\n\n"
                f"💆 {proxima['service']}\n"
                f"📅 {proxima['scheduled_at']}\n\n"
                f"Cuando quieras reagendar, aquí estaré 🌸"
            )
        elif accion == 'reagendar':
            contexto = (
                f"[REAGENDAR] Servicio: {proxima['service']} | "
                f"ID cita: {proxima.get('id')} | "
                f"Pregunta qué día prefiere para la nueva cita."
            )
            _agregar_mensaje(numero, 'user', contexto)
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
            headers=_obtener_headers(),
            timeout=5
        )
        data = r.json()

        if not data.get('exists'):
            return None

        citas = data.get('appointments', [])
        cita_encuesta = next(
            (c for c in citas if c.get('survey_sent') and not c.get('survey_rating')),
            None
        )

        if not cita_encuesta:
            return None

        requests.patch(
            f'{_base_url()}/api/agent/appointments/{cita_encuesta["id"]}/survey',
            json={'rating': calificacion},
            headers=_obtener_headers(),
            timeout=10
        )

        nombre = data['full_name'].split()[0]
        if calificacion >= 4:
            return (
                f"¡Gracias {nombre}! 🌟 Nos alegra muchísimo saber que tuviste una gran experiencia.\n\n"
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


def _extraer_token(texto: str, token: str) -> str | None:
    if token not in texto:
        return None
    parte = texto.split(token)[1].strip()
    # Extraer hasta cierre del JSON
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


def _llamar_llm(system: str, mensajes: list, max_tokens: int = 500) -> str:
    """Centraliza las llamadas al LLM."""
    respuesta = client.messages.create(
        model='claude-haiku-4-5-20251001',
        max_tokens=max_tokens,
        system=system,
        messages=mensajes
    )
    return respuesta.content[0].text


def _construir_system(servicios_raw: list) -> str:
    fecha_actual = datetime.now().strftime('%A %d de %B de %Y')
    servicios_texto = _obtener_servicios_texto(servicios_raw)
    return (
        SYSTEM_PROMPT
        .replace('{fecha_actual}', fecha_actual)
        .replace('{servicios}', servicios_texto)
    )


def procesar_mensaje(numero: str, mensaje: str) -> str:

    mensaje_lower = mensaje.lower().strip()

    # ── Acciones especiales ─────────────────────────────────────────────────
    if mensaje_lower in ['confirmar', 'cancelar', 'reagendar']:
        return _manejar_confirmacion_cita(numero, mensaje_lower)

    # Detectar solicitud de asesor
    palabras_asesor = ['asesor', 'asesora', 'humano', 'persona', 'hablar con alguien',
                       'agente', 'representante', 'ayuda humana']
    if any(p in mensaje_lower for p in palabras_asesor):
        return _manejar_asesor(numero)

    # Detectar calificación de encuesta
    if mensaje_lower in ['1', '2', '3', '4', '5']:
        resultado = _guardar_calificacion(numero, int(mensaje_lower))
        if resultado:
            return resultado

    es_primer_mensaje = numero not in conversaciones
    servicios_raw = _obtener_servicios_raw()

    # ── Primer mensaje: inyectar contexto del cliente ───────────────────────
    if es_primer_mensaje:
        historial = _obtener_historial_cliente(numero)
        if historial.get('exists'):
            citas = historial.get('appointments', [])
            ultimo_servicio = citas[0]['service'] if citas else None
            contexto = (
                f"[CTX:CLIENTE_CONOCIDO] "
                f"Nombre: {historial['full_name']} | "
                f"Último servicio: {ultimo_servicio or 'ninguno'} | "
                f"Salúdalo por su nombre y menciona su último servicio de forma natural."
            )
            _agregar_mensaje(numero, 'user', contexto)

    # ── Selección de servicio por número ────────────────────────────────────
    if mensaje_lower.strip().isdigit() and numero in servicios_categoria:
        idx = int(mensaje_lower.strip()) - 1
        servicios_mostrados = servicios_categoria[numero]
        if 0 <= idx < len(servicios_mostrados):
            servicio = servicios_mostrados[idx]
            mins = servicio.get('duration_minutes', 0)
            duracion = f"{mins//60}h {mins%60:02d}min" if mins >= 60 else f"{mins} min"
            respuesta = (
                f"¿Confirmás que querés agendar *{servicio['name']}*? 😊\n\n"
                f"💰 ${float(servicio['price']):,.0f} · ⏱ {duracion}"
            )
            contexto_servicio = (
                f"[CTX:SERVICIO] "
                f"Nombre: {servicio['name']} | ID: {servicio['id']} | "
                f"Precio: ${float(servicio['price']):,.0f} | Duración: {mins}min"
            )
            _agregar_mensaje(numero, 'user', contexto_servicio)
            _agregar_mensaje(numero, 'assistant', respuesta)
            return respuesta

    # ── Selección de categoría ───────────────────────────────────────────────
    categoria_detectada = None
    mapa_numeros = {
        '1': 'facial', '2': 'corporal', '3': 'capilar',
        '4': 'sueroterapia', '5': 'masaje'
    }

    if mensaje_lower.strip() in mapa_numeros and numero not in servicios_categoria:
        categoria_detectada = mapa_numeros[mensaje_lower.strip()]
    elif mensaje_lower.strip() in CATEGORIAS:
        categoria_detectada = mensaje_lower.strip()

    if categoria_detectada:
        ultima_categoria[numero] = categoria_detectada
        servicios_categoria.pop(numero, None)
        respuesta = _respuesta_categoria(numero, categoria_detectada, servicios_raw)
        _agregar_mensaje(numero, 'user', mensaje)
        _agregar_mensaje(numero, 'assistant', respuesta)
        return respuesta

    # ── Flujo LLM ────────────────────────────────────────────────────────────
    system = _construir_system(servicios_raw)
    _agregar_mensaje(numero, 'user', mensaje)

    texto_respuesta = _llamar_llm(system, conversaciones[numero])
    _agregar_mensaje(numero, 'assistant', texto_respuesta)

    # Interceptar CONTACTAR_ASESOR
    if 'CONTACTAR_ASESOR' in texto_respuesta:
        respuesta_asesor = _manejar_asesor(numero)
        conversaciones[numero][-1]['content'] = respuesta_asesor
        return respuesta_asesor

    # Interceptar CONSULTAR_DISPONIBILIDAD
    if 'CONSULTAR_DISPONIBILIDAD:' in texto_respuesta:
        return _manejar_consulta_disponibilidad(numero, texto_respuesta, system)

    # Interceptar AGENDAR_CITA
    if 'AGENDAR_CITA:' in texto_respuesta:
        resultado = _agendar_cita(numero, texto_respuesta)
        conversaciones[numero][-1]['content'] = resultado
        return resultado

    return texto_respuesta


def _manejar_consulta_disponibilidad(numero: str, texto: str, system: str) -> str:
    try:
        json_str = _extraer_token(texto, 'CONSULTAR_DISPONIBILIDAD:')
        if not json_str:
            raise ValueError("Token no encontrado")
        datos = json.loads(json_str)
        fecha = datos['fecha']
    except Exception as e:
        logger.error(f"CONSULTAR_DISPONIBILIDAD malformado: {e} — {texto}")
        respuesta_error = "Tuve un problema consultando la disponibilidad 😔 ¿Me repites el día?"
        conversaciones[numero][-1]['content'] = respuesta_error
        return respuesta_error

    slots = _slots_disponibles(fecha)
    resultado_tool = _formatear_slots(fecha, slots)

    # Reemplazar token en historial
    conversaciones[numero][-1]['content'] = f"[Consulté disponibilidad: {fecha}]"

    tool_msg = {
        'role': 'user',
        'content': (
            f"[SISTEMA] Disponibilidad para {fecha}:\n{resultado_tool}\n"
            f"Muestra estos horarios al cliente exactamente como están."
        )
    }

    respuesta_final = _llamar_llm(
        system,
        conversaciones[numero] + [tool_msg],
        max_tokens=300
    )
    _agregar_mensaje(numero, 'assistant', respuesta_final)
    return respuesta_final


def _agendar_cita(numero: str, texto: str) -> str:
    try:
        json_str = _extraer_token(texto, 'AGENDAR_CITA:')
        if not json_str:
            raise ValueError("Token no encontrado")
        datos = json.loads(json_str)
        datos['servicio_id'] = int(datos['servicio_id'])

        headers = _obtener_headers()

        # Verificar disponibilidad
        if not _verificar_disponibilidad(datos['fecha_cita']):
            dt = datetime.fromisoformat(datos['fecha_cita'])
            fecha = dt.strftime('%Y-%m-%d')
            r = requests.get(
                f'{_base_url()}/api/agent/availability',
                params={'date': fecha},
                headers=headers,
                timeout=5
            )
            slots = [s['label'] for s in r.json().get('available', [])]
            slots_texto = ', '.join(slots[:5]) if slots else 'ninguno disponible'
            return (
                f"😔 El horario {dt.strftime('%d/%m/%Y %H:%M')} ya está ocupado.\n\n"
                f"⏰ Horarios libres ese día: {slots_texto}\n\n"
                f"¿Cuál te viene mejor?"
            )

        # Crear cliente
        r_cliente = requests.post(
            f'{_base_url()}/api/agent/clients',
            json={
                'full_name':    datos['nombre'],
                'phone':        _normalizar_numero(numero),
                'email':        datos.get('correo', ''),
                'birth_date':   datos.get('fecha_nacimiento', ''),
                'address':      datos.get('direccion', ''),
                'skin_type':    datos.get('tipo_piel', ''),
                'allergies':    datos.get('alergias', ''),
                'observations': datos.get('observaciones', '')
            },
            headers=headers,
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
            headers=headers,
            timeout=10
        )
        r_cita.raise_for_status()
        cita = r_cita.json()

        # Limpiar estado
        servicios_categoria.pop(numero, None)
        ultima_categoria.pop(numero, None)
        conversaciones.pop(numero, None)

        return (
            f"✅ *¡Tu cita está confirmada!*\n\n"
            f"👤 {cita['client']}\n"
            f"💆 {cita['service']}\n"
            f"📅 {datos['fecha_cita']}\n"
            f"💰 ${float(cita['price']):,.0f}\n\n"
            f"¡Te esperamos con mucho cariño en Seremyc Sthetic! 💜\n"
            f"Si necesitas algo más, aquí estaré 🌸"
        )

    except json.JSONDecodeError as e:
        logger.error(f"JSON inválido AGENDAR_CITA: {e} — {texto}")
        return "Hubo un problema procesando tu cita 😔 ¿Intentamos de nuevo?"
    except Exception as e:
        logger.error(f"Error agendando cita {numero}: {e}")
        return (
            "Ocurrió un error al agendar 😔\n"
            "Por favor intenta de nuevo o escribe *asesor* para que te ayude una de nosotras 💜"
        )