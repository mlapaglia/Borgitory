import os
import socket
import subprocess
from pathlib import Path

def ensure_certificates():
    """Generate self-signed certificate that actually works"""
    cert_dir = Path("/app/ssl")
    cert_path = cert_dir / "cert.pem"
    key_path = cert_dir / "key.pem"
    
    # Create directory if it doesn't exist
    cert_dir.mkdir(exist_ok=True)
    
    if not cert_path.exists() or not key_path.exists():
        print("🔒 Generating self-signed certificate...")
        
        # Collect all possible access methods
        san_entries = [
            'DNS:localhost',
            'IP:127.0.0.1',
            'IP:::1'
        ]
        
        # Add hostname
        hostname = socket.gethostname()
        san_entries.append(f'DNS:{hostname}')
        
        # Add container IP
        try:
            container_ip = socket.gethostbyname(hostname)
            san_entries.append(f'IP:{container_ip}')
        except:
            pass
        
        # Add user-specified hosts
        if extra_hosts := os.environ.get('CERT_HOSTS'):
            for host in extra_hosts.split(','):
                host = host.strip()
                if host.replace('.', '').replace(':', '').isdigit():  # IP address
                    san_entries.append(f'IP:{host}')
                else:  # hostname
                    san_entries.append(f'DNS:{host}')
        
        san_string = ','.join(san_entries)
        
        # Generate the certificate
        subprocess.run([
            'openssl', 'req', '-x509', '-newkey', 'rsa:2048',
            '-keyout', str(key_path), '-out', str(cert_path),
            '-days', '365', '-nodes',
            '-subj', f'/CN={hostname}',
            '-addext', f'subjectAltName={san_string}'
        ], check=True)
        
        # Set proper permissions
        os.chmod(key_path, 0o600)
        os.chmod(cert_path, 0o644)
        
        print(f"✅ Certificate generated for: {san_string}")
    else:
        print("✅ SSL certificate already exists")
    
    return str(cert_path), str(key_path)