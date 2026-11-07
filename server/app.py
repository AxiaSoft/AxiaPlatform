"""AXIASOFT API and development server.

Production deployments should still move to a hardened ASGI/WSGI stack and
PostgreSQL. This module is a development server, but it is now defensive:

* every database connection is closed on every path (no wedged SQLite locks);
* JSON writes are atomic per request (BEGIN IMMEDIATE / COMMIT / ROLLBACK);
* fixed-name rate-limit buckets, per-email lockout, body-size and header limits;
* bounded in-flight requests per client and overall, plus a slow-header guard;
* restrictive security headers, no directory listing, no static caching surprises.

Abuse control can be tuned with environment variables documented in README.md.
"""
from http.server import HTTPServer, SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote
from datetime import datetime, timedelta, timezone
from email.utils import formatdate
from socketserver import ThreadingMixIn
import base64
import hashlib
import hmac
import http.client
import io
import json
import os
import re
import secrets
import signal
import socket
import sqlite3
import sys
import threading
import time
import uuid

import db as database
from db import connect, init, ROOT, DB_PATH
from security import (
    ConcurrencyGuard,
    Lockout,
    RateLimiter,
    client_from_forwarded,
    env_float,
    env_int,
    normalize_ip,
)

PUBLIC = ROOT / 'public'
SESSION_DAYS = 7
STATUSES = ['Submitted', 'Under Review', 'Requirements Analysis', 'Quotation Sent', 'Awaiting Confirmation', 'In Development', 'Testing', 'Ready for Delivery', 'Delivered', 'Cancelled']

# --------------------------------------------------------------------------- #
# Tunables (environment overridable, documented in README)                     #
# --------------------------------------------------------------------------- #
MAX_INFLIGHT_PER_CLIENT = env_int('AXIA_MAX_INFLIGHT_PER_CLIENT', 16, 1, 256)
MAX_BODY_BYTES = env_int('AXIA_MAX_BODY_BYTES', 100_000, 1_024, 1_000_000)
MAX_HEADER_BYTES = env_int('AXIA_MAX_HEADER_BYTES', 16_384, 1_024, 131_072)
HEADER_TIMEOUT = env_float('AXIA_HEADER_TIMEOUT', 10.0, 1.0, 120.0)
SOCKET_TIMEOUT = env_float('AXIA_SOCKET_TIMEOUT', 20.0, 2.0, 300.0)
TRUSTED_PROXIES = {p.strip() for p in (os.environ.get('AXIA_TRUSTED_PROXIES') or '').split(',') if p.strip()}

RATE_WINDOW = 60
# On bigger machines allow proportionally more concurrent work (the ceiling that
# actually protects the process), while per-client limits stay strict.
CPU_HINT = os.cpu_count() or 2
MAX_INFLIGHT = env_int('AXIA_MAX_INFLIGHT', min(1024, max(256, CPU_HINT * 32)), 8, 8192)
RATE_LIMITS = {
    # bucket            per-window limit (per client)
    'api_read': env_int('AXIA_RATE_READ', 1800),
    'identity': env_int('AXIA_RATE_IDENTITY', 3000),
    'api_write': env_int('AXIA_RATE_WRITE', 120),
    'auth': env_int('AXIA_RATE_AUTH', 30),
    'register': env_int('AXIA_RATE_REGISTER', 12),
    'support': env_int('AXIA_RATE_SUPPORT', 10),
    'static': env_int('AXIA_RATE_STATIC', 3000),
}
WRITE_COST = {'register': 1}
LOCKOUT_THRESHOLD = env_int('AXIA_LOCKOUT_THRESHOLD', 8, 2, 100)
LOCKOUT_SECONDS = env_int('AXIA_LOCKOUT_SECONDS', 900, 30, 86_400)

RATE = RateLimiter()
GUARD = ConcurrencyGuard(MAX_INFLIGHT, MAX_INFLIGHT_PER_CLIENT)
LOGIN_LOCKOUT = Lockout(LOCKOUT_THRESHOLD, LOCKOUT_SECONDS)

# In-flight database connections owned by the current request.
_local = threading.local()
STATIC_TYPES = {
    '.html': 'text/html; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.svg': 'image/svg+xml',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.webp': 'image/webp',
    '.ico': 'image/x-icon',
    '.woff2': 'font/woff2',
    '.woff': 'font/woff',
    '.txt': 'text/plain; charset=utf-8',
    '.xml': 'application/xml; charset=utf-8',
    '.webmanifest': 'application/manifest+json',
}
BIG_ASSET_TYPES = {'.png', '.jpg', '.jpeg', '.webp', '.woff2', '.woff', '.ico'}
# Buckets that must always be counted per network address, never per session.
PER_IP_BUCKETS = {'auth', 'register'}
# Routes that monitoring may poll freely: never rate limited, never shed.
UNMETERED_PATHS = {'/api/health'}
IMMUTABLE_DIRS = ('/fonts/', '/brand/')

EMAIL_RE = re.compile(r'[^@\s]+@[^@\s]+\.[^@\s]+')
SLUG_RE = re.compile(r'[a-z0-9-]{3,100}')
SAFE_PATH_RE = re.compile(r'^/[a-z0-9._/-]*$', re.IGNORECASE)


# --------------------------------------------------------------------------- #
# Small helpers                                                               #
# --------------------------------------------------------------------------- #
def now():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.isoformat(timespec='seconds')


def hash_password(pw, salt=None):
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac('sha256', pw.encode(), salt, 310000)
    return 'pbkdf2_sha256$310000$' + base64.b64encode(salt).decode() + '$' + base64.b64encode(dk).decode()


def verify_password(pw, encoded):
    try:
        alg, rounds, salt, expected = encoded.split('$')
        return hmac.compare_digest(hashlib.pbkdf2_hmac('sha256', pw.encode(), base64.b64decode(salt), int(rounds)), base64.b64decode(expected))
    except Exception:
        return False


def token_hash(v):
    return hashlib.sha256(v.encode()).hexdigest()


