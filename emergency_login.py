from app import app
import webbrowser
import time

print("🚑 Emergency Login Helper")
print("1. Aplikasi akan jalan di port 5001")
print("2. Buka http://127.0.0.1:5001/emergency")

@app.route('/emergency')
def emergency():
    from flask import session, redirect, url_for
    user = query_db('SELECT * FROM users WHERE username = ?', ['admin'], one=True)
    if user:
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['role'] = user['role']
        return redirect(url_for('dashboard'))
    return "Admin not found"

if __name__ == '__main__':
    webbrowser.open('http://127.0.0.1:5001/emergency')
    app.run(port=5001, debug=True)