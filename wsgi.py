# wsgi.py
import os
import sys

# Tambahkan path saat ini ke sys.path
sys.path.insert(0, os.path.dirname(__file__))

# Import create_app dari folder app
from app import create_app

# Buat aplikasi - PASTI bernama 'application' (bukan 'app')
application = create_app(os.environ.get('FLASK_CONFIG'))

# Untuk running lokal
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    application.run(host='0.0.0.0', port=port, debug=True)