def clean(s, n=5000):
    return str(s or '').strip()[:n]


def public_user(row):
    return {'id': row['id'], 'name': row['name'], 'email': row['email'], 'role': row['role'], 'phone': row['phone']}


def product_out(r):
    x = dict(r)
    try:
        x['features'] = json.loads(x['features'])
    except Exception:
        x['features'] = []
    try:
        x['technologies'] = json.loads(x['technologies'])
    except Exception:
        x['technologies'] = []
    return x


def ref(prefix):
    return prefix + '-' + uuid.uuid4().hex[:8].upper()


def acquire_db():
    """Open and track a connection for the current request."""
    conn = connect()
    tracked = getattr(_local, 'conns', None)
    if tracked is None:
        tracked = _local.conns = []
    tracked.append(conn)
    return conn


def close_request_connections():
    tracked = getattr(_local, 'conns', None) or []
    while tracked:
        try:
            tracked.pop().close()
        except Exception:
            pass


def json_readable(raw):
    """Reject deeply nested JSON so recursive decoding cannot exhaust the stack."""
    depth = 0
    in_str = False
    esc = False
    for ch in raw:
        if in_str:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in '{[':
            depth += 1
            if depth > 12:
                return False
        elif ch in '}]':
            depth -= 1
    return True


def is_json(payload):
    return isinstance(payload, dict)


