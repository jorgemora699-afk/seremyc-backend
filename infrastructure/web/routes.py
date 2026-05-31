def register_routes(app):
    from infrastructure.controllers.auth_controller import auth_bp
    from infrastructure.controllers.client_controller import client_bp
    from infrastructure.controllers.service_controller import service_bp
    from infrastructure.controllers.appointment_controller import appointment_bp
    from infrastructure.controllers.finance_controller import finance_bp
    from infrastructure.controllers.inventory_controller import inventory_bp
    from infrastructure.controllers.promotion_controller import promotion_bp
    from infrastructure.controllers.dashboard_controller import dashboard_bp
    from infrastructure.controllers.photo_controller import photo_bp
    from infrastructure.web.agent_api import agent_bp
    from infrastructure.web.whatsapp_webhook import whatsapp_bp


    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(client_bp, url_prefix='/api/clients')
    app.register_blueprint(service_bp, url_prefix='/api/services')
    app.register_blueprint(appointment_bp, url_prefix='/api/appointments')
    app.register_blueprint(finance_bp, url_prefix='/api/finances')
    app.register_blueprint(inventory_bp, url_prefix='/api/inventory')
    app.register_blueprint(promotion_bp, url_prefix='/api/promotions')
    app.register_blueprint(dashboard_bp, url_prefix='/api/dashboard')
    app.register_blueprint(photo_bp, url_prefix='/api/photos')
    app.register_blueprint(agent_bp)
    app.register_blueprint(whatsapp_bp)