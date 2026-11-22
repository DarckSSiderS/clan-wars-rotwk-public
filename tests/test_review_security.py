import asyncio
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ssl
import subprocess
import sys
from threading import Thread

import aiohttp
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import pytest

from app.services.ladder_service import BFMELadderService


def test_malformed_form_header_is_bounded_in_a_separate_process():
    # ReDoS regression stays local, with a hard timeout; no production requests.
    code = '''
from python_multipart.multipart import parse_options_header
header = 'application/x-www-form-urlencoded; !="' + chr(92) * 10000
parse_options_header(header)
'''
    subprocess.run([sys.executable, "-c", code], check=True, timeout=5, capture_output=True)


@pytest.fixture
def untrusted_https_server(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=1))
            .sign(key, hashes.SHA256()))
    cert_path, key_path = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"[]")

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        yield f"https://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_real_ladder_connector_rejects_untrusted_certificates(db, monkeypatch, untrusted_https_server):
    service = BFMELadderService()
    service.proxy = None

    async def load(session, *_args, **_kwargs):
        async with session.get(untrusted_https_server) as response:
            await response.read()
        return []

    monkeypatch.setattr(service, "_load_api_replays", load)
    with pytest.raises(aiohttp.ClientConnectorCertificateError):
        asyncio.run(service.fetch_and_save_matches_from_api(db))
