from dotenv import load_dotenv
load_dotenv()

from infrastructure.web.flask_app import create_app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=False, host='0.0.0.0', port=5000)