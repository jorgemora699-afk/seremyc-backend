import os
import json
import logging
import requests
from groq import Groq
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = Groq(api_key=os.getenv('GROQ_API_KEY'))

# ─────────────────────────────────────────
# Estado en memoria (reemplazar por Redis en producción)
# ─────────────────────────────────────────
conversaciones: dict[str, list] = {}
ultima_categoria: dict[str, str] = {}

MAX_HISTORIAL = 20  # Máximo de mensajes por conversación

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
Cuando el cliente mencione el nombre de un servicio o indique cuál quiere, pregunta:
"¿Confirmas que quieres agendar [nombre del servicio]? 😊"
Luego inicia el PASO 3.
Si el cliente dice "sí" o "quiero ese" sin especificar cuál, pregúntale:
"¿Cuál de los servicios te gustaría agendar? Por favor escribe el nombre. 😊"

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


# ─────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────
def _normalizar_numero(numero: str) -> str:
    """Elimina el prefijo 'whatsapp:' y espacios del número."""
    return numero.replace('whatsapp:', '').strip()


def _obtener_headers() -> dict:
    return {
        'X-Agent-Key': os.getenv('AGENT_API_KEY'),
        'Content-Type': 'application/json'
    }


def _base_url() -> str:
    return os.getenv('API_BASE_URL', 'http://localhost:5000')


# ─────────────────────────────────────────
# Obtener servicios raw desde la API
# ─────────────────────────────────────────
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


# ─────────────────────────────────────────
# Formatear servicios para el prompt
# ─────────────────────────────────────────
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


# ─────────────────────────────────────────
# Verificar disponibilidad
# ─────────────────────────────────────────
def _verificar_disponibilidad(fecha_cita: str) -> bool:
    """Verifica si el horario está disponible. fecha_cita: YYYY-MM-DDTHH:MM:00"""
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
        return True  # Si falla la API, dejar pasar y que lo detecte al agendar


# ─────────────────────────────────────────
# Construir respuesta de categoría
# ─────────────────────────────────────────
def _respuesta_categoria(categoria: str, servicios_raw: list) -> str:
    filtrados = [
        s for s in servicios_raw
        if s.get('category', '').lower().strip() == categoria
    ]

    if not filtrados:
        return (
            f"Lo siento, no encontré servicios en la categoría {categoria}. 😔\n"
            f"¿Te gustaría ver otra categoría?"
        )

    texto = f"🌸 Servicios de {categoria.capitalize()}:\n\n"
    for s in filtrados:
        duracion = (
            f"{s['duration_minutes'] // 60}h {s['duration_minutes'] % 60}min"
            if s['duration_minutes'] >= 60
            else f"{s['duration_minutes']} min"
        )
        texto += f"• {s['name']} - {duracion} - ${float(s['price']):,.0f}\n"

    texto += "\n¿Cuál te gustaría agendar? 😊"
    return texto


# ─────────────────────────────────────────
# Obtener slots disponibles para una fecha
# ─────────────────────────────────────────
def _slots_disponibles(fecha: str) -> list[str]:
    """Retorna lista de horarios libres para una fecha YYYY-MM-DD."""
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
    """Formatea los horarios disponibles para mostrarlos al cliente."""
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


# ─────────────────────────────────────────
# Gestión del historial
# ─────────────────────────────────────────
def _agregar_mensaje(numero: str, role: str, content: str) -> None:
    """Agrega un mensaje y recorta el historial si supera MAX_HISTORIAL."""
    conversaciones.setdefault(numero, [])
    conversaciones[numero].append({'role': role, 'content': content})

    # Mantener solo los últimos MAX_HISTORIAL mensajes
    if len(conversaciones[numero]) > MAX_HISTORIAL:
        conversaciones[numero] = conversaciones[numero][-MAX_HISTORIAL:]

