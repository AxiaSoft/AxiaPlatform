"""SQLite persistence layer for the AXIASOFT development platform.

Connection policy
-----------------
The development server is multi-threaded, so the connection factory is tuned for
concurrent readers plus short serialised writers:

* ``isolation_level=None`` (autocommit). Every statement commits immediately, so a
  connection can never sit on an uncommitted write transaction. This is what keeps
  a single failed write from wedging the whole database for every other request.
* ``busy_timeout`` makes concurrent writers wait briefly instead of failing.
* WAL journaling lets readers proceed while a writer is active.
* ``transaction()`` is provided for the few operations that must be atomic.

Callers should still close connections promptly; ``connect()`` is usable as a
context manager and ``Handler.finish()`` closes anything a request opened.
"""
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / 'data' / 'axiasoft.sqlite3'

DB_PATH = Path(os.environ.get('AXIA_DB') or DEFAULT_DB_PATH)
DB_TIMEOUT = float(os.environ.get('AXIA_DB_TIMEOUT') or 5.0)

SCHEMA = '''
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE COLLATE NOCASE, phone TEXT DEFAULT '', password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'customer' CHECK(role IN ('customer','admin')), active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, csrf TEXT NOT NULL, expires_at TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, slug TEXT UNIQUE NOT NULL, title TEXT NOT NULL, category TEXT NOT NULL, summary TEXT NOT NULL, description TEXT NOT NULL, cover TEXT NOT NULL DEFAULT '', features TEXT NOT NULL DEFAULT '[]', technologies TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL DEFAULT 'available', price_label TEXT NOT NULL DEFAULT 'Request a quote', github_url TEXT NOT NULL DEFAULT '', published INTEGER NOT NULL DEFAULT 1, featured INTEGER NOT NULL DEFAULT 0, position INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY, number TEXT UNIQUE NOT NULL, user_id INTEGER NOT NULL REFERENCES users(id), product_id INTEGER NOT NULL REFERENCES products(id), name TEXT NOT NULL, email TEXT NOT NULL, phone TEXT NOT NULL, description TEXT NOT NULL, requirements TEXT NOT NULL DEFAULT '', contact_method TEXT NOT NULL DEFAULT 'Email', status TEXT NOT NULL DEFAULT 'Submitted', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS order_history(id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE, status TEXT NOT NULL, note TEXT DEFAULT '', actor_id INTEGER REFERENCES users(id), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS tickets(id INTEGER PRIMARY KEY, ref TEXT UNIQUE NOT NULL, user_id INTEGER REFERENCES users(id), email TEXT NOT NULL, subject TEXT NOT NULL, message TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Open', priority TEXT NOT NULL DEFAULT 'Normal', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS refunds(id INTEGER PRIMARY KEY, ref TEXT UNIQUE NOT NULL, order_id INTEGER NOT NULL REFERENCES orders(id), user_id INTEGER NOT NULL REFERENCES users(id), reason TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Under review', admin_note TEXT DEFAULT '', transaction_ref TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS ticket_messages(id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE, sender_id INTEGER REFERENCES users(id), message TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS audit_logs(id INTEGER PRIMARY KEY, actor_id INTEGER REFERENCES users(id), action TEXT NOT NULL, entity TEXT NOT NULL, entity_id TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS site_settings(id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL DEFAULT '{}', updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS articles(id INTEGER PRIMARY KEY, slug TEXT NOT NULL UNIQUE, title TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '', body TEXT NOT NULL DEFAULT '', cover TEXT NOT NULL DEFAULT '', tags TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','published')), language TEXT NOT NULL DEFAULT 'fa' CHECK(language IN ('fa','en')), published_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category,published);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_status ON articles(status, published_at DESC);
-- Machine translations of an article, cached so a published post is translated
-- once rather than on every request. A row is keyed to the article's
-- updated_at, so editing the source invalidates the English version.
CREATE TABLE IF NOT EXISTS article_translations(article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE, lang TEXT NOT NULL, title TEXT NOT NULL DEFAULT '', summary TEXT NOT NULL DEFAULT '', body TEXT NOT NULL DEFAULT '', source_hash TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(article_id, lang));
'''

