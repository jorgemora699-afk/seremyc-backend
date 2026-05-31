import os
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from infrastructure.web.whatsapp_sender import enviar_mensaje

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────
# Tarea: enviar recordatorios 24h antes
# ─────────────────────────────────────────
def enviar_recordatorios():
    from infrastructure.database.db import db
    from infrastructure.database.models import AppointmentModel
    from infrastructure.web.flask_app import create_app

    app = create_app()

    with app.app_context():
        try:
            ahora = datetime.now()
            manana_inicio = (ahora + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            manana_fin = manana_inicio.replace(
                hour=23, minute=59, second=59
            )

            citas = AppointmentModel.query.filter(
                AppointmentModel.scheduled_at >= manana_inicio,
                AppointmentModel.scheduled_at <= manana_fin,
                AppointmentModel.status == 'confirmed',
                AppointmentModel.reminder_sent == False
            ).all()

            logger.info(f"Recordatorios: {len(citas)} citas para mañana")

            for cita in citas:
                cliente = cita.client
                servicio = cita.service

                if not cliente or not (cliente.phone or cliente.whatsapp):
                    continue

                telefono = cliente.whatsapp or cliente.phone
                hora = cita.scheduled_at.strftime('%H:%M')
                fecha = cita.scheduled_at.strftime('%d/%m/%Y')
                nombre = cliente.full_name.split()[0]

                mensaje = (
                    f"¡Hola {nombre}! 🌸 Te recordamos que mañana tienes una cita en *Seremyc Sthetic*.\n\n"
                    f"📋 *Detalle de tu cita:*\n"
                    f"💆 {servicio.name if servicio else 'Servicio'}\n"
                    f"📅 {fecha} a las {hora}\n\n"
                    f"¿Confirmas tu asistencia?\n"
                    f"✅ Responde *CONFIRMAR* para confirmar\n"
                    f"❌ Responde *CANCELAR* si no puedes asistir\n\n"
                    f"¡Te esperamos! 💜"
                )

                enviado = enviar_mensaje(telefono, mensaje)

                if enviado:
                    cita.reminder_sent = True
                    db.session.commit()
                    logger.info(f"Recordatorio enviado a {telefono} — cita {cita.id}")

        except Exception as e:
            logger.error(f"Error en enviar_recordatorios: {e}")


# ─────────────────────────────────────────
# Inicializar scheduler
# ─────────────────────────────────────────
def init_scheduler():
    scheduler = BackgroundScheduler(timezone='America/Bogota')

    # Ejecutar cada hora
    scheduler.add_job(
        enviar_recordatorios,
        'interval',
        hours=1,
        id='recordatorios',
        replace_existing=True
    )

    scheduler.start()
    logger.info("Scheduler iniciado — recordatorios activos")
    return scheduler