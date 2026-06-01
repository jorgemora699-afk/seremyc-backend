import os
import json
import logging
import requests
from groq import Groq
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = Groq(api_key=os.getenv('GROQ_API_KEY'))

conversaciones: dict[str, list] = {}
ultima_categoria: dict[str, str] = {}
servicios_categoria: dict[str, list] = {}  # guarda los servicios mostrados por número

MAX_HISTORIAL = 20

CATEGORIAS = ['facial', 'corporal', 'capilar', 'sueroterapia', 'masaje']

SYSTEM_PROMPT = """Eres la asistente virtual de Seremyc Sthetic, un centro de bienestar y estética.
Tu nombre es Sere.

REGLAS IMPORTANTES:
- Tus respuestas NUNCA deben superar 300 palabras
- Nunca listes servicios por tu cuenta, el sistema lo hace automáticamente
- Sigue siempre el flujo definido abajo

MANEJO DE FECHAS:
- Si el cliente da una fecha en lenguaje natural como "el viernes", "la próxima semana", etc., calcula la fecha exacta en formato YYYY-MM-DD.
- Hoy es {fecha_actual}. Usa esta fecha como referencia para calcular fechas relativas.
- Para fechas de nacimiento usa formato DD/MM/YYYY.
- Para citas usa formato YYYY-MM-DDTHH:MM:00.

HERRAMIENTA DISPONIBLE — CONSULTAR_DISPONIBILIDAD:
Cuando necesites conocer los horarios libres de un día, responde EXACTAMENTE así y nada más:
CONSULTAR_DISPONIBILIDAD:{"fecha":"YYYY-MM-DD"}
El sistema te devolverá los horarios disponibles y deberás mostrárselos al cliente.

FLUJO DE CONVERSACIÓN:

PASO 1 — BIENVENIDA:
Saluda brevemente y pregunta qué tipo de servicio busca. Muestra las categorías así:
"¿Qué tipo de servicio te interesa? 🌸
1️⃣ Facial
2️⃣ Corporal
3️⃣ Capilar
4️⃣ Sueroterapia
5️⃣ Masaje"

PASO 2 — SERVICIO ELEGIDO:
El sistema ya mostró los servicios numerados. Cuando el cliente escriba un número o el nombre del servicio, confirma:
"¿Confirmas que quieres agendar [nombre del servicio]? 😊"
Luego inicia el PASO 3.

PASO 3 — RECOLECTAR DATOS (uno por uno, no todos juntos):
Pide cada dato en este orden:
1. Nombre completo
2. Correo electrónico
3. Fecha de nacimiento (DD/MM/YYYY)
4. Dirección
5. Tipo de piel (normal, seca, mixta, grasa, sensible)
6. Alergias (o "ninguna")
7. Observaciones adicionales
8. Día deseado para la cita → cuando el cliente responda, usa CONSULTAR_DISPONIBILIDAD para obtener los horarios libres ese día y mostrárselos.
9. El cliente elige un horario de la lista mostrada → guarda fecha+hora como YYYY-MM-DDTHH:MM:00.

PASO 4 — CONFIRMAR:
Muestra un resumen de todos los datos y pregunta si son correctos.

PASO 5 — AGENDAR:
Solo cuando el cliente confirme, responde EXACTAMENTE con esto y nada más:
AGENDAR_CITA:{"nombre":"...","correo":"...","fecha_nacimiento":"...","direccion":"...","tipo_piel":"...","alergias":"...","observaciones":"...","servicio_id":ID_REAL_DEL_SERVICIO,"fecha_cita":"YYYY-MM-DDTHH:MM:00"}

El servicio_id debe ser el ID numérico del servicio que el cliente eligió, según la lista de SERVICIOS POR CATEGORÍA.

Sé cálida, profesional y usa emojis ocasionalmente. Responde siempre en español. Mensajes cortos y directos."""


def _normalizar_numero(numero: str) -> str:
    return numero.replace('whatsapp:', '').strip()


def _obtener_headers() -> dict:
    return {
        'X-Agent-Key': os.getenv('AGENT_API_KEY'),
        'Content-Type': 'application/json'
    }


def _base_url() -> str:
    return os.getenv('API_BASE_URL', 'http://localhost:5000')


