import os
import subprocess
from pathlib import Path

def ensure_certificates():
    """Generate self-signed certificate for the user's IP"""
    cert_dir = Path("/app/ssl")
    cert_path = cert_dir / "cert.pem"
    key_path = cert_dir / "key.pem"
    
    # Create directory if it doesn't exist
    cert_dir.mkdir(exist_ok=True)
    
    if not cert_path.exists() or not key_path.exists():
        print("🔒 Generating self-signed certificate...")
        
        # Get the IP address the user will access the app from
        server_ip = os.environ.get('SERVER_IP')
        if not server_ip:
            print("❌ SERVER_IP environment variable is required!")
            print("   Example: -e SERVER_IP=192.168.1.100")
            exit(1)
        
        # Generate certificate for localhost and the user's IP
        san_string = f'DNS:localhost,IP:127.0.0.1,IP:{server_ip}'
        
        subprocess.run([
            'openssl', 'req', '-x509', '-newkey', 'rsa:2048',
            '-keyout', str(key_path), '-out', str(cert_path),
            '-days', '365', '-nodes',
            '-subj', f'/CN={server_ip}',
            '-addext', f'subjectAltName={san_string}'
        ], check=True)
        
        # Set proper permissions
        os.chmod(key_path, 0o600)
        os.chmod(cert_path, 0o644)
        
        print(f"✅ Certificate generated for: {san_string}")
    else:
        print("✅ SSL certificate already exists")
    
    return str(cert_path), str(key_path)