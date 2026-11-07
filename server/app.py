"""AXIASOFT API and development server. Production deployments should use a hardened ASGI/WSGI stack and PostgreSQL."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path
import json, os, secrets, hashlib, hmac, base64, time, re, uuid, mimetypes
from datetime import datetime, timedelta, timezone
from db import connect, init, ROOT

PUBLIC=ROOT/'public'; SESSION_DAYS=7; RATE={}
STATUSES=['Submitted','Under Review','Requirements Analysis','Quotation Sent','Awaiting Confirmation','In Development','Testing','Ready for Delivery','Delivered','Cancelled']
def now(): return datetime.now(timezone.utc)
def iso(dt): return dt.isoformat(timespec='seconds')
def hash_password(pw,salt=None):
    salt=salt or secrets.token_bytes(16); dk=hashlib.pbkdf2_hmac('sha256',pw.encode(),salt,310000); return 'pbkdf2_sha256$310000$'+base64.b64encode(salt).decode()+'$'+base64.b64encode(dk).decode()
def verify_password(pw, encoded):
    try:
        alg,rounds,salt,expected=encoded.split('$'); return hmac.compare_digest(hashlib.pbkdf2_hmac('sha256',pw.encode(),base64.b64decode(salt),int(rounds)),base64.b64decode(expected))
    except Exception: return False
def token_hash(v): return hashlib.sha256(v.encode()).hexdigest()
def clean(s, n=5000): return str(s or '').strip()[:n]
def public_user(row): return {'id':row['id'],'name':row['name'],'email':row['email'],'role':row['role'],'phone':row['phone']}
def product_out(r):
    x=dict(r); x['features']=json.loads(x['features']); x['technologies']=json.loads(x['technologies']); return x
def ref(prefix): return prefix+'-'+uuid.uuid4().hex[:8].upper()

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw): super().__init__(*a,directory=str(PUBLIC),**kw)
    def log_message(self,fmt,*args): print('%s - %s'%(self.address_string(),fmt%args))
    def send_json(self,obj,status=200,headers=None):
        raw=json.dumps(obj,ensure_ascii=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(raw))); self.send_header('Cache-Control','no-store')
        if headers:
            for k,v in headers.items(): self.send_header(k,v)
        self.end_headers(); self.wfile.write(raw)
    def body(self):
        try:
            n=int(self.headers.get('Content-Length','0'))
            if n>100_000: raise ValueError('Request too large')
            return json.loads(self.rfile.read(n) or b'{}')
        except Exception: raise ValueError('Invalid or oversized JSON request')
    def client_ip(self): return self.client_address[0]
    def limited(self,limit=12,window=60):
        key=(self.client_ip(),self.path); t=time.time(); arr=[x for x in RATE.get(key,[]) if t-x<window]; arr.append(t); RATE[key]=arr; return len(arr)>limit
    def auth(self):
        raw=''
        for p in self.headers.get('Cookie','').split(';'):
            if p.strip().startswith('axia_session='): raw=p.strip().split('=',1)[1]
        if not raw: return None
        db=connect(); row=db.execute("SELECT u.*,s.csrf,s.expires_at FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>? AND u.active=1",(token_hash(raw),iso(now()))).fetchone(); db.close(); return dict(row) if row else None
    def audit(self,user,action,entity,eid):
        db=connect(); db.execute('INSERT INTO audit_logs(actor_id,action,entity,entity_id) VALUES(?,?,?,?)',(user['id'] if user else None,action,entity,str(eid))); db.commit(); db.close()
    def do_GET(self):
        p=urlparse(self.path).path
        if p.startswith('/api/'):
            try: self.api_get(p,parse_qs(urlparse(self.path).query))
            except Exception as e: self.send_json({'error':'Request could not be completed'},500); print('API error:',repr(e))
        else:
            self.path='/index.html' if p=='/' else p; super().do_GET()
    def do_POST(self): self.dispatch('POST')
    def do_PUT(self): self.dispatch('PUT')
    def do_DELETE(self): self.dispatch('DELETE')
    def dispatch(self,method):
        try:
            if self.limited(20 if 'auth' in self.path else 40): return self.send_json({'error':'Too many requests. Please wait a moment.'},429)
            data=self.body(); self.api_write(urlparse(self.path).path,method,data)
        except ValueError as e: self.send_json({'error':str(e)},400)
        except Exception as e: print('API error:',repr(e)); self.send_json({'error':'Request could not be completed'},500)
    def api_get(self,p,q):
        db=connect(); user=self.auth()
        if p=='/api/health': self.send_json({'status':'ok','service':'AXIASOFT'}); db.close(); return
        if p=='/api/products':
            cat=q.get('category',[''])[0]; rows=db.execute('SELECT * FROM products WHERE published=1 '+('AND category=? ' if cat else '')+'ORDER BY id',(cat,) if cat else ()).fetchall(); self.send_json([product_out(r) for r in rows]); db.close(); return
        if p.startswith('/api/products/'):
            slug=p.rsplit('/',1)[-1]; r=db.execute('SELECT * FROM products WHERE slug=? AND published=1',(slug,)).fetchone(); self.send_json(product_out(r) if r else {'error':'Product not found'},200 if r else 404); db.close(); return
        if p=='/api/me':
            self.send_json({'user':public_user(user) if user else None,'csrf':user['csrf'] if user else None}); db.close(); return
        if p=='/api/orders':
            if not user: self.send_json({'error':'Please sign in first'},401)
            elif user['role']=='admin':
                rows=db.execute('SELECT o.*,p.title product_title FROM orders o JOIN products p ON p.id=o.product_id ORDER BY o.created_at DESC').fetchall(); self.send_json([dict(x) for x in rows])
            else:
                rows=db.execute('SELECT o.*,p.title product_title FROM orders o JOIN products p ON p.id=o.product_id WHERE o.user_id=? ORDER BY o.created_at DESC',(user['id'],)).fetchall(); self.send_json([dict(x) for x in rows])
            db.close(); return
        if p=='/api/admin/overview':
            if not user or user['role']!='admin': self.send_json({'error':'Administrator access required'},403)
            else:
                counts={'customers':db.execute("SELECT count(*) FROM users WHERE role='customer'").fetchone()[0], 'orders':db.execute('SELECT count(*) FROM orders').fetchone()[0], 'pending':db.execute("SELECT count(*) FROM orders WHERE status IN ('Submitted','Under Review','Requirements Analysis')").fetchone()[0], 'active':db.execute("SELECT count(*) FROM orders WHERE status IN ('In Development','Testing')").fetchone()[0], 'completed':db.execute("SELECT count(*) FROM orders WHERE status='Delivered'").fetchone()[0], 'tickets':db.execute("SELECT count(*) FROM tickets WHERE status='Open'").fetchone()[0]}
                orders=db.execute('SELECT o.*,p.title product_title FROM orders o JOIN products p ON p.id=o.product_id ORDER BY o.created_at DESC').fetchall(); products=db.execute('SELECT * FROM products ORDER BY id').fetchall(); tickets=db.execute('SELECT * FROM tickets ORDER BY created_at DESC LIMIT 8').fetchall(); counts['refunds']=db.execute("SELECT count(*) FROM refunds WHERE status='Under review'").fetchone()[0]; counts['published']=db.execute('SELECT count(*) FROM products WHERE published=1').fetchone()[0]; self.send_json({'counts':counts,'orders':[dict(x) for x in orders],'products':[product_out(x) for x in products],'tickets':[dict(x) for x in tickets]})
            db.close(); return
        if p=='/api/admin/customers':
            if not user or user['role']!='admin': self.send_json({'error':'Administrator access required'},403)
            else:
                term=clean((q.get('q') or [''])[0],120); pattern='%'+term+'%'
                rows=db.execute("SELECT u.id,u.name,u.email,u.phone,u.role,u.active,u.created_at,(SELECT count(*) FROM orders o WHERE o.user_id=u.id) order_count,(SELECT count(*) FROM tickets t WHERE t.user_id=u.id) ticket_count FROM users u WHERE u.role='customer' AND (?='' OR u.name LIKE ? OR u.email LIKE ? OR u.phone LIKE ?) ORDER BY u.created_at DESC LIMIT 500",(term,pattern,pattern,pattern)).fetchall()
                self.send_json({'customers':[dict(x) for x in rows],'total':len(rows)})
            db.close(); return
        if p=='/api/admin/audit':
            if not user or user['role']!='admin': self.send_json({'error':'Administrator access required'},403)
            else:
                try: limit=max(1,min(int((q.get('limit') or ['100'])[0]),200))
                except Exception: limit=100
                rows=db.execute('SELECT a.id,a.action,a.entity,a.entity_id,a.created_at,u.name actor_name,u.email actor_email FROM audit_logs a LEFT JOIN users u ON u.id=a.actor_id ORDER BY a.created_at DESC,a.id DESC LIMIT ?',(limit,)).fetchall(); self.send_json([dict(x) for x in rows])
            db.close(); return
        history_match=re.fullmatch(r'/api/admin/orders/(\d+)/history',p)
        if history_match:
            if not user or user['role']!='admin': self.send_json({'error':'Administrator access required'},403)
            else:
                rows=db.execute('SELECT h.id,h.status,h.note,h.created_at,u.name actor_name FROM order_history h LEFT JOIN users u ON u.id=h.actor_id WHERE h.order_id=? ORDER BY h.created_at,h.id',(int(history_match.group(1)),)).fetchall(); self.send_json([dict(x) for x in rows])
            db.close(); return
        if p=='/api/support':
            if not user: self.send_json({'error':'Please sign in first'},401)
            else:
                rows=db.execute('SELECT * FROM tickets ORDER BY created_at DESC' if user['role']=='admin' else 'SELECT * FROM tickets WHERE user_id=? ORDER BY created_at DESC',() if user['role']=='admin' else (user['id'],)).fetchall()
                tickets=[]
                for r in rows:
                    item=dict(r); item['messages']=[dict(m) for m in db.execute('SELECT tm.message,tm.created_at,u.name sender FROM ticket_messages tm LEFT JOIN users u ON u.id=tm.sender_id WHERE tm.ticket_id=? ORDER BY tm.created_at',(r['id'],))]; tickets.append(item)
                self.send_json(tickets)
            db.close(); return
        if p=='/api/refunds':
            if not user: self.send_json({'error':'Please sign in first'},401)
            else:
                rows=db.execute('SELECT r.*,o.number order_number FROM refunds r JOIN orders o ON o.id=r.order_id '+('ORDER BY r.created_at DESC' if user['role']=='admin' else 'WHERE r.user_id=? ORDER BY r.created_at DESC'),() if user['role']=='admin' else (user['id'],)).fetchall(); self.send_json([dict(r) for r in rows])
            db.close(); return
        self.send_json({'error':'Not found'},404); db.close()
    def check_csrf(self,user):
        if not user: return False
        supplied=self.headers.get('X-CSRF-Token',''); return bool(supplied and hmac.compare_digest(supplied,user['csrf']))
    def api_write(self,p,m,d):
        db=connect(); user=self.auth()
        if p=='/api/register' and m=='POST':
            name=clean(d.get('name'),120); email=clean(d.get('email'),254).lower(); pw=str(d.get('password','')); phone=clean(d.get('phone'),40)
            if len(name)<2 or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email) or len(pw)<12: return self.send_json({'error':'Enter your name, a valid email, and a password of at least 12 characters.'},400)
            try: cur=db.execute('INSERT INTO users(name,email,phone,password_hash) VALUES(?,?,?,?)',(name,email,phone,hash_password(pw))); uid=cur.lastrowid
            except Exception: return self.send_json({'error':'An account with that email may already exist.'},409)
            self.create_session(db,uid); self.audit({'id':uid},'register','user',uid); return self.send_json({'user':public_user(db.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone())},201)
        if p=='/api/login' and m=='POST':
            email=clean(d.get('email'),254).lower(); pw=str(d.get('password','')); r=db.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
            if not r or not verify_password(pw,r['password_hash']) or not r['active']: return self.send_json({'error':'Email or password is incorrect.'},401)
            self.create_session(db,r['id']); self.audit(dict(r),'login','user',r['id']); return self.send_json({'user':public_user(r)})
        if p=='/api/logout' and m=='POST':
            if user and self.check_csrf(user):
                token=''
                for x in self.headers.get('Cookie','').split(';'):
                    if x.strip().startswith('axia_session='): token=x.strip().split('=',1)[1]
                db.execute('DELETE FROM sessions WHERE token_hash=?',(token_hash(token),)); db.commit()
            return self.send_json({'ok':True},headers={'Set-Cookie':'axia_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'})
        if not user: return self.send_json({'error':'Please sign in first'},401)
        if m!='GET' and not self.check_csrf(user): return self.send_json({'error':'Session security check failed. Refresh and try again.'},403)
        if p=='/api/orders' and m=='POST':
            product=db.execute('SELECT * FROM products WHERE id=? AND published=1',(d.get('product_id'),)).fetchone(); name=clean(d.get('name'),120); email=clean(d.get('email'),254).lower(); phone=clean(d.get('phone'),40); desc=clean(d.get('description'),3000)
            if not product or product['category']=='Aurion': return self.send_json({'error':'Select an orderable website or application product.'},400)
            if not name or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email) or len(phone)<5 or len(desc)<15: return self.send_json({'error':'Please complete all required fields. Project details must be at least 15 characters.'},400)
            no='AX-'+now().strftime('%y%m')+'-'+secrets.token_hex(3).upper(); cur=db.execute('INSERT INTO orders(number,user_id,product_id,name,email,phone,description,requirements,contact_method) VALUES(?,?,?,?,?,?,?,?,?)',(no,user['id'],product['id'],name,email,phone,desc,clean(d.get('requirements'),2000),clean(d.get('contact_method'),30) or 'Email')); oid=cur.lastrowid; db.execute('INSERT INTO order_history(order_id,status,note,actor_id) VALUES(?,?,?,?)',(oid,'Submitted','Order request received',user['id'])); db.commit(); self.audit(user,'create','order',oid); return self.send_json({'number':no,'status':'Submitted'},201)
        if p=='/api/support' and m=='POST':
            subject=clean(d.get('subject'),140); message=clean(d.get('message'),3000)
            if len(subject)<3 or len(message)<10:return self.send_json({'error':'Please add a subject and a message of at least 10 characters.'},400)
            refno=ref('AXS'); db.execute('INSERT INTO tickets(ref,user_id,email,subject,message) VALUES(?,?,?,?,?)',(refno,user['id'],user['email'],subject,message)); db.commit(); self.audit(user,'create','ticket',refno); return self.send_json({'ref':refno,'message':'A support request has been created. Our team will follow up.'},201)
        if p=='/api/refunds' and m=='POST':
            order=db.execute('SELECT * FROM orders WHERE id=? AND user_id=?',(d.get('order_id'),user['id'])).fetchone(); reason=clean(d.get('reason'),2000)
            if not order or len(reason)<5:return self.send_json({'error':'Choose one of your orders and provide a reason.'},400)
            try: created=datetime.strptime(order['created_at'],'%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
            except Exception: created=now()-timedelta(days=365)
            if now()-created>timedelta(days=14): return self.send_json({'error':'This order is outside the 14-calendar-day request window. Contact support if you believe an exception applies.'},400)
            if db.execute('SELECT 1 FROM refunds WHERE order_id=? AND user_id=? AND status IN (\'Under review\',\'Approved\')',(order['id'],user['id'])).fetchone(): return self.send_json({'error':'A refund request is already open or approved for this order.'},409)
            refno=ref('RFD'); db.execute('INSERT INTO refunds(ref,order_id,user_id,reason) VALUES(?,?,?,?)',(refno,order['id'],user['id'],reason)); db.commit(); return self.send_json({'ref':refno,'status':'Under review'},201)
        if p.startswith('/api/admin/') and user['role']!='admin': return self.send_json({'error':'Administrator access required'},403)
        if p=='/api/admin/tickets/status' and m=='PUT':
            tid=d.get('id'); status=d.get('status')
            if status not in ['Open','In progress','Closed']: return self.send_json({'error':'Unknown support status'},400)
            cur=db.execute('UPDATE tickets SET status=? WHERE id=?',(status,tid)); db.commit()
            if not cur.rowcount:return self.send_json({'error':'Ticket not found'},404)
            self.audit(user,'ticket_status','ticket',tid); return self.send_json({'ok':True})
        if p=='/api/admin/tickets/reply' and m=='POST':
            tid=d.get('id'); message=clean(d.get('message'),3000)
            if len(message)<2:return self.send_json({'error':'Reply is too short'},400)
            ticket=db.execute('SELECT id FROM tickets WHERE id=?',(tid,)).fetchone()
            if not ticket:return self.send_json({'error':'Ticket not found'},404)
            db.execute('INSERT INTO ticket_messages(ticket_id,sender_id,message) VALUES(?,?,?)',(tid,user['id'],message)); db.execute('UPDATE tickets SET status=\'In progress\' WHERE id=?',(tid,)); db.commit(); self.audit(user,'ticket_reply','ticket',tid); return self.send_json({'ok':True})
        if p=='/api/admin/orders/status' and m=='PUT':
            oid=d.get('id'); status=clean(d.get('status'),80); note=clean(d.get('note'),1000)
            if status not in STATUSES:return self.send_json({'error':'Unknown order status'},400)
            order=db.execute('SELECT id FROM orders WHERE id=?',(oid,)).fetchone()
            if not order:return self.send_json({'error':'Order not found'},404)
            db.execute('UPDATE orders SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(status,oid)); db.execute('INSERT INTO order_history(order_id,status,note,actor_id) VALUES(?,?,?,?)',(oid,status,note,user['id'])); db.commit(); self.audit(user,'status_change','order',oid); return self.send_json({'ok':True})
        if p=='/api/admin/products' and m=='POST':
            slug=clean(d.get('slug'),100).lower(); title=clean(d.get('title'),140); cat=clean(d.get('category'),40); summary=clean(d.get('summary'),300); description=clean(d.get('description'),3000); status=clean(d.get('status','available'),20); cover=clean(d.get('cover'),120); features=d.get('features',[]); technologies=d.get('technologies',[])
            if not re.fullmatch(r'[a-z0-9-]{3,100}',slug) or not title or cat not in ['Websites','Applications','Aurion'] or status not in ['available','showcase'] or not summary or not description or not isinstance(features,list) or not isinstance(technologies,list) or len(features)>20 or len(technologies)>20:return self.send_json({'error':'Check required product fields, category, status and feature lists.'},400)
            features=[clean(x,100) for x in features if clean(x,100)]; technologies=[clean(x,100) for x in technologies if clean(x,100)]
            try: cur=db.execute('INSERT INTO products(slug,title,category,summary,description,cover,status,price_label,features,technologies,published) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(slug,title,cat,summary,description,cover,status,clean(d.get('price_label'),80) or 'Request a quote',json.dumps(features,ensure_ascii=False),json.dumps(technologies,ensure_ascii=False),1 if d.get('published',True) in (True,1,'true','1') else 0)); db.commit(); self.audit(user,'create','product',cur.lastrowid); return self.send_json({'id':cur.lastrowid},201)
            except Exception:return self.send_json({'error':'Slug already exists or product is invalid.'},409)
        if p=='/api/admin/products' and m=='PUT':
            try: pid=int(d.get('id'))
            except (TypeError,ValueError): return self.send_json({'error':'A valid product id is required.'},400)
            old=db.execute('SELECT * FROM products WHERE id=?',(pid,)).fetchone()
            if not old:return self.send_json({'error':'Product not found'},404)
            slug=clean(d.get('slug',old['slug']),100).lower(); title=clean(d.get('title',old['title']),140); summary=clean(d.get('summary',old['summary']),300); description=clean(d.get('description',old['description']),3000); price=clean(d.get('price_label',old['price_label']),80); cat=clean(d.get('category',old['category']),40); cover=clean(d.get('cover',old['cover']),120); status=clean(d.get('status',old['status']),20)
            features=d.get('features',json.loads(old['features'])); technologies=d.get('technologies',json.loads(old['technologies']))
            if not re.fullmatch(r'[a-z0-9-]{3,100}',slug) or not title or not summary or not description or cat not in ['Websites','Applications','Aurion'] or status not in ['available','showcase'] or not isinstance(features,list) or not isinstance(technologies,list) or len(features)>20 or len(technologies)>20:return self.send_json({'error':'Check required product fields, slug, category, status and feature lists.'},400)
            features=[clean(x,100) for x in features if clean(x,100)]; technologies=[clean(x,100) for x in technologies if clean(x,100)]
            published_value=d.get('published',old['published']); published=1 if published_value in (True,1,'true','1') else 0
            try: cur=db.execute('UPDATE products SET slug=?,title=?,summary=?,description=?,price_label=?,category=?,cover=?,status=?,features=?,technologies=?,published=? WHERE id=?',(slug,title,summary,description,price,cat,cover,status,json.dumps(features,ensure_ascii=False),json.dumps(technologies,ensure_ascii=False),published,pid)); db.commit()
            except Exception:return self.send_json({'error':'Slug already exists or product is invalid.'},409)
            self.audit(user,'update','product',pid); return self.send_json({'ok':True})
        if p=='/api/admin/customers/status' and m=='PUT':
            try: uid=int(d.get('id'))
            except (TypeError,ValueError): return self.send_json({'error':'A valid customer id is required.'},400)
            active_value=d.get('active')
            if active_value not in (True,False,0,1): return self.send_json({'error':'Choose a valid account state.'},400)
            target=db.execute("SELECT id,role FROM users WHERE id=? AND role='customer'",(uid,)).fetchone()
            if not target:return self.send_json({'error':'Customer not found.'},404)
            active=1 if active_value in (True,1) else 0
            db.execute('UPDATE users SET active=? WHERE id=?',(active,uid))
            if not active: db.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
            db.commit(); self.audit(user,'customer_access','user',uid); return self.send_json({'ok':True,'active':bool(active)})
        if p=='/api/admin/products' and m=='DELETE':
            pid=d.get('id'); cur=db.execute('UPDATE products SET published=0 WHERE id=?',(pid,)); db.commit()
            if not cur.rowcount:return self.send_json({'error':'Product not found'},404)
            self.audit(user,'unpublish','product',pid); return self.send_json({'ok':True,'note':'Product unpublished; order history is preserved.'})
        if p=='/api/admin/refunds/decision' and m=='PUT':
            status=d.get('status'); rid=d.get('id')
            if status not in ['Approved','Rejected']: return self.send_json({'error':'Decision must be Approved or Rejected.'},400)
            try: rid=int(rid)
            except (TypeError,ValueError): return self.send_json({'error':'A valid refund id is required.'},400)
            if not db.execute('SELECT 1 FROM refunds WHERE id=?',(rid,)).fetchone():return self.send_json({'error':'Refund request not found.'},404)
            db.execute('UPDATE refunds SET status=?,admin_note=?,transaction_ref=? WHERE id=?',(status,clean(d.get('note'),1000),clean(d.get('transaction_ref'),120),rid)); db.commit(); self.audit(user,'refund_decision','refund',rid); return self.send_json({'ok':True,'note':'Approval records a decision only; it does not move funds.'})
        return self.send_json({'error':'Not found'},404)
    def create_session(self,db,uid):
        raw=secrets.token_urlsafe(32); csrf=secrets.token_urlsafe(24); exp=iso(now()+timedelta(days=SESSION_DAYS)); db.execute('INSERT INTO sessions(token_hash,user_id,csrf,expires_at) VALUES(?,?,?,?)',(token_hash(raw),uid,csrf,exp)); db.commit(); self._new_csrf=csrf; self.send_response # cookie emitted by send_json helper not used here
        secure='; Secure' if os.environ.get('AXIA_COOKIE_SECURE')=='1' else ''
        self._session_cookie='axia_session='+raw+'; HttpOnly; SameSite=Strict; Path=/; Max-Age='+str(SESSION_DAYS*86400)+secure
    # Wrap JSON writer to attach newly issued session cookie and csrf token header.
    def end_headers(self):
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','strict-origin-when-cross-origin')
        self.send_header('Permissions-Policy','camera=(), microphone=(), geolocation=()')
        self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        if os.environ.get('AXIA_HSTS')=='1': self.send_header('Strict-Transport-Security','max-age=31536000; includeSubDomains')
        if getattr(self,'_session_cookie',None): self.send_header('Set-Cookie',self._session_cookie); self._session_cookie=None
        if getattr(self,'_new_csrf',None): self.send_header('X-CSRF-Token',self._new_csrf); self._new_csrf=None
        super().end_headers()

if __name__=='__main__':
    init(); db=connect()
    # Optional seeded administrator. Set AXIA_ADMIN_EMAIL and AXIA_ADMIN_PASSWORD before first launch.
    email=os.environ.get('AXIA_ADMIN_EMAIL'); password=os.environ.get('AXIA_ADMIN_PASSWORD')
    if email and password and not db.execute('SELECT 1 FROM users WHERE email=?',(email,)).fetchone():
        db.execute('INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,?)',('AXIASOFT Admin',email.lower(),hash_password(password),'admin')); db.commit(); print('Initial admin account created from environment.')
    db.close(); port=int(os.environ.get('PORT','8000')); print('AXIASOFT listening on 0.0.0.0:%s'%port); ThreadingHTTPServer(('0.0.0.0',port),Handler).serve_forever()
