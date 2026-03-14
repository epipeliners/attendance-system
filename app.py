import os
import sys

print("="*50)
print("DEBUG: Starting app.py")
print(f"DEBUG: Python version: {sys.version}")
print(f"DEBUG: Current directory: {os.getcwd()}")
print(f"DEBUG: Files in directory: {os.listdir('.')}")
print("="*50)

try:
    from app import create_app
    print("DEBUG: Successfully imported create_app from app")
except Exception as e:
    print(f"DEBUG: Failed to import create_app: {e}")

try:
    # Pastikan variabel bernama 'app'
    app = create_app(os.environ.get('FLASK_CONFIG'))
    print(f"DEBUG: App created successfully: {app}")
    print(f"DEBUG: App type: {type(app)}")
except Exception as e:
    print(f"DEBUG: Failed to create app: {e}")
    app = None

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    if app:
        app.run(host='0.0.0.0', port=port, debug=True)
    else:
        print("DEBUG: App is None, cannot run")