def _obtener_servicios_raw() -> list:
    try:
        r = requests.get(
            f'{_base_url()}/api/agent/services',
            headers=_obtener_headers(),
            timeout=5
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error(f"Error obteniendo servicios: {e}")
        return []


def _obtener_servicios_texto() -> str:
    servicios_raw = _obtener_servicios_raw()
    if not servicios_raw:
        return "Servicios disponibles: consultar con la asistente."

    categorias: dict[str, list] = {}
    for s in servicios_raw:
        cat = s.get('category', 'otro').lower().strip()
        categorias.setdefault(cat, [])
        duracion = (
            f"{s['duration_minutes'] // 60}h {s['duration_minutes'] % 60}min"
            if s['duration_minutes'] >= 60
            else f"{s['duration_minutes']} min"
        )
        categorias[cat].append(
            f"  - {s['name']} (ID: {s['id']}) - {duracion} - ${float(s['price']):,.0f}"
        )

    texto = "SERVICIOS POR CATEGORÍA:\n\n"
    for cat, items in categorias.items():
        texto += f"CATEGORÍA {cat.upper()}:\n"
        texto += "\n".join(items)
        texto += "\n\n"

    return texto


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

        disponibilidad = r.json()
        horas_libres = [s['label'] for s in disponibilidad.get('available', [])]
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
            f"Lo siento, no encontré servicios en la categoría {categoria}. 😔\n"
            f"¿Te gustaría ver otra categoría?"
        )

    # Guardar los servicios mostrados para este número
    servicios_categoria[numero] = filtrados

    texto = f"🌸 Servicios de {categoria.capitalize()}:\n\n"
    for i, s in enumerate(filtrados, 1):
        duracion = (
            f"{s['duration_minutes'] // 60}h {s['duration_minutes'] % 60}min"
            if s['duration_minutes'] >= 60
            else f"{s['duration_minutes']} min"
        )
        texto += f"{i}️⃣ {s['name']} - {duracion} - ${float(s['price']):,.0f}\n"

    texto += "\n¿Cuál te gustaría agendar? Escribe el número o el nombre 😊"
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
        fecha_legible = dt.strftime('%A %d de %B de %Y')
    except ValueError:
        fecha_legible = fecha

    if not slots:
        return (
            f"😔 Lo siento, no hay horarios disponibles para el {fecha_legible}.\n"
            f"¿Te gustaría elegir otro día?"
        )

    opciones = "\n".join(f"  {i + 1}️⃣ {h}" for i, h in enumerate(slots))
    return (
        f"📅 Horarios disponibles para el {fecha_legible}:\n\n"
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
            return "No encontré citas asociadas a tu número. 😔"

        citas = data.get('appointments', [])
        proxima = next(
            (c for c in citas if c['status'] == 'confirmed'),
            None
        )

        if not proxima:
            return "No tienes citas confirmadas próximas. 😔"

        nombre = data['full_name'].split()[0]

        if accion == 'confirmar':
            return (
                f"✅ ¡Perfecto {nombre}! Tu cita está confirmada.\n\n"
                f"💆 {proxima['service']}\n"
                f"📅 {proxima['scheduled_at']}\n\n"
                f"¡Te esperamos en Seremyc Sthetic! 💜"
            )

        elif accion == 'cancelar':
            requests.patch(
                f'{_base_url()}/api/agent/appointments/{proxima.get("id")}/cancel',
                headers=_obtener_headers(),
                timeout=10
            )
            return (
                f"😔 Entendido {nombre}, hemos cancelado tu cita.\n\n"
                f"💆 {proxima['service']}\n"
                f"📅 {proxima['scheduled_at']}\n\n"
                f"Si deseas reagendar, escribe *REAGENDAR* cuando quieras. 🌸"
            )

        elif accion == 'reagendar':
            _agregar_mensaje(numero, 'user', 'REAGENDAR')
            _agregar_mensaje(numero, 'assistant', '')

            contexto = (
                f"[REAGENDAR]\n"
                f"El cliente quiere reagendar su cita de {proxima['service']}.\n"
                f"ID de la cita: {proxima.get('id')}\n"
                f"Servicio ID: {proxima.get('service_id')}\n"
                f"[FIN REAGENDAR]\n\n"
                f"Pregúntale al cliente qué día prefiere para la nueva cita."
            )
            _agregar_mensaje(numero, 'user', contexto)

            return (
                f"¡Claro {nombre}! Vamos a reagendar tu cita de *{proxima['service']}*. 🗓️\n\n"
                f"¿Qué día te quedaría mejor?"
            )

    except Exception as e:
        logger.error(f"Error manejando acción {accion}: {e}")
        return "Lo siento, ocurrió un error. Por favor contáctanos directamente. 😔"


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
                f"¡Muchas gracias {nombre}! 🌟 Nos alegra mucho que hayas tenido una "
                f"gran experiencia.\n\n"
                f"¿Quieres dejarnos algún comentario adicional? 😊\n"
                f"(O escribe *NO* si no deseas agregar nada)"
            )
        else:
            return (
                f"Gracias {nombre} por tu honestidad. 🙏\n\n"
                f"Lamentamos que tu experiencia no haya sido la mejor. "
                f"¿Nos puedes contar qué podríamos mejorar? 😔"
            )

    except Exception as e:
        logger.error(f"Error guardando calificación: {e}")
        return None


