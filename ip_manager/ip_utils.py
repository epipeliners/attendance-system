"""
Utility functions untuk IP Manager.
"""
from flask import request

def get_client_ip():
    """
    Dapatkan IP address client dari request.
    Handle berbagai proxy/load balancer.
    """
    # Cek header X-Forwarded-For (untuk proxy/load balancer)
    if request.headers.get('X-Forwarded-For'):
        ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()
    # Cek header X-Real-IP (untuk nginx)
    elif request.headers.get('X-Real-IP'):
        ip = request.headers.get('X-Real-IP')
    # Fallback ke remote_addr
    else:
        ip = request.remote_addr
    return ip

def get_user_agent():
    """Dapatkan user agent dari request."""
    return request.headers.get('User-Agent')

def log_user_ip(user_id, action='login'):
    """
    Helper function untuk mencatat IP user.
    Bisa dipanggil langsung dari route manapun.
    """
    from ip_manager.ip_model import IPModel
    ip = get_client_ip()
    ua = get_user_agent()
    return IPModel.log(user_id, ip, ua, action)