class Reject(Exception):
    """Raised mid-request to send a clean error response."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


# --------------------------------------------------------------------------- #
# Server                                                                      #
# --------------------------------------------------------------------------- #
class AxiServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = env_int('AXIA_BACKLOG', 256, 16, 4096)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stopping = threading.Event()

    def process_request(self, request, client_address):
        # Bound total threads: refuse the connection rather than queueing forever.
        if GUARD.active >= MAX_INFLIGHT:
            GUARD.rejected += 1
            body = (b'{"error":"The server is at capacity. Please retry in a moment."}')
            head = (b'HTTP/1.1 503 Service Unavailable\r\n'
                    b'Content-Type: application/json; charset=utf-8\r\n'
                    b'Content-Length: ' + str(len(body)).encode() + b'\r\n'
                    b'Retry-After: 3\r\nCache-Control: no-store\r\n'
                    b'X-Content-Type-Options: nosniff\r\nConnection: close\r\n\r\n')
            try:
                request.settimeout(1.0)
                request.sendall(head + body)
            except OSError:
                pass
            try:
                request.close()
            except OSError:
                pass
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            try:
                request.close()
            except OSError:
                pass

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (BrokenPipeError, ConnectionResetError, TimeoutError, socket.timeout)):
            return
        super().handle_error(request, client_address)


class Handler(SimpleHTTPRequestHandler):
    server_version = 'AXIASOFT'
    sys_version = ''
    protocol_version = 'HTTP/1.1'
    timeout = SOCKET_TIMEOUT

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(PUBLIC), **kw)

    # -- logging / identity -------------------------------------------------- #
    def log_message(self, fmt, *args):
        print('%s - %s' % (self.client, fmt % args))

    def setup(self):
        self.client = normalize_ip(self.client_address[0])
        self._started = time.time()
        self._responded = False
        self._session_cookie = None
        self._new_csrf = None
        super().setup()

    def finish(self):
        close_request_connections()
        super().finish()

    def handle_one_request(self):
        close_request_connections()
        try:
            super().handle_one_request()
        finally:
            close_request_connections()

    def client_ip(self):
        try:
            return client_from_forwarded(self.headers.get('X-Forwarded-For'), self.client_address[0], TRUSTED_PROXIES)
        except Exception:
            return self.client

    # -- connection gate ----------------------------------------------------- #
    def _gate(self):
        """Best-effort in-flight accounting for every request."""
        if not GUARD.acquire(self.client):
            self._responded = True
            self._send_json({'error': 'The server is handling a high volume of requests. Please retry in a moment.'}, 503, extra={'Retry-After': '2'})
            return False
        self._gate_held = True
        return True

    def _release_gate(self):
        if getattr(self, '_gate_held', False):
            self._gate_held = False
            GUARD.release(self.client)

    # -- responses ----------------------------------------------------------- #
    def _send_json(self, obj, status=200, extra=None):
        raw = json.dumps(obj, ensure_ascii=False).encode()
        self._responded = True
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def send_json(self, obj, status=200, headers=None):
        # Backwards-compatible alias used by the route handlers.
        self._send_json(obj, status, headers)

    def body(self):
        try:
            n = int(self.headers.get('Content-Length', '0') or 0)
        except (TypeError, ValueError):
            raise Reject('Invalid request size.', 400)
        if n < 0 or n > MAX_BODY_BYTES:
            # The declared body is not read, so this connection cannot be reused.
            self.close_connection = True
            raise Reject('Request is too large.', 413)
        raw = self.rfile.read(n) if n else b'{}'
        if not raw:
            raw = b'{}'
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError:
            raise Reject('Request body must be UTF-8.', 400)
        if not json_readable(text):
            raise Reject('Request body is malformed.', 400)
        try:
            data = json.loads(text)
        except Exception:
            raise Reject('Invalid JSON request.', 400)
        if data is None:
            data = {}
        if not is_json(data):
            raise Reject('Request body must be a JSON object.', 400)
        return data

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        self.send_header('Permissions-Policy', 'camera=(), microphone=(), geolocation=(), payment=(), usb=()')
        self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'; media-src 'self'")
        if os.environ.get('AXIA_HSTS') == '1':
            self.send_header('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
        if getattr(self, '_session_cookie', None):
            self.send_header('Set-Cookie', self._session_cookie)
            self._session_cookie = None
        if getattr(self, '_new_csrf', None):
            self.send_header('X-CSRF-Token', self._new_csrf)
            self._new_csrf = None
        super().end_headers()

    # -- auth ---------------------------------------------------------------- #
    def session_token(self):
        raw = ''
        for part in self.headers.get('Cookie', '').split(';'):
            part = part.strip()
            if part.startswith('axia_session='):
                raw = part.split('=', 1)[1]
        return raw

    def auth(self):
        raw = self.session_token()
        if not raw or len(raw) > 200:
            return None
        db = acquire_db()
        row = db.execute(
            "SELECT u.*,s.csrf,s.expires_at FROM sessions s JOIN users u ON u.id=s.user_id "
            "WHERE s.token_hash=? AND s.expires_at>? AND u.active=1",
            (token_hash(raw), iso(now())),
        ).fetchone()
        return dict(row) if row else None

    def audit(self, user, action, entity, eid):
        db = acquire_db()
        db.execute('INSERT INTO audit_logs(actor_id,action,entity,entity_id) VALUES(?,?,?,?)',
                   (user['id'] if user else None, action, entity, str(eid)))

    def create_session(self, db, uid):
        raw = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(24)
        exp = iso(now() + timedelta(days=SESSION_DAYS))
        db.execute('INSERT INTO sessions(token_hash,user_id,csrf,expires_at) VALUES(?,?,?,?)',
                   (token_hash(raw), uid, csrf, exp))
        self._new_csrf = csrf
        secure = '; Secure' if os.environ.get('AXIA_COOKIE_SECURE') == '1' else ''
        self._session_cookie = ('axia_session=' + raw + '; HttpOnly; SameSite=Strict; Path=/; Max-Age='
                                + str(SESSION_DAYS * 86400) + secure)

    def check_csrf(self, user):
        if not user:
            return False
        supplied = self.headers.get('X-CSRF-Token', '')
        return bool(supplied and hmac.compare_digest(supplied, user['csrf']))

    # -- rate limiting ------------------------------------------------------- #
    def rate_key(self, bucket):
        """Choose what a limit is counted against.

        Identity-style buckets (sign-in, registration) are always per network
        address. Content buckets prefer the session, so several genuine visitors
        sharing one office NAT or mobile carrier address do not exhaust each
        other's allowance, while an anonymous flood is still bounded per address.
        """
        if bucket in PER_IP_BUCKETS:
            return 'ip:' + self.client_ip()
        token = self.session_token()
        if token and len(token) <= 200:
            return 'session:' + token_hash(token)[:32]
        return 'ip:' + self.client_ip()

    def rate(self, bucket, cost=1):
        limit = RATE_LIMITS.get(bucket, 60)
        allowed, retry, _ = RATE.hit(bucket, self.rate_key(bucket), limit, RATE_WINDOW, cost)
        if not allowed:
            self._send_json({'error': 'Too many requests. Please wait a moment and try again.'}, 429,
                            extra={'Retry-After': str(retry)})
        return allowed

    # -- header guard -------------------------------------------------------- #
    def parse_request(self):
        """Parse the request line and headers with size and time limits.

        Mirrors ``BaseHTTPRequestHandler.parse_request`` but caps the *total*
        header block, enforces a deadline across all header reads (slow-header
        / slowloris defence) and validates the Host header.
        """
        self.command = ''
        self.request_version = ''
        self.requestline = ''
        self.close_connection = True
        raw = getattr(self, 'raw_requestline', b'') or b''
        if not raw:
            return False
        if len(raw) > 8192:
            self.send_error(414, 'Request-URI or request line too long')
            return False
        self.requestline = raw.decode('iso-8859-1').rstrip('\r\n')
        words = self.requestline.split()
        if len(words) == 3:
            self.command, self.path, self.request_version = words
        elif len(words) == 2:
            self.command, self.path = words
            self.request_version = 'HTTP/0.9'
        else:
            self.send_error(400, 'Bad request syntax')
            return False
        if not self.command or not re.fullmatch(r'[A-Z]{3,10}', self.command):
            self.send_error(400, 'Bad request method')
            return False
        if not self.path.startswith('/'):
            self.send_error(400, 'Bad request target')
            return False
        deadline = getattr(self, '_started', time.time()) + HEADER_TIMEOUT
        block = []
        total = 0
        try:
            while True:
                if time.time() > deadline:
                    self.send_error(408, 'Request header timeout')
                    return False
                line = self.rfile.readline(8192)
                total += len(line)
                if total > MAX_HEADER_BYTES:
                    self.send_error(431, 'Request header fields too large')
                    return False
                if not line:
                    return False
                if line in (b'\r\n', b'\n'):
                    break
                if not line.endswith(b'\n'):
                    self.send_error(431, 'Request header line too long')
                    return False
                block.append(line)
            self.headers = http.client.parse_headers(io.BytesIO(b''.join(block)), _class=self.MessageClass)
        except (socket.timeout, TimeoutError):
            try:
                self.send_error(408, 'Request header timeout')
            except OSError:
                pass
            return False
        except Exception:
            return False
        host = self.headers.get('Host', '')
        if host and not re.fullmatch(r'[A-Za-z0-9.\-:\[\]]{1,255}', host):
            self.send_error(400, 'Bad Host header')
            return False
        conntype = self.headers.get('Connection', '')
        if conntype.lower() == 'close':
            self.close_connection = True
        elif conntype.lower() == 'keep-alive' and self.protocol_version >= 'HTTP/1.1':
            self.close_connection = False
        return True

    # -- dispatch ------------------------------------------------------------ #
    def do_GET(self):
        self._handle('GET')

    def do_HEAD(self):
        self._handle('HEAD')

    def do_POST(self):
        self._handle('POST')

    def do_PUT(self):
        self._handle('PUT')

    def do_DELETE(self):
        self._handle('DELETE')

    def do_PATCH(self):
        self._responded = True
        self._send_json({'error': 'Method not allowed'}, 405, extra={'Allow': 'GET, HEAD, POST, PUT, DELETE'})

    def do_OPTIONS(self):
        self._responded = True
        self._send_json({'error': 'Method not allowed'}, 405, extra={'Allow': 'GET, HEAD, POST, PUT, DELETE'})

    def do_TRACE(self):
        self._responded = True
        self._send_json({'error': 'Method not allowed'}, 405, extra={'Allow': 'GET, HEAD, POST, PUT, DELETE'})

    def _handle(self, method):
        # Monitoring must never be rate limited or shed: answer before any gate.
        try:
            path_only = urlparse(self.path).path
        except Exception:
            path_only = ''
        if path_only in UNMETERED_PATHS and method in ('GET', 'HEAD'):
            self._send_json({'status': 'ok', 'service': 'AXIASOFT'})
            return
        if not self._gate():
            self._release_gate()
            return
        try:
            path = urlparse(self.path).path
            if path.startswith('/api/'):
                if method in ('GET', 'HEAD'):
                    bucket = 'identity' if path == '/api/me' else 'api_read'
                else:
                    bucket = 'api_write'
                if not self.rate(bucket):
                    return
                if method in ('GET', 'HEAD'):
                    self.api_get(path, parse_qs(urlparse(self.path).query))
                else:
                    self.dispatch_write(method)
            elif method in ('GET', 'HEAD'):
                self.serve_static(path)
            else:
                self._responded = True
                self._send_json({'error': 'Method not allowed'}, 405, extra={'Allow': 'GET'})
        except Reject as exc:
            self._responded = True
            if exc.status >= 400 and exc.status != 405:
                self.close_connection = True
            self._send_json({'error': str(exc)}, exc.status, extra={'Connection': 'close'} if self.close_connection else None)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            if not self._responded:
                print('API error:', repr(exc))
                self._responded = True
                self._send_json({'error': 'Request could not be completed'}, 500)
        finally:
            self._release_gate()
            close_request_connections()

    def dispatch_write(self, method):
        d = self.body()
        self.api_write(urlparse(self.path).path, method, d)

    # -- static files -------------------------------------------------------- #
    def serve_static(self, path):
        if not SAFE_PATH_RE.match(path) or '..' in path or '\\' in path or '\x00' in path:
            return self._not_found()
        decoded = unquote(path)
        if decoded != path and not SAFE_PATH_RE.match(decoded):
            return self._not_found()
        if path.endswith('/'):
            path += 'index.html'
        if path.startswith('/.') or '/.' in path:
            return self._not_found()
        target = (PUBLIC / path.lstrip('/')).resolve()
        try:
            target.relative_to(PUBLIC.resolve())
        except ValueError:
            return self._not_found()
        if not target.is_file():
            return self._not_found()
        if not self.rate('static'):
            return
        suffix = target.suffix.lower()
        ctype = STATIC_TYPES.get(suffix, 'application/octet-stream')
        try:
            size = target.stat().st_size
            with target.open('rb') as fh:
                self._responded = True
                self.send_response(200)
                self.send_header('Content-Type', ctype)
                self.send_header('Content-Length', str(size))
                if path in IMMUTABLE_DIRS or path.startswith(IMMUTABLE_DIRS):
                    self.send_header('Cache-Control', 'public, max-age=604800')
                elif suffix in BIG_ASSET_TYPES:
                    self.send_header('Cache-Control', 'public, max-age=86400')
                else:
                    self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                if self.command != 'HEAD':
                    while True:
                        chunk = fh.read(65536)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except OSError:
            self._not_found()

    def _not_found(self):
        self._responded = True
        page = PUBLIC / '404.html'
        if page.is_file():
            raw = page.read_bytes()
            self.send_response(404)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            if self.command != 'HEAD':
                try:
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    pass
        else:
            self._send_json({'error': 'Not found'}, 404)

    def list_directory(self, path):
        # Directory listings are never served.
        self._responded = True
        self.send_error(404)
        return None

    # ------------------------------------------------------------------ #
    # Read routes                                                         #
    # ------------------------------------------------------------------ #
    def api_get(self, p, q):
        db = acquire_db()
        user = self.auth()

        if p == '/api/products':
            cat = clean((q.get('category') or [''])[0], 40)
            if cat:
                rows = db.execute('SELECT * FROM products WHERE published=1 AND category=? ORDER BY id', (cat,)).fetchall()
            else:
                rows = db.execute('SELECT * FROM products WHERE published=1 ORDER BY id').fetchall()
            self._send_json([product_out(r) for r in rows]); return

        if p.startswith('/api/products/'):
            slug = unquote(p.rsplit('/', 1)[-1])[:100]
            if not SLUG_RE.fullmatch(slug):
                self._send_json({'error': 'Product not found'}, 404); return
            r = db.execute('SELECT * FROM products WHERE slug=? AND published=1', (slug,)).fetchone()
            if r:
                self._send_json(product_out(r))
            else:
                self._send_json({'error': 'Product not found'}, 404)
            return

        if p == '/api/me':
            self._send_json({'user': public_user(user) if user else None, 'csrf': user['csrf'] if user else None}); return

        if p == '/api/orders':
            if not user:
                self._send_json({'error': 'Please sign in first'}, 401); return
            if user['role'] == 'admin':
                rows = db.execute('SELECT o.*,p.title product_title FROM orders o JOIN products p ON p.id=o.product_id ORDER BY o.created_at DESC LIMIT 500').fetchall()
            else:
                rows = db.execute('SELECT o.*,p.title product_title FROM orders o JOIN products p ON p.id=o.product_id WHERE o.user_id=? ORDER BY o.created_at DESC', (user['id'],)).fetchall()
            self._send_json([dict(x) for x in rows]); return

        if p == '/api/support':
            if not user:
                self._send_json({'error': 'Please sign in first'}, 401); return
            if user['role'] == 'admin':
                rows = db.execute('SELECT * FROM tickets ORDER BY created_at DESC LIMIT 500').fetchall()
            else:
                rows = db.execute('SELECT * FROM tickets WHERE user_id=? ORDER BY created_at DESC', (user['id'],)).fetchall()
            tickets = []
            for r in rows:
                item = dict(r)
                item['messages'] = [dict(m) for m in db.execute(
                    'SELECT tm.message,tm.created_at,u.name sender FROM ticket_messages tm LEFT JOIN users u ON u.id=tm.sender_id WHERE tm.ticket_id=? ORDER BY tm.created_at',
                    (r['id'],))]
                tickets.append(item)
            self._send_json(tickets); return

        if p == '/api/refunds':
            if not user:
                self._send_json({'error': 'Please sign in first'}, 401); return
            if user['role'] == 'admin':
                rows = db.execute('SELECT r.*,o.number order_number FROM refunds r JOIN orders o ON o.id=r.order_id ORDER BY r.created_at DESC LIMIT 500').fetchall()
            else:
                rows = db.execute('SELECT r.*,o.number order_number FROM refunds r JOIN orders o ON o.id=r.order_id WHERE r.user_id=? ORDER BY r.created_at DESC', (user['id'],)).fetchall()
            self._send_json([dict(r) for r in rows]); return

        if p.startswith('/api/admin/'):
            if not user or user['role'] != 'admin':
                self._send_json({'error': 'Administrator access required'}, 403); return

            if p == '/api/admin/overview':
                counts = {
                    'customers': db.execute("SELECT count(*) FROM users WHERE role='customer'").fetchone()[0],
                    'orders': db.execute('SELECT count(*) FROM orders').fetchone()[0],
                    'pending': db.execute("SELECT count(*) FROM orders WHERE status IN ('Submitted','Under Review','Requirements Analysis')").fetchone()[0],
                    'active': db.execute("SELECT count(*) FROM orders WHERE status IN ('In Development','Testing')").fetchone()[0],
                    'completed': db.execute("SELECT count(*) FROM orders WHERE status='Delivered'").fetchone()[0],
                    'tickets': db.execute("SELECT count(*) FROM tickets WHERE status='Open'").fetchone()[0],
                    'refunds': db.execute("SELECT count(*) FROM refunds WHERE status='Under review'").fetchone()[0],
                    'published': db.execute('SELECT count(*) FROM products WHERE published=1').fetchone()[0],
                }
                orders = db.execute('SELECT o.*,p.title product_title FROM orders o JOIN products p ON p.id=o.product_id ORDER BY o.created_at DESC LIMIT 500').fetchall()
                products = db.execute('SELECT * FROM products ORDER BY id').fetchall()
                tickets = db.execute('SELECT * FROM tickets ORDER BY created_at DESC LIMIT 8').fetchall()
                self._send_json({'counts': counts, 'orders': [dict(x) for x in orders],
                                 'products': [product_out(x) for x in products],
                                 'tickets': [dict(x) for x in tickets]}); return

            if p == '/api/admin/customers':
                term = clean((q.get('q') or [''])[0], 120)
                like = '%' + term.replace('%', r'\%').replace('_', r'\_') + '%'
                rows = db.execute(
                    "SELECT u.id,u.name,u.email,u.phone,u.role,u.active,u.created_at,"
                    "(SELECT count(*) FROM orders o WHERE o.user_id=u.id) order_count,"
                    "(SELECT count(*) FROM tickets t WHERE t.user_id=u.id) ticket_count "
                    "FROM users u WHERE u.role='customer' AND (?='' OR u.name LIKE ? ESCAPE '\\' OR u.email LIKE ? ESCAPE '\\' OR u.phone LIKE ? ESCAPE '\\') "
                    "ORDER BY u.created_at DESC LIMIT 500", (term, like, like, like)).fetchall()
                self._send_json({'customers': [dict(x) for x in rows], 'total': len(rows)}); return

            if p == '/api/admin/audit':
                try:
                    limit = max(1, min(int((q.get('limit') or ['100'])[0]), 200))
                except Exception:
                    limit = 100
                rows = db.execute(
                    'SELECT a.id,a.action,a.entity,a.entity_id,a.created_at,u.name actor_name,u.email actor_email '
                    'FROM audit_logs a LEFT JOIN users u ON u.id=a.actor_id ORDER BY a.created_at DESC,a.id DESC LIMIT ?',
                    (limit,)).fetchall()
                self._send_json([dict(x) for x in rows]); return

            m = re.fullmatch(r'/api/admin/orders/(\d+)/history', p)
            if m:
                rows = db.execute(
                    'SELECT h.id,h.status,h.note,h.created_at,u.name actor_name FROM order_history h '
                    'LEFT JOIN users u ON u.id=h.actor_id WHERE h.order_id=? ORDER BY h.created_at,h.id',
                    (int(m.group(1)),)).fetchall()
                self._send_json([dict(x) for x in rows]); return

        self._send_json({'error': 'Not found'}, 404)

    # ------------------------------------------------------------------ #
    # Write routes                                                        #
    # ------------------------------------------------------------------ #
    def api_write(self, p, method, d):
        db = acquire_db()
        user = self.auth()

        if p == '/api/register':
            if method != 'POST':
                self._send_json({'error': 'Method not allowed'}, 405); return
            if not self.rate('register'):
                return
            name = clean(d.get('name'), 120)
            email = clean(d.get('email'), 254).lower()
            phone = clean(d.get('phone'), 40)
            pw = d.get('password')
            pw = pw if isinstance(pw, str) else ''
            if len(name) < 2 or not EMAIL_RE.fullmatch(email) or len(pw) < 12 or len(pw) > 256:
                self._send_json({'error': 'Enter your name, a valid email, and a password of at least 12 characters.'}, 400); return
            exists = db.execute('SELECT 1 FROM users WHERE email=?', (email,)).fetchone()
            if exists:
                self._send_json({'error': 'An account with that email may already exist.'}, 409); return
            ph = hash_password(pw)
            try:
                db.execute('BEGIN IMMEDIATE')
                cur = db.execute('INSERT INTO users(name,email,phone,password_hash) VALUES(?,?,?,?)', (name, email, phone, ph))
                uid = cur.lastrowid
                db.execute('COMMIT')
            except sqlite3.IntegrityError:
                self._rollback(db)
                self._send_json({'error': 'An account with that email may already exist.'}, 409); return
            except sqlite3.OperationalError:
                self._rollback(db)
                self._send_json({'error': 'The service is briefly busy. Please try again.'}, 503); return
            except Exception:
                self._rollback(db)
                raise
            self.create_session(db, uid)
            self.audit({'id': uid}, 'register', 'user', uid)
            self._send_json({'user': public_user(db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone())}, 201); return

        if p == '/api/login':
            if method != 'POST':
                self._send_json({'error': 'Method not allowed'}, 405); return
            if not self.rate('auth'):
                return
            email = clean(d.get('email'), 254).lower()
            pw = d.get('password')
            pw = pw if isinstance(pw, str) else ''
            locked, retry = LOGIN_LOCKOUT.is_locked(email)
            if locked:
                self._send_json({'error': 'Too many failed sign-in attempts. Please try again later.'}, 429,
                                {'Retry-After': str(retry)})
                return
            row = db.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
            if not row or not verify_password(pw, row['password_hash']) or not row['active']:
                LOGIN_LOCKOUT.register_failure(email)
                self._send_json({'error': 'Email or password is incorrect.'}, 401); return
            LOGIN_LOCKOUT.clear(email)
            self.create_session(db, row['id'])
            self.audit(dict(row), 'login', 'user', row['id'])
            self._send_json({'user': public_user(row)}); return

        if p == '/api/logout':
            if method != 'POST':
                self._send_json({'error': 'Method not allowed'}, 405); return
            token = self.session_token()
            if token:
                db.execute('DELETE FROM sessions WHERE token_hash=?', (token_hash(token),))
            self._session_cookie = 'axia_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'
            self._send_json({'ok': True}); return

        if not user:
            self._send_json({'error': 'Please sign in first'}, 401); return
        if not self.check_csrf(user):
            self._send_json({'error': 'Session security check failed. Refresh and try again.'}, 403); return

        # ---- customer writes -------------------------------------------- #
        if p == '/api/orders':
            if method != 'POST':
                self._send_json({'error': 'Method not allowed'}, 405); return
            try:
                product_id = int(d.get('product_id'))
            except (TypeError, ValueError):
                self._send_json({'error': 'Select an orderable website or application product.'}, 400); return
            product = db.execute('SELECT * FROM products WHERE id=? AND published=1', (product_id,)).fetchone()
            name = clean(d.get('name'), 120)
            email = clean(d.get('email'), 254).lower()
            phone = clean(d.get('phone'), 40)
            desc = clean(d.get('description'), 3000)
            if not product or product['category'] == 'Aurion':
                self._send_json({'error': 'Select an orderable website or application product.'}, 400); return
            if not name or not EMAIL_RE.fullmatch(email) or len(phone) < 5 or len(desc) < 15:
                self._send_json({'error': 'Please complete all required fields. Project details must be at least 15 characters.'}, 400); return
            number = 'AX-' + now().strftime('%y%m') + '-' + secrets.token_hex(3).upper()
            try:
                db.execute('BEGIN IMMEDIATE')
                cur = db.execute(
                    'INSERT INTO orders(number,user_id,product_id,name,email,phone,description,requirements,contact_method) VALUES(?,?,?,?,?,?,?,?,?)',
                    (number, user['id'], product['id'], name, email, phone, desc, clean(d.get('requirements'), 2000),
                     clean(d.get('contact_method'), 30) or 'Email'))
                oid = cur.lastrowid
                db.execute('INSERT INTO order_history(order_id,status,note,actor_id) VALUES(?,?,?,?)',
                           (oid, 'Submitted', 'Order request received', user['id']))
                db.execute('COMMIT')
            except Exception:
                self._rollback(db)
                raise
            self.audit(user, 'create', 'order', oid)
            self._send_json({'number': number, 'status': 'Submitted'}, 201); return

        if p == '/api/support':
            if method != 'POST':
                self._send_json({'error': 'Method not allowed'}, 405); return
            if not self.rate('support'):
                return
            subject = clean(d.get('subject'), 140)
            message = clean(d.get('message'), 3000)
            if len(subject) < 3 or len(message) < 10:
                self._send_json({'error': 'Please add a subject and a message of at least 10 characters.'}, 400); return
            refno = ref('AXS')
            db.execute('INSERT INTO tickets(ref,user_id,email,subject,message) VALUES(?,?,?,?,?)',
                       (refno, user['id'], user['email'], subject, message))
            self.audit(user, 'create', 'ticket', refno)
            self._send_json({'ref': refno, 'message': 'A support request has been created. Our team will follow up.'}, 201); return

        if p == '/api/refunds':
            if method != 'POST':
                self._send_json({'error': 'Method not allowed'}, 405); return
            try:
                order_id = int(d.get('order_id'))
            except (TypeError, ValueError):
                self._send_json({'error': 'Choose one of your orders and provide a reason.'}, 400); return
            order = db.execute('SELECT * FROM orders WHERE id=? AND user_id=?', (order_id, user['id'])).fetchone()
            reason = clean(d.get('reason'), 2000)
            if not order or len(reason) < 5:
                self._send_json({'error': 'Choose one of your orders and provide a reason.'}, 400); return
            try:
                created = datetime.strptime(order['created_at'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
            except Exception:
                created = now() - timedelta(days=365)
            if now() - created > timedelta(days=14):
                self._send_json({'error': 'This order is outside the 14-calendar-day request window. Contact support if you believe an exception applies.'}, 400); return
            open_one = db.execute("SELECT 1 FROM refunds WHERE order_id=? AND user_id=? AND status IN ('Under review','Approved')",
                                  (order['id'], user['id'])).fetchone()
            if open_one:
                self._send_json({'error': 'A refund request is already open or approved for this order.'}, 409); return
            refno = ref('RFD')
            db.execute('INSERT INTO refunds(ref,order_id,user_id,reason) VALUES(?,?,?,?)',
                       (refno, order['id'], user['id'], reason))
            self.audit(user, 'create', 'refund', refno)
            self._send_json({'ref': refno, 'status': 'Under review'}, 201); return

        # ---- administrator writes --------------------------------------- #
        if p.startswith('/api/admin/') and user['role'] != 'admin':
            self._send_json({'error': 'Administrator access required'}, 403); return

        if p == '/api/admin/tickets/status' and method == 'PUT':
            try:
                tid = int(d.get('id'))
            except (TypeError, ValueError):
                self._send_json({'error': 'A valid ticket id is required.'}, 400); return
            status = d.get('status')
            if status not in ('Open', 'In progress', 'Closed'):
                self._send_json({'error': 'Unknown support status'}, 400); return
            cur = db.execute('UPDATE tickets SET status=? WHERE id=?', (status, tid))
            if not cur.rowcount:
                self._send_json({'error': 'Ticket not found'}, 404); return
            self.audit(user, 'ticket_status', 'ticket', tid)
            self._send_json({'ok': True}); return

        if p == '/api/admin/tickets/reply' and method == 'POST':
            try:
                tid = int(d.get('id'))
            except (TypeError, ValueError):
                self._send_json({'error': 'A valid ticket id is required.'}, 400); return
            message = clean(d.get('message'), 3000)
            if len(message) < 2:
                self._send_json({'error': 'Reply is too short'}, 400); return
            if not db.execute('SELECT 1 FROM tickets WHERE id=?', (tid,)).fetchone():
                self._send_json({'error': 'Ticket not found'}, 404); return
            try:
                db.execute('BEGIN IMMEDIATE')
                db.execute('INSERT INTO ticket_messages(ticket_id,sender_id,message) VALUES(?,?,?)', (tid, user['id'], message))
                db.execute("UPDATE tickets SET status='In progress' WHERE id=?", (tid,))
                db.execute('COMMIT')
            except Exception:
                self._rollback(db)
                raise
            self.audit(user, 'ticket_reply', 'ticket', tid)
            self._send_json({'ok': True}); return

        if p == '/api/admin/orders/status' and method == 'PUT':
            try:
                oid = int(d.get('id'))
            except (TypeError, ValueError):
                self._send_json({'error': 'A valid order id is required.'}, 400); return
            status = clean(d.get('status'), 80)
            note = clean(d.get('note'), 1000)
            if status not in STATUSES:
                self._send_json({'error': 'Unknown order status'}, 400); return
            if not db.execute('SELECT 1 FROM orders WHERE id=?', (oid,)).fetchone():
                self._send_json({'error': 'Order not found'}, 404); return
            try:
                db.execute('BEGIN IMMEDIATE')
                db.execute('UPDATE orders SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?', (status, oid))
                db.execute('INSERT INTO order_history(order_id,status,note,actor_id) VALUES(?,?,?,?)', (oid, status, note, user['id']))
                db.execute('COMMIT')
            except Exception:
                self._rollback(db)
                raise
            self.audit(user, 'status_change', 'order', oid)
            self._send_json({'ok': True}); return

        if p == '/api/admin/products' and method == 'POST':
            slug = clean(d.get('slug'), 100).lower()
            title = clean(d.get('title'), 140)
            cat = clean(d.get('category'), 40)
            summary = clean(d.get('summary'), 300)
            description = clean(d.get('description'), 3000)
            status = clean(d.get('status', 'available'), 20)
            cover = clean(d.get('cover'), 120)
            features = d.get('features', [])
            technologies = d.get('technologies', [])
            if (not SLUG_RE.fullmatch(slug) or not title or cat not in ('Websites', 'Applications', 'Aurion')
                    or status not in ('available', 'showcase') or not summary or not description
                    or not isinstance(features, list) or not isinstance(technologies, list)
                    or len(features) > 20 or len(technologies) > 20):
                self._send_json({'error': 'Check required product fields, category, status and feature lists.'}, 400); return
            if db.execute('SELECT 1 FROM products WHERE slug=?', (slug,)).fetchone():
                self._send_json({'error': 'Slug already exists or product is invalid.'}, 409); return
            features = [clean(x, 100) for x in features if clean(x, 100)]
            technologies = [clean(x, 100) for x in technologies if clean(x, 100)]
            try:
                cur = db.execute(
                    'INSERT INTO products(slug,title,category,summary,description,cover,status,price_label,features,technologies,published) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                    (slug, title, cat, summary, description, cover, status,
                     clean(d.get('price_label'), 80) or 'Request a quote',
                     json.dumps(features, ensure_ascii=False), json.dumps(technologies, ensure_ascii=False),
                     1 if d.get('published', True) in (True, 1, 'true', '1') else 0))
            except sqlite3.IntegrityError:
                self._send_json({'error': 'Slug already exists or product is invalid.'}, 409); return
            except sqlite3.OperationalError:
                self._send_json({'error': 'The service is briefly busy. Please try again.'}, 503); return
            new_id = cur.lastrowid
            self.audit(user, 'create', 'product', new_id)
            self._send_json({'id': new_id}, 201); return

        if p == '/api/admin/products' and method == 'PUT':
            try:
                pid = int(d.get('id'))
            except (TypeError, ValueError):
                self._send_json({'error': 'A valid product id is required.'}, 400); return
            old = db.execute('SELECT * FROM products WHERE id=?', (pid,)).fetchone()
            if not old:
                self._send_json({'error': 'Product not found'}, 404); return
            slug = clean(d.get('slug', old['slug']), 100).lower()
            title = clean(d.get('title', old['title']), 140)
            summary = clean(d.get('summary', old['summary']), 300)
            description = clean(d.get('description', old['description']), 3000)
            price = clean(d.get('price_label', old['price_label']), 80)
            cat = clean(d.get('category', old['category']), 40)
            cover = clean(d.get('cover', old['cover']), 120)
            status = clean(d.get('status', old['status']), 20)
            features = d.get('features', json.loads(old['features']))
            technologies = d.get('technologies', json.loads(old['technologies']))
            if (not SLUG_RE.fullmatch(slug) or not title or not summary or not description
                    or cat not in ('Websites', 'Applications', 'Aurion') or status not in ('available', 'showcase')
                    or not isinstance(features, list) or not isinstance(technologies, list)
                    or len(features) > 20 or len(technologies) > 20):
                self._send_json({'error': 'Check required product fields, slug, category, status and feature lists.'}, 400); return
            features = [clean(x, 100) for x in features if clean(x, 100)]
            technologies = [clean(x, 100) for x in technologies if clean(x, 100)]
            published = 1 if d.get('published', old['published']) in (True, 1, 'true', '1') else 0
            try:
                db.execute(
                    'UPDATE products SET slug=?,title=?,summary=?,description=?,price_label=?,category=?,cover=?,status=?,features=?,technologies=?,published=? WHERE id=?',
                    (slug, title, summary, description, price, cat, cover, status,
                     json.dumps(features, ensure_ascii=False), json.dumps(technologies, ensure_ascii=False), published, pid))
            except sqlite3.IntegrityError:
                self._send_json({'error': 'Slug already exists or product is invalid.'}, 409); return
            except sqlite3.OperationalError:
                self._send_json({'error': 'The service is briefly busy. Please try again.'}, 503); return
            self.audit(user, 'update', 'product', pid)
            self._send_json({'ok': True}); return

        if p == '/api/admin/customers/status' and method == 'PUT':
            try:
                uid = int(d.get('id'))
            except (TypeError, ValueError):
                self._send_json({'error': 'A valid customer id is required.'}, 400); return
            active_value = d.get('active')
            if active_value not in (True, False, 0, 1):
                self._send_json({'error': 'Choose a valid account state.'}, 400); return
            if not db.execute("SELECT 1 FROM users WHERE id=? AND role='customer'", (uid,)).fetchone():
                self._send_json({'error': 'Customer not found.'}, 404); return
            active = 1 if active_value in (True, 1) else 0
            try:
                db.execute('BEGIN IMMEDIATE')
                db.execute('UPDATE users SET active=? WHERE id=?', (active, uid))
                if not active:
                    db.execute('DELETE FROM sessions WHERE user_id=?', (uid,))
                db.execute('COMMIT')
            except Exception:
                self._rollback(db)
                raise
            self.audit(user, 'customer_access', 'user', uid)
            self._send_json({'ok': True, 'active': bool(active)}); return

        if p == '/api/admin/products' and method == 'DELETE':
            try:
                pid = int(d.get('id'))
            except (TypeError, ValueError):
                self._send_json({'error': 'A valid product id is required.'}, 400); return
            cur = db.execute('UPDATE products SET published=0 WHERE id=?', (pid,))
            if not cur.rowcount:
                self._send_json({'error': 'Product not found'}, 404); return
            self.audit(user, 'unpublish', 'product', pid)
            self._send_json({'ok': True, 'note': 'Product unpublished; order history is preserved.'}); return

        if p == '/api/admin/refunds/decision' and method == 'PUT':
            status = d.get('status')
            if status not in ('Approved', 'Rejected'):
                self._send_json({'error': 'Decision must be Approved or Rejected.'}, 400); return
            try:
                rid = int(d.get('id'))
            except (TypeError, ValueError):
                self._send_json({'error': 'A valid refund id is required.'}, 400); return
            if not db.execute('SELECT 1 FROM refunds WHERE id=?', (rid,)).fetchone():
                self._send_json({'error': 'Refund request not found.'}, 404); return
            db.execute('UPDATE refunds SET status=?,admin_note=?,transaction_ref=? WHERE id=?',
                       (status, clean(d.get('note'), 1000), clean(d.get('transaction_ref'), 120), rid))
            self.audit(user, 'refund_decision', 'refund', rid)
            self._send_json({'ok': True, 'note': 'Approval records a decision only; it does not move funds.'}); return

        self._send_json({'error': 'Not found'}, 404)

    @staticmethod
    def _rollback(db):
        try:
            db.execute('ROLLBACK')
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# Entry point                                                                 #
# --------------------------------------------------------------------------- #
def bootstrap_admin():
    """Optionally seed an administrator from the environment (never a default password)."""
    email = os.environ.get('AXIA_ADMIN_EMAIL')
    password = os.environ.get('AXIA_ADMIN_PASSWORD')
    if not (email and password):
        return
    if len(password) < 12:
        print('AXIA_ADMIN_PASSWORD is shorter than 12 characters; seeded admin skipped.')
        return
    with database.connection() as conn:
        if conn.execute('SELECT 1 FROM users WHERE email=?', (email.lower(),)).fetchone():
            return
        conn.execute('INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,?)',
                     ('AXIASOFT Admin', email.lower(), hash_password(password), 'admin'))
        print('Initial admin account created from environment.')


def housekeeping():
    """Periodic bounded maintenance: expired sessions, trimmed audit log."""
    while True:
        try:
            time.sleep(3600)
            with database.connection() as conn:
                database.prune_sessions(conn)
                database.prune_audit(conn)
        except Exception as exc:
            print('housekeeping error:', repr(exc))


def graceful_shutdown(server, signame):
    """Stop accepting work, let in-flight requests finish, release the port."""
    print('%s received: finishing in-flight requests.' % signame)
    server.stopping.set()
    threading.Thread(target=server.shutdown, daemon=True).start()


def main():
    init()
    bootstrap_admin()
    threading.Thread(target=housekeeping, daemon=True).start()
    port = int(os.environ.get('PORT', '8000'))
    host = os.environ.get('AXIA_HOST', '0.0.0.0')
    server = AxiServer((host, port), Handler)

    for signame in ('SIGTERM', 'SIGINT'):
        signal_name = getattr(signal, signame, None)
        if signal_name is None:
            continue
        try:
            signal.signal(signal_name, lambda *_, name=signame: graceful_shutdown(server, name))
        except (ValueError, OSError):
            pass

    print('AXIASOFT listening on %s:%s (max in-flight %d, %d per client)'
          % (host, port, MAX_INFLIGHT, MAX_INFLIGHT_PER_CLIENT))
    try:
        server.serve_forever(poll_interval=0.4)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            server.server_close()
        finally:
            print('Shutdown complete.')


if __name__ == '__main__':
    main()