def _manejar_confirmacion_cita(numero: str, accion: str) -> str:
    try:
        from infrastructure.database.models import AppointmentModel, ClientModel
        from infrastructure.database.db import db
        from infrastructure.web.flask_app import create_app

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

        if accion == 'confirmar':
            return (
                f"✅ ¡Perfecto! Tu cita está confirmada.\n\n"
                f"💆 {proxima['service']}\n"
                f"📅 {proxima['scheduled_at']}\n\n"
                f"¡Te esperamos en Seremyc Sthetic! 💜"
            )
        else:
            # Cancelar via API
            requests.patch(
                f'{_base_url()}/api/agent/appointments/{proxima.get("id")}/cancel',
                headers=_obtener_headers(),
                timeout=10
            )
            return (
                f"😔 Entendido, hemos cancelado tu cita.\n\n"
                f"Si deseas reagendar, escríbenos cuando quieras. 🌸"
            )

    except Exception as e:
        logger.error(f"Error manejando confirmación: {e}")
        return "Lo siento, ocurrió un error. Por favor contáctanos directamente. 😔"
    
# ─────────────────────────────────────────
# Procesar mensaje entrante
# ─────────────────────────────────────────
def procesar_mensaje(numero: str, mensaje: str) -> str:

    mensaje_lower = mensaje.lower().strip()  

    # Detectar confirmación o cancelación de cita
    if mensaje_lower in ['confirmar', 'cancelar']:
        return _manejar_confirmacion_cita(numero, mensaje_lower)

    es_primer_mensaje = numero not in conversaciones

    mensaje_lower = mensaje.lower().strip()
    servicios_raw = _obtener_servicios_raw()

    # Si es el primer mensaje, inyectar historial en el contexto
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

    # ── Detectar cambio de categoría (siempre, no solo al inicio) ──────────
    categoria_detectada = None

    for cat in CATEGORIAS:
        if cat in mensaje_lower:
            categoria_detectada = cat
            break

    if not categoria_detectada:
        mapa_numeros = {
            '1': 'facial', '2': 'corporal', '3': 'capilar',
            '4': 'sueroterapia', '5': 'masaje'
        }
        categoria_detectada = mapa_numeros.get(mensaje_lower.strip())

    if categoria_detectada:
        # Actualizar (o limpiar) la categoría activa
        ultima_categoria[numero] = categoria_detectada
        respuesta = _respuesta_categoria(categoria_detectada, servicios_raw)
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
    """
    Intercepta el token CONSULTAR_DISPONIBILIDAD emitido por el LLM,
    consulta la API, inyecta el resultado y pide al LLM que continúe.
    """
    try:
        json_str = texto.replace('CONSULTAR_DISPONIBILIDAD:', '').strip()
        datos = json.loads(json_str)
        fecha = datos['fecha']
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Token CONSULTAR_DISPONIBILIDAD malformado: {e} — texto: {texto}")
        respuesta_error = "Lo siento, tuve un problema consultando la disponibilidad. ¿Puedes repetirme el día? 😔"
        conversaciones[numero][-1]['content'] = respuesta_error
        return respuesta_error

    slots = _slots_disponibles(fecha)
    resultado_tool = _formatear_slots(fecha, slots)

    # Inyectar el resultado como mensaje del sistema (tool result)
    tool_result_msg = {
        'role': 'user',
        'content': (
            f"[RESULTADO DE HERRAMIENTA — CONSULTAR_DISPONIBILIDAD]\n"
            f"{resultado_tool}\n"
            f"[FIN RESULTADO]\n\n"
            f"Muéstrale estos horarios al cliente con un mensaje amable."
        )
    }

    # Segunda llamada al LLM con el resultado inyectado
    respuesta_llm2 = client.chat.completions.create(
        model='llama-3.3-70b-versatile',
        messages=[{'role': 'system', 'content': system}]
                 + conversaciones[numero]
                 + [tool_result_msg],
        max_tokens=500
    )

    respuesta_final = respuesta_llm2.choices[0].message.content

    # Reemplazar el token en el historial por la respuesta legible
    conversaciones[numero][-1]['content'] = respuesta_final

    return respuesta_final

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

# ─────────────────────────────────────────
# Agendar cita en la app
# ─────────────────────────────────────────
def _agendar_cita(numero: str, texto: str) -> str:
    try:
        json_str = texto.replace('AGENDAR_CITA:', '').strip()
        datos = json.loads(json_str)

        headers = _obtener_headers()

        # ── Verificar disponibilidad ─────────────────────────────────────
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

        # ── Crear o actualizar cliente ───────────────────────────────────
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

        # ── Crear cita ───────────────────────────────────────────────────
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
        logger.error(f"JSON inválido en AGENDAR_CITA: {e} — texto: {texto}")
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