# ─────────────────────────────────────────
# Procesar mensaje entrante
# ─────────────────────────────────────────
def procesar_mensaje(numero: str, mensaje: str) -> str:

    mensaje_lower = mensaje.lower().strip()

    # Detectar confirmación, cancelación o reagendamiento
    if mensaje_lower in ['confirmar', 'cancelar', 'reagendar']:
        return _manejar_confirmacion_cita(numero, mensaje_lower)

    # Detectar calificación de encuesta (solo si hay encuesta pendiente)
    if mensaje_lower in ['1', '2', '3', '4', '5']:
        resultado = _guardar_calificacion(numero, int(mensaje_lower))
        if resultado:
            return resultado

    es_primer_mensaje = numero not in conversaciones
    servicios_raw = _obtener_servicios_raw()

    # Inyectar historial si es el primer mensaje
    if es_primer_mensaje:
        historial = _obtener_historial_cliente(numero)
        if historial.get('exists'):
            nombre = historial['full_name'].split()[0]
            citas = historial.get('appointments', [])
            ultimo_servicio = citas[0]['service'] if citas else None

            contexto = f"[CONTEXTO DEL CLIENTE]\nEste cliente ya nos ha visitado antes.\n"
            contexto += f"Nombre: {historial['full_name']}\n"
            if ultimo_servicio:
                contexto += f"Último servicio: {ultimo_servicio}\n"
            contexto += "[FIN CONTEXTO]\n\n"
            contexto += "Saluda al cliente por su nombre y menciona su último servicio de forma natural."
            _agregar_mensaje(numero, 'user', contexto)

    # ── Detectar selección de servicio por número ──────────────────────────
    if mensaje_lower.strip().isdigit() and numero in servicios_categoria:
        idx = int(mensaje_lower.strip()) - 1
        servicios_mostrados = servicios_categoria[numero]
        if 0 <= idx < len(servicios_mostrados):
            servicio = servicios_mostrados[idx]
            respuesta = (
                f"¿Confirmas que quieres agendar *{servicio['name']}*? 😊\n\n"
                f"💰 Precio: ${float(servicio['price']):,.0f}\n"
                f"⏱ Duración: {servicio['duration_minutes']} min"
            )
            # Guardar el servicio seleccionado en el contexto
            contexto_servicio = (
                f"[SERVICIO SELECCIONADO]\n"
                f"Nombre: {servicio['name']}\n"
                f"ID: {servicio['id']}\n"
                f"Precio: ${float(servicio['price']):,.0f}\n"
                f"[FIN SERVICIO SELECCIONADO]"
            )
            _agregar_mensaje(numero, 'user', contexto_servicio)
            _agregar_mensaje(numero, 'assistant', respuesta)
            return respuesta

    # ── Detectar selección de categoría ───────────────────────────────────
    categoria_detectada = None
    mapa_numeros = {
        '1': 'facial', '2': 'corporal', '3': 'capilar',
        '4': 'sueroterapia', '5': 'masaje'
    }

    # Solo detectar categoría si el mensaje es exactamente un número o categoría sola
    if mensaje_lower.strip() in mapa_numeros and numero not in servicios_categoria:
        categoria_detectada = mapa_numeros[mensaje_lower.strip()]
    elif mensaje_lower.strip() in CATEGORIAS:
        categoria_detectada = mensaje_lower.strip()

    if categoria_detectada:
        ultima_categoria[numero] = categoria_detectada
        # Limpiar servicios anteriores al cambiar de categoría
        servicios_categoria.pop(numero, None)
        respuesta = _respuesta_categoria(numero, categoria_detectada, servicios_raw)
        _agregar_mensaje(numero, 'user', mensaje)
        _agregar_mensaje(numero, 'assistant', respuesta)
        return respuesta

    # ── Flujo normal con el LLM ─────────────────────────────────────────────
    fecha_actual = datetime.now().strftime('%A %d de %B de %Y')
    servicios_texto = _obtener_servicios_texto()

    system = (
        SYSTEM_PROMPT.replace('{fecha_actual}', fecha_actual)
        + f"\n\n{servicios_texto}"
    )

    _agregar_mensaje(numero, 'user', mensaje)

    respuesta_llm = client.chat.completions.create(
        model='llama-3.3-70b-versatile',
        messages=[{'role': 'system', 'content': system}] + conversaciones[numero],
        max_tokens=1000
    )

    texto_respuesta = respuesta_llm.choices[0].message.content
    _agregar_mensaje(numero, 'assistant', texto_respuesta)

    # ── Interceptar CONSULTAR_DISPONIBILIDAD ────────────────────────────────
    if texto_respuesta.strip().startswith('CONSULTAR_DISPONIBILIDAD:'):
        return _manejar_consulta_disponibilidad(numero, texto_respuesta.strip(), system)

    # ── Interceptar AGENDAR_CITA ─────────────────────────────────────────────
    if texto_respuesta.strip().startswith('AGENDAR_CITA:'):
        resultado = _agendar_cita(numero, texto_respuesta.strip())
        conversaciones[numero][-1]['content'] = resultado
        return resultado

    return texto_respuesta


