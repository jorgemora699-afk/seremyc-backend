import os
import json
import requests
from groq import Groq

client = Groq(api_key=os.getenv('GROQ_API_KEY'))

conversaciones = {}
estado_conversacion = {}
ultima_categoria = {}

CATEGORIAS = ['facial', 'corporal', 'capilar', 'sueroterapia', 'masaje']

SYSTEM_PROMPT = """Eres la asistente virtual de Seremyc Sthetic, un centro de bienestar y estética.
Tu nombre es Sere.

REGLAS IMPORTANTES:
- Tus respuestas NUNCA deben superar 300 palabras
- Nunca listes servicios por tu cuenta, el sistema lo hace automáticamente
- Sigue siempre el flujo definido abajo

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
Cuando el cliente elija un servicio y quiera agendar, pide cada dato por separado en este orden:
1. Nombre completo
2. Correo electrónico
3. Fecha de nacimiento (DD/MM/YYYY)
4. Dirección
5. Tipo de piel (normal, seca, mixta, grasa, sensible)
6. Alergias (o "ninguna")
7. Observaciones adicionales
8. Fecha y hora deseada para la cita

PASO 4 — CONFIRMAR:
Muestra un resumen de todos los datos y pregunta si son correctos.

PASO 5 — AGENDAR:
Solo cuando el cliente confirme, responde EXACTAMENTE con esto y nada más:
AGENDAR_CITA:{"nombre":"...","correo":"...","fecha_nacimiento":"...","direccion":"...","tipo_piel":"...","alergias":"...","observaciones":"...","servicio_id":ID_REAL_DEL_SERVICIO,"fecha_cita":"YYYY-MM-DDTHH:MM:00"}

El servicio_id debe ser el ID numérico del servicio que el cliente eligió, según la lista de SERVICIOS POR CATEGORÍA.

Sé cálida, profesional y usa emojis ocasionalmente. Responde siempre en español. Mensajes cortos y directos."""


# ─────────────────────────────────────────
# Obtener servicios raw desde la API
# ─────────────────────────────────────────
def _obtener_servicios_raw() -> list:
    try:
        base_url = os.getenv('API_BASE_URL', 'http://localhost:5000')
        headers  = {'X-Agent-Key': os.getenv('AGENT_API_KEY')}
        r = requests.get(
            f'{base_url}/api/agent/services',
            headers=headers,
            timeout=5
        )
        return r.json()
    except Exception:
        return []


# ─────────────────────────────────────────
# Formatear servicios para el prompt
# ─────────────────────────────────────────
def _obtener_servicios() -> str:
    servicios_raw = _obtener_servicios_raw()
    if not servicios_raw:
        return "Servicios disponibles: consultar con la asistente."

    categorias = {}
    for s in servicios_raw:
        cat = s.get('category', 'otro').lower().strip()
        if cat not in categorias:
            categorias[cat] = []
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
# Procesar mensaje entrante
# ─────────────────────────────────────────
def procesar_mensaje(numero: str, mensaje: str) -> str:

    if numero not in conversaciones:
        conversaciones[numero] = []

    mensaje_lower = mensaje.lower().strip()
    servicios_raw = _obtener_servicios_raw()

    # Detectar categoría solo si el cliente NO está en conversación activa
    categoria_detectada = None

    if numero not in ultima_categoria:
        for cat in CATEGORIAS:
            if cat in mensaje_lower:
                categoria_detectada = cat
                break

        if not categoria_detectada:
            mapa_numeros = {
                '1': 'facial',
                '2': 'corporal',
                '3': 'capilar',
                '4': 'sueroterapia',
                '5': 'masaje'
            }
            for num, cat in mapa_numeros.items():
                if mensaje_lower.strip() == num:
                    categoria_detectada = cat
                    break

    if categoria_detectada:
        ultima_categoria[numero] = categoria_detectada
        respuesta = _respuesta_categoria(categoria_detectada, servicios_raw)
        conversaciones[numero].append({'role': 'user', 'content': mensaje})
        conversaciones[numero].append({'role': 'assistant', 'content': respuesta})
        return respuesta

    # Flujo normal con el LLM
    servicios_texto = _obtener_servicios()
    system = SYSTEM_PROMPT + f"\n\n{servicios_texto}"

    conversaciones[numero].append({
        'role': 'user',
        'content': mensaje
    })

    respuesta_llm = client.chat.completions.create(
        model='-3.3-llama70b-versatile',
        messages=[{'role': 'system', 'content': system}] + conversaciones[numero],
        max_tokens=1000
    )

    texto_respuesta = respuesta_llm.choices[0].message.content

    conversaciones[numero].append({
        'role': 'assistant',
        'content': texto_respuesta
    })

    if texto_respuesta.strip().startswith('AGENDAR_CITA:'):
        resultado = _agendar_cita(numero, texto_respuesta.strip())
        conversaciones[numero][-1]['content'] = resultado
        return resultado

    return texto_respuesta


# ─────────────────────────────────────────
# Agendar cita en la app
# ─────────────────────────────────────────
def _agendar_cita(numero: str, texto: str) -> str:

    try:
        json_str = texto.replace('AGENDAR_CITA:', '').strip()
        datos = json.loads(json_str)

        base_url = os.getenv('API_BASE_URL', 'http://localhost:5000')
        headers  = {
            'X-Agent-Key':  os.getenv('AGENT_API_KEY'),
            'Content-Type': 'application/json'
        }

        # 1. Crear o actualizar cliente
        r_cliente = requests.post(
            f'{base_url}/api/agent/clients',
            json={
                'full_name':    datos['nombre'],
                'phone':        numero.replace('whatsapp:', ''),
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

        cliente_id = r_cliente.json()['client_id']

        # 2. Crear cita
        r_cita = requests.post(
            f'{base_url}/api/agent/appointments',
            json={
                'client_id':    cliente_id,
                'service_id':   datos['servicio_id'],
                'scheduled_at': datos['fecha_cita'],
                'notes':        f'Agendado por WhatsApp desde {numero}'
            },
            headers=headers,
            timeout=10
        )

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

    except Exception:
        return (
            "Lo siento, ocurrió un error al agendar tu cita 😔\n"
            "Por favor intenta de nuevo o contáctanos directamente."
        )