# The shipped catalog is intentionally empty: products are created from the admin
# console, each pointing at its own GitHub preview link.
SEED_PRODUCTS = []


def migrate(db):
    """Add columns introduced after a database was first created.

    ``CREATE TABLE IF NOT EXISTS`` never alters an existing table, so a database
    created before a column existed would raise on every product query. Adding
    the columns here keeps old installations working.
    """
    cols = {row[1] for row in db.execute('PRAGMA table_info(products)').fetchall()}
    if 'github_url' not in cols:
        db.execute("ALTER TABLE products ADD COLUMN github_url TEXT NOT NULL DEFAULT ''")
    if 'featured' not in cols:
        db.execute('ALTER TABLE products ADD COLUMN featured INTEGER NOT NULL DEFAULT 0')
    if 'position' not in cols:
        db.execute('ALTER TABLE products ADD COLUMN position INTEGER NOT NULL DEFAULT 0')



def connect():
    """Open a hardened, autocommit SQLite connection."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(DB_PATH), timeout=DB_TIMEOUT, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=%d' % int(DB_TIMEOUT * 1000))
    return db


@contextmanager
def connection():
    """Context manager that always closes the connection, even on error."""
    db = connect()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def transaction():
    """Atomic multi-statement block: BEGIN IMMEDIATE ... COMMIT / ROLLBACK."""
    db = connect()
    try:
        db.execute('BEGIN IMMEDIATE')
        try:
            yield db
        except Exception:
            db.execute('ROLLBACK')
            raise
        db.execute('COMMIT')
    finally:
        db.close()


def init():
    """Create the schema and seed the showcase catalog. Safe to run repeatedly."""
    with connection() as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript(SCHEMA)
        migrate(db)
        if db.execute('SELECT count(*) FROM products').fetchone()[0] == 0:
            db.executemany(
                'INSERT INTO products(slug,title,category,summary,description,cover,features,technologies,status,price_label) VALUES(?,?,?,?,?,?,?,?,?,?)',
                SEED_PRODUCTS,
            )


def get_settings(db):
    """Return the stored storefront settings document (complete, with defaults)."""
    import site_settings
    row = db.execute('SELECT data FROM site_settings WHERE id=1').fetchone()
    try:
        stored = json.loads(row['data']) if row else {}
    except (TypeError, ValueError):
        stored = {}
    if not isinstance(stored, dict):
        stored = {}
    return site_settings.merge(stored)


def save_settings(db, payload):
    """Persist a partial settings document over the current one."""
    import site_settings
    current = get_settings(db)
    cleaned, errors = site_settings.clean_settings(payload)
    if errors:
        return current, errors
    current.update(cleaned)
    label = json.dumps(current, ensure_ascii=False)
    db.execute(
        'INSERT INTO site_settings(id, data) VALUES(1, ?) '
        'ON CONFLICT(id) DO UPDATE SET data=excluded.data, updated_at=CURRENT_TIMESTAMP',
        (label,))
    return current, {}


def prune_sessions(db, now_iso=None):
    """Delete expired session rows. Returns the number of rows removed."""
    from datetime import datetime, timezone
    now_iso = now_iso or datetime.now(timezone.utc).isoformat(timespec='seconds')
    return db.execute('DELETE FROM sessions WHERE expires_at<=?', (now_iso,)).rowcount


def prune_audit(db, keep=20000):
    """Keep the audit log bounded so it cannot grow without limit."""
    return db.execute(
        'DELETE FROM audit_logs WHERE id NOT IN (SELECT id FROM audit_logs ORDER BY id DESC LIMIT ?)',
        (int(keep),),
    ).rowcount


if __name__ == '__main__':
    init()
    print(DB_PATH)

def now_string():
    """UTC timestamp in the same shape SQLite's CURRENT_TIMESTAMP produces."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