# ─────────────────────────────────────────
# Manejar tool call CONSULTAR_DISPONIBILIDAD
# ─────────────────────────────────────────
def _manejar_consulta_disponibilidad(numero: str, texto: str, system: str) -> str:
    try:
        json_str = texto.replace('CONSULTAR_DISPONIBILIDAD:', '').strip()
        datos = json.loads(json_str)
        fecha = datos['fecha']
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Token CONSULTAR_DISPONIBILIDAD malformado: {e}")
        respuesta_error = "Lo siento, tuve un problema consultando la disponibilidad. ¿Puedes repetirme el día? 😔"
        conversaciones[numero][-1]['content'] = respuesta_error
        return respuesta_error

    slots = _slots_disponibles(fecha)
    resultado_tool = _formatear_slots(fecha, slots)

    tool_result_msg = {
        'role': 'user',
        'content': (
            f"[RESULTADO DE HERRAMIENTA — CONSULTAR_DISPONIBILIDAD]\n"
            f"{resultado_tool}\n"
            f"[FIN RESULTADO]\n\n"
            f"Muéstrale estos horarios al cliente con un mensaje amable."
        )
    }

    respuesta_llm2 = client.chat.completions.create(
        model='llama-3.3-70b-versatile',
        messages=[{'role': 'system', 'content': system}]
                 + conversaciones[numero]
                 + [tool_result_msg],
        max_tokens=500
    )

    respuesta_final = respuesta_llm2.choices[0].message.content
    conversaciones[numero][-1]['content'] = respuesta_final
    return respuesta_final


# ─────────────────────────────────────────
# Agendar cita en la app
# ─────────────────────────────────────────
def _agendar_cita(numero: str, texto: str) -> str:
    try:
        json_str = texto.replace('AGENDAR_CITA:', '').strip()
        datos = json.loads(json_str)

        headers = _obtener_headers()

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
                f"😔 Lo siento, el horario {dt.strftime('%d/%m/%Y %H:%M')} ya está ocupado.\n\n"
                f"⏰ Horarios disponibles para ese día: {slots_texto}\n\n"
                f"¿Te gustaría alguno de estos horarios?"
            )

        r_cliente = requests.post(
            f'{_base_url()}/api/agent/clients',
            json={
                'full_name':    datos['nombre'],
                'phone':        _normalizar_numero(numero),
                'email':        datos['correo'],
                'birth_date':   datos['fecha_nacimiento'],
                'address':      datos['direccion'],
                'skin_type':    datos['tipo_piel'],
                'allergies':    datos['alergias'],
                'observations': datos['observaciones']
            },
            headers=headers,
            timeout=10
        )
        r_cliente.raise_for_status()
        cliente_id = r_cliente.json()['client_id']

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

        # Limpiar estado de la conversación al agendar exitosamente
        servicios_categoria.pop(numero, None)
        ultima_categoria.pop(numero, None)

        return (
            f"✅ ¡Tu cita ha sido agendada exitosamente!\n\n"
            f"📋 Resumen:\n"
            f"👤 {cita['client']}\n"
            f"💆 {cita['service']}\n"
            f"📅 {datos['fecha_cita']}\n"
            f"💰 ${float(cita['price']):,.0f}\n\n"
            f"Te esperamos en Seremyc Sthetic 💜"
        )

    except json.JSONDecodeError as e:
        logger.error(f"JSON inválido en AGENDAR_CITA: {e}")
        return (
            "Lo siento, hubo un problema al procesar los datos de tu cita. 😔\n"
            "Por favor intenta de nuevo."
        )
    except Exception as e:
        logger.error(f"Error agendando cita para {numero}: {e}")
        return (
            "Lo siento, ocurrió un error al agendar tu cita 😔\n"
            "Por favor intenta de nuevo o contáctanos directamente."
        )