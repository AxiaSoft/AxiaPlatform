"""SQLite persistence layer for the AXIASOFT development platform."""
import sqlite3, os, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get('AXIA_DB', ROOT / 'data' / 'axiasoft.sqlite3'))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
SCHEMA = '''
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE COLLATE NOCASE, phone TEXT DEFAULT '', password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'customer' CHECK(role IN ('customer','admin')), active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, csrf TEXT NOT NULL, expires_at TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, slug TEXT UNIQUE NOT NULL, title TEXT NOT NULL, category TEXT NOT NULL, summary TEXT NOT NULL, description TEXT NOT NULL, cover TEXT NOT NULL DEFAULT '', features TEXT NOT NULL DEFAULT '[]', technologies TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL DEFAULT 'available', price_label TEXT NOT NULL DEFAULT 'Request a quote', published INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY, number TEXT UNIQUE NOT NULL, user_id INTEGER NOT NULL REFERENCES users(id), product_id INTEGER NOT NULL REFERENCES products(id), name TEXT NOT NULL, email TEXT NOT NULL, phone TEXT NOT NULL, description TEXT NOT NULL, requirements TEXT NOT NULL DEFAULT '', contact_method TEXT NOT NULL DEFAULT 'Email', status TEXT NOT NULL DEFAULT 'Submitted', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS order_history(id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE, status TEXT NOT NULL, note TEXT DEFAULT '', actor_id INTEGER REFERENCES users(id), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS tickets(id INTEGER PRIMARY KEY, ref TEXT UNIQUE NOT NULL, user_id INTEGER REFERENCES users(id), email TEXT NOT NULL, subject TEXT NOT NULL, message TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Open', priority TEXT NOT NULL DEFAULT 'Normal', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS refunds(id INTEGER PRIMARY KEY, ref TEXT UNIQUE NOT NULL, order_id INTEGER NOT NULL REFERENCES orders(id), user_id INTEGER NOT NULL REFERENCES users(id), reason TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Under review', admin_note TEXT DEFAULT '', transaction_ref TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS ticket_messages(id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE, sender_id INTEGER REFERENCES users(id), message TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS audit_logs(id INTEGER PRIMARY KEY, actor_id INTEGER REFERENCES users(id), action TEXT NOT NULL, entity TEXT NOT NULL, entity_id TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category,published);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
'''

def connect():
    db=sqlite3.connect(DB_PATH, timeout=10); db.row_factory=sqlite3.Row; db.execute('PRAGMA foreign_keys=ON'); return db

def init():
    db=connect(); db.executescript(SCHEMA)
    if db.execute('SELECT count(*) FROM products').fetchone()[0] == 0:
        data=[
          ('northstar-corporate','Northstar Corporate','Websites','A confident digital home for ambitious teams.','A responsive corporate website designed to clarify your value and turn visits into conversations. Includes an editorial-ready page system and a polished contact journey.','web','["Responsive pages","CMS-ready structure","Accessibility-minded","Lead capture"]','["Next.js","TypeScript","PostgreSQL"]','available','Request a quote'),
          ('atelier-store','Atelier Commerce','Websites','A considered storefront built for modern retail.','A conversion-focused commerce experience with product storytelling, clear navigation and an extensible foundation. Scope and integrations are confirmed during discovery.','shopping-bag','["Product discovery","Mobile-first checkout design","Catalog structure","Analytics-ready"]','["React","Node.js","PostgreSQL"]','available','Request a quote'),
          ('care-clinic','Careline Clinic','Websites','A calmer, more accessible patient experience.','A clean healthcare website concept with service information, provider profiles and a booking journey designed around clarity.','heart-pulse','["Service directory","Appointment inquiry","Accessible UI","Privacy-aware forms"]','["Next.js","TypeScript"]','available','Request a quote'),
          ('fieldwork-app','Fieldwork Mobile','Applications','Keep field teams connected and work moving.','A cross-platform mobile product concept for task coordination, updates and field operations. Final feature scope is agreed with your team.','smartphone','["Team task flows","Status updates","Offline-first planning","Role-aware screens"]','["React Native","TypeScript","API"]','available','Request a quote'),
          ('orbit-booking','Orbit Booking','Applications','A friction-light booking experience for services.','A mobile booking application concept with service discovery, schedule selection and clear customer communication.','calendar-days','["Booking flow","Availability interface","Customer profile","Notifications-ready"]','["Flutter","REST API"]','available','Request a quote'),
          ('aurion','AURION','Aurion','A symbolic showcase for MetaTrader companion software.','AURION is presented as a product concept for working with trading robots in the MetaTrader environment. No trading, broker connection, license generation, activation or payment is available in this showcase.','orbit','["MetaTrader-oriented concept","Package presentation","Demo-only experience","No live trading"]','["Product showcase"]','showcase','Presentation only')]
        db.executemany('INSERT INTO products(slug,title,category,summary,description,cover,features,technologies,status,price_label) VALUES(?,?,?,?,?,?,?,?,?,?)',data)
    db.commit(); db.close()

if __name__=='__main__': init(); print(DB_PATH)
