/* ==========================================================================
   AXIASOFT — GitHub Pages demo backend

   The published site has no Python server, so this file answers the API calls
   the admin console makes, entirely in the browser. It exists so the console can
   be tried on GitHub Pages instead of showing a "needs the server" gate.

   It is a DEMO, and it behaves like one:

   * Credentials are demo / demo. They are written in this file, in public. They
     protect nothing. The real console requires a server-verified administrator
     session; this one is a shop window.
   * Product edits are kept in localStorage for the current browser, and can be
     exported as JSON to replace `data/products.json` in the repository. Nothing
     is written back to GitHub — a static host cannot accept writes.
   * Orders, customers, tickets, refunds and audit records are read-only sample
     rows. They are clearly illustrative and are not stored anywhere.

   Everything is scope-guarded: if a real API answers on this origin, this file
   backs out and the real server response is used unchanged.
   ========================================================================== */
(function () {
  'use strict';

  if (!window.fetch || window.AXIA_DEMO_BACKEND) return;
  window.AXIA_DEMO_BACKEND = true;

  var config = window.AXIA_STATIC || {};
  var BASE = config.base || '/';

  // The name is shown inside Persian sentences, so it is built in the active
  // language; the email/username stays "demo" because that is what is typed.
  function demoUser() {
    var fa = document.documentElement.lang === 'fa';
    return { id: 1, name: fa ? 'مدیر نمایشی' : 'Demo Administrator', email: 'demo', role: 'admin', phone: '' };
  }
  var DEMO_CREDENTIALS = { email: 'demo', password: 'demo' };

  var STORE_KEY = 'axia-demo-products-v1';
  var SESSION_KEY = 'axia-demo-session-v1';
  var CSRF = 'demo-csrf-token';

  /* ------------------------------------------------------------- storage */
  function readProducts() {
    var raw = null;
    try { raw = localStorage.getItem(STORE_KEY); } catch (err) { /* private mode */ }
    if (raw) {
      try {
        var parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) return parsed;
      } catch (err) { /* fall through to the shipped snapshot */ }
    }
    // First visit: seed the editable copy from the build's product snapshot.
    return snapshot().map(function (p) { return normalise(p); });
  }

  function writeProducts(list) {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(list)); } catch (err) { /* ignore */ }
  }

  function snapshot() {
    if (Array.isArray(window.AXIA_STATIC && window.AXIA_STATIC.products)) {
      return window.AXIA_STATIC.products.slice();
    }
    return [];
  }

  function normalise(p) {
    var copy = {};
    for (var k in p) if (Object.prototype.hasOwnProperty.call(p, k)) copy[k] = p[k];
    if (!copy.github_url) copy.github_url = '';
    if (copy.published === undefined) copy.published = 1;
    return copy;
  }

  function signedIn() {
    try { return sessionStorage.getItem(SESSION_KEY) === '1'; } catch (err) { return false; }
  }

  function setSignedIn(value) {
    try {
      if (value) sessionStorage.setItem(SESSION_KEY, '1');
      else sessionStorage.removeItem(SESSION_KEY);
    } catch (err) { /* ignore */ }
  }

  /* -------------------------------------------------------- sample data */
  // Illustrative rows so the console's other screens are not blank. They are
  // never written anywhere and the site never claims they are real.
  var SAMPLE_ORDERS = [
    { id: 1, number: 'AX-2401', user_id: 2, product_id: 1, name: 'Sample Customer', email: 'sample@example.com',
      phone: '', description: 'Illustrative project request used to show the console layout.',
      requirements: '', contact_method: 'Email', status: 'Submitted', created_at: ago(3), updated_at: ago(3),
      product_title: 'Sample product' },
    { id: 2, number: 'AX-2402', user_id: 3, product_id: 1, name: 'Sample Customer', email: 'sample@example.com',
      phone: '', description: 'Illustrative project request used to show the console layout.',
      requirements: '', contact_method: 'Email', status: 'In Development', created_at: ago(21), updated_at: ago(4),
      product_title: 'Sample product' }
  ];

  function ago(days) {
    var d = new Date(Date.now() - days * 86400000);
    return d.toISOString().slice(0, 19).replace('T', ' ');
  }

  /* ------------------------------------------------------------ replies */
  function fallbackResponse(body, status) {
    var text = JSON.stringify(body);
    return {
      ok: status >= 200 && status < 300,
      status: status,
      statusText: '',
      headers: { get: function (name) { return /^(content-type|x-csrf-token)$/i.test(name) ? (name.toLowerCase() === 'x-csrf-token' ? CSRF : 'application/json; charset=utf-8') : null; } },
      text: function () { return Promise.resolve(text); },
      json: function () { return Promise.resolve(JSON.parse(text)); }
    };
  }

  function json(body, status) {
    var code = status || 200;
    if (typeof Response === 'function') {
      try {
        return Promise.resolve(new Response(JSON.stringify(body), {
          status: code,
          headers: { 'Content-Type': 'application/json; charset=utf-8', 'X-CSRF-Token': CSRF }
        }));
      } catch (err) { /* fall through */ }
    }
    return Promise.resolve(fallbackResponse(body, code));
  }

  function fail(message, status) { return json({ error: message }, status || 400); }

  /* -------------------------------------------------------------- fetch */
  var originalFetch = window.fetch.bind(window);

  window.fetch = function (input, init) {
    var url = typeof input === 'string' ? input : (input && input.url) || '';
    var method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
    var path = url.split('?')[0];

    if (/^[a-z]+:/i.test(url) || path.indexOf('/data/') === 0) {
      return originalFetch(input, init);
    }
    if (path.indexOf('/api/') !== 0) return originalFetch(input, init);

    var payload = {};
    if (init && typeof init.body === 'string') {
      try { payload = JSON.parse(init.body) || {}; } catch (err) { payload = {}; }
    }

    // ---- auth -----------------------------------------------------------
    if (path === '/api/me') {
      return json(signedIn() ? { user: demoUser(), csrf: CSRF } : { user: null, csrf: null });
    }
    if (path === '/api/login' && method === 'POST') {
      var email = String(payload.email || '').trim().toLowerCase();
      var pass = String(payload.password || '');
      if (email === DEMO_CREDENTIALS.email && pass === DEMO_CREDENTIALS.password) {
        setSignedIn(true);
        return json({ user: demoUser(), csrf: CSRF });
      }
      return fail('Use the demo credentials: demo / demo', 401);
    }
    if (path === '/api/logout') {
      setSignedIn(false);
      return json({ ok: true });
    }

    // ---- catalog --------------------------------------------------------
    if (path === '/api/products' && method === 'GET') {
      return json(readProducts().filter(function (p) { return p.published; }));
    }
    if (path.indexOf('/api/products/') === 0 && method === 'GET') {
      var slug = decodeURIComponent(path.split('/').pop());
      var found = readProducts().filter(function (p) { return p.slug === slug && p.published; })[0];
      return found ? json(found) : fail('Product not found', 404);
    }

    // ---- admin ----------------------------------------------------------
    if (path.indexOf('/api/admin/') === 0) {
      if (!signedIn()) return fail('Administrator access required', 403);

      if (path === '/api/admin/overview') {
        var products = readProducts();
        var orders = SAMPLE_ORDERS;
        var counts = {
          customers: 2,
          orders: orders.length,
          pending: orders.filter(function (o) { return ['Submitted', 'Under Review', 'Requirements Analysis'].indexOf(o.status) >= 0; }).length,
          active: orders.filter(function (o) { return ['In Development', 'Testing'].indexOf(o.status) >= 0; }).length,
          completed: 0,
          tickets: 0,
          refunds: 0,
          published: products.filter(function (p) { return p.published; }).length
        };
        return json({ counts: counts, orders: orders, products: products, tickets: [] });
      }

      if (path === '/api/admin/customers') {
        return json({ customers: [], total: 0 });
      }

      if (path === '/api/admin/audit') {
        return json([{
          id: 1, action: 'login', entity: 'session', entity_id: 'demo',
          created_at: ago(0), actor_name: demoUser().name, actor_email: 'demo'
        }]);
      }

      if (path === '/api/admin/products' && method === 'POST') {
        var list = readProducts();
        var slugNew = String(payload.slug || '').toLowerCase();
        if (list.some(function (p) { return p.slug === slugNew; })) {
          return fail('Slug already exists or product is invalid.', 409);
        }
        var created = normalise({
          id: nextId(list), slug: slugNew, title: payload.title, category: payload.category,
          summary: payload.summary, description: payload.description, cover: payload.cover || '',
          features: payload.features || [], technologies: payload.technologies || [],
          status: payload.status || 'available',
          price_label: payload.price_label || 'Request a quote',
          github_url: payload.github_url || '',
          published: payload.published ? 1 : 0, created_at: ago(0)
        });
        list.push(created);
        writeProducts(list);
        return json({ id: created.id }, 201);
      }

      if (path === '/api/admin/products' && method === 'PUT') {
        var items = readProducts();
        var id = Number(payload.id);
        var target = items.filter(function (p) { return Number(p.id) === id; })[0];
        if (!target) return fail('Product not found', 404);
        for (var key in payload) {
          if (!Object.prototype.hasOwnProperty.call(payload, key) || key === 'id') continue;
          if (key === 'features' || key === 'technologies') {
            if (Array.isArray(payload[key])) target[key] = payload[key];
          } else if (key === 'published') {
            target.published = payload.published ? 1 : 0;
          } else {
            target[key] = payload[key];
          }
        }
        writeProducts(items);
        return json({ ok: true });
      }

      if (path === '/api/admin/products' && method === 'DELETE') {
        var rows = readProducts();
        var pid = Number(payload.id);
        var hit = rows.filter(function (p) { return Number(p.id) === pid; })[0];
        if (!hit) return fail('Product not found', 404);
        hit.published = 0;
        writeProducts(rows);
        return json({ ok: true, note: 'Product unpublished.' });
      }

      // Other admin writes have no meaning without a database.
      return fail('This action is not available in the static demo.', 501);
    }

    // ---- everything else is demo-only --------------------------------
    if (path === '/api/orders' || path === '/api/support' || path === '/api/refunds') {
      return fail('This action is not available in the static demo.', 501);
    }

    return originalFetch(input, init);
  };

  function nextId(list) {
    var max = 0;
    for (var i = 0; i < list.length; i++) max = Math.max(max, Number(list[i].id) || 0);
    return max + 1;
  }

  /* -------------------------------------------------------------- export */
  // The console offers "Export CSV"; this adds a JSON export that can replace
  // data/products.json in the repository, which is how a demo edit becomes real.
  window.AXIA_DEMO_EXPORT = function () {
    var blob = new Blob([JSON.stringify(readProducts(), null, 2)], { type: 'application/json' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'products.json';
    a.click();
    URL.revokeObjectURL(a.href);
  };

  /* ------------------------------------------------------- demo banner */
  // Make it unmistakable that this console is a demo and what the credentials
  // are. The real server build never loads this file, so it never sees this.
  function markDemo() {
    var fa = document.documentElement.lang === 'fa';

    if (document.documentElement.dataset.demoMode !== 'on') {
      document.documentElement.dataset.demoMode = 'on';
      var chip = document.createElement('div');
      chip.className = 'demo-chip';
      chip.dataset.demoChip = '';
      chip.setAttribute('role', 'status');
      chip.textContent = fa ? 'حالت نمایشی · داده‌ها در همین مرورگر ذخیره می‌شوند' : 'Demo mode · data is stored in this browser only';
      document.body.appendChild(chip);
    }

    // The login card is re-rendered on every failed attempt, so the note has to
    // be rewritten each time rather than once at startup.
    var note = document.querySelector('.setup-command');
    if (note && !note.dataset.demoNote) {
      note.dataset.demoNote = '1';
      note.innerHTML = fa
        ? 'حساب نمایشی: <code>demo</code> / <code>demo</code> — این اطلاعات در یک فایل عمومی نوشته شده‌اند و هیچ امنیتی ایجاد نمی‌کنند.'
        : 'Demo account: <code>demo</code> / <code>demo</code> — written in a public file, protects nothing.';
    }
  }

  /* ---------------------------------------------------- login field fix */
  // The console's login input is type="email", so a browser refuses to submit
  // the form for a username like "demo" (it demands an "@"). The demo account is
  // a username, not an address, so relax the field once the login form exists.
  function relaxLoginField() {
    var email = document.getElementById('loginEmail');
    if (!email || email.type === 'text') return;
    email.type = 'text';
    email.setAttribute('autocomplete', 'username');
    email.setAttribute('placeholder', 'demo');
    email.removeAttribute('pattern');
  }

  // The login view is re-rendered on every failed attempt, so keep watching.
  document.addEventListener('DOMContentLoaded', function () {
    markDemo();
    relaxLoginField();
    new MutationObserver(function () { relaxLoginField(); markDemo(); })
      .observe(document.body, { childList: true, subtree: true });
  });

  window.AXIA_DEMO_RESET = function () {
    try { localStorage.removeItem(STORE_KEY); } catch (err) { /* ignore */ }
    window.location.reload();
  };
})();
