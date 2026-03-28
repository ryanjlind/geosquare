import os
from pathlib import Path

from dotenv import load_dotenv

from app import create_app

def load_environment() -> None:
    load_dotenv(Path(__file__).resolve().parent / '.env')

load_environment()

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', '8000')), debug=True)
