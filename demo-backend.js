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

  var STORE_KEY = 'axia-demo-products-v1';
  var SETTINGS_KEY = 'axia-demo-settings-v1';
  var SESSION_KEY = 'axia-demo-session-v1';
  var CSRF = 'demo-csrf-token';
  // Sample orders are generated from this seed so the dashboard's numbers are
  // stable between reloads instead of drifting with the clock.
  var DEMO_SEED = 20261107;

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
    // First visit: the editable copy starts from the build's product snapshot.
    // That snapshot is deliberately empty (products are created here), so the
    // demo catalog starts empty too. `Load sample catalog` in the console's
    // Maintenance tab adds illustrative rows on request - never automatically,
    // because the public site must not invent products.
    return seedProducts();
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
    if (copy.featured === undefined) copy.featured = 0;
    if (copy.position === undefined) copy.position = 0;
    return copy;
  }

  /* ------------------------------------------------------------ settings */
  // The console can change the public storefront (announcement bar, hero copy,
  // contact details, visible sections). The defaults live in data/settings.js so
  // the same document is used by the Python server and this demo.
  function defaults() {
    return (window.AXIA_STATIC && window.AXIA_STATIC.settings) || {};
  }

  function readSettings() {
    var merged = {};
    var base = defaults();
    for (var k in base) if (Object.prototype.hasOwnProperty.call(base, k)) merged[k] = base[k];
    var raw = null;
    try { raw = localStorage.getItem(SETTINGS_KEY); } catch (err) { return merged; }
    if (!raw) return merged;
    try {
      var stored = JSON.parse(raw);
      if (stored && typeof stored === 'object') {
        for (var key in stored) if (Object.prototype.hasOwnProperty.call(stored, key)) merged[key] = stored[key];
      }
    } catch (err) { /* corrupted value: fall back to the shipped defaults */ }
    return merged;
  }

  /* The rules mirror server/site_settings.py. They exist so the demo refuses the
     same input the real server refuses, instead of quietly accepting it. */
  var SETTINGS_SPEC = {
    announcement_enabled: 'bool', announcement_text: 'text', announcement_link: 'link',
    announcement_tone: 'tone', hero_title: 'text', hero_accent: 'text', hero_subtitle: 'text',
    contact_email: 'email', contact_phone: 'text', github_url: 'link', footer_note: 'text',
    show_catalog: 'bool', show_services: 'bool', show_aurion: 'bool', show_about: 'bool',
    show_contact: 'bool', show_assistant: 'bool', show_prices: 'bool', default_theme: 'theme'
  };
  var EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
  var LINK_RE = /^(?:https:\/\/[^\s<>"']+|#\/[a-z0-9/_-]*)$/i;

  function validateSettings(patch) {
    var errors = {};
    for (var key in patch) {
      if (!Object.prototype.hasOwnProperty.call(patch, key)) continue;
      var kind = SETTINGS_SPEC[key];
      var value = patch[key];
      if (!kind) { errors[key] = 'Unknown setting.'; continue; }
      if (kind === 'bool') {
        if (typeof value !== 'boolean') errors[key] = 'Expected true or false.';
      } else if (kind === 'email') {
        if (value && (!EMAIL_RE.test(String(value)) || String(value).length > 254)) errors[key] = 'Invalid email.';
      } else if (kind === 'link') {
        if (value && (!LINK_RE.test(String(value)) || String(value).length > 300)) errors[key] = 'Invalid link.';
      } else if (kind === 'tone') {
        if (['info', 'promo', 'warning'].indexOf(value) < 0) errors[key] = 'Invalid tone.';
      } else if (kind === 'theme') {
        if (['dark', 'light', 'system'].indexOf(value) < 0) errors[key] = 'Invalid theme.';
      } else if (typeof value !== 'string' || value.length > 300) {
        errors[key] = 'Invalid text.';
      }
    }
    return errors;
  }

  function writeSettings(patch) {
    var merged = readSettings();
    for (var key in patch) {
      if (Object.prototype.hasOwnProperty.call(patch, key)) merged[key] = patch[key];
    }
    try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(merged)); } catch (err) { /* ignore */ }
    return merged;
  }

  function orderProducts(list) {
    return list.slice().sort(function (a, b) {
      return (Number(b.featured) || 0) - (Number(a.featured) || 0)
        || (Number(a.position) || 0) - (Number(b.position) || 0)
        || (Number(a.id) || 0) - (Number(b.id) || 0);
    });
  }

  function byId(list, id) {
    for (var i = 0; i < list.length; i++) if (Number(list[i].id) === Number(id)) return list[i];
    return null;
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
  // Illustrative rows so the dashboard is not an empty shell in the demo. They
  // are never written anywhere and the site never claims they are real: the
  // orders/customers/tickets/refunds screens read from these, prices are zero.
  var DEMO_PRODUCTS = [
    { slug: 'northstar-corporate', title: 'Northstar Corporate', category: 'Websites', price_label: '€4,800 – €7,200',
      status: 'available', github_url: 'https://github.com/AxiaSoft/northstar-corporate', published: 1, featured: 1, position: 1 },
    { slug: 'atlas-client-portal', title: 'Atlas Client Portal', category: 'Applications', price_label: '€6,500 – €11,000',
      status: 'available', github_url: 'https://github.com/AxiaSoft/atlas-client-portal', published: 1, featured: 0, position: 2 },
    { slug: 'studio-cms', title: 'Studio CMS', category: 'Websites', price_label: '€3,200 – €5,400',
      status: 'available', github_url: 'https://github.com/AxiaSoft/studio-cms', published: 1, featured: 0, position: 3 },
    { slug: 'field-notes', title: 'Field Notes', category: 'Applications', price_label: '€2,900 – €4,600',
      status: 'showcase', github_url: '', published: 1, featured: 0, position: 4 },
    { slug: 'aurion', title: 'AURION', category: 'Aurion', price_label: 'Concept',
      status: 'showcase', github_url: 'https://github.com/AxiaSoft/aurion', published: 1, featured: 0, position: 5 },
    { slug: 'signal-desk', title: 'Signal Desk', category: 'Applications', price_label: '€5,100 – €8,400',
      status: 'available', github_url: 'https://github.com/AxiaSoft/signal-desk', published: 0, featured: 0, position: 6 }
  ];

  var STATUSES = ['Submitted', 'Under Review', 'Requirements Analysis', 'Quotation Sent',
                  'Awaiting Confirmation', 'In Development', 'Testing', 'Ready for Delivery',
                  'Delivered', 'Cancelled'];
  var OPEN_STATES = ['Open', 'In progress'];

  function ago(days) {
    var d = new Date(Date.now() - days * 86400000);
    return d.toISOString().slice(0, 19).replace('T', ' ');
  }

  // A tiny seeded PRNG keeps the illustrative numbers stable per page load.
  function rng(seed) {
    var s = seed >>> 0;
    return function () {
      s = (s * 1664525 + 1013904223) >>> 0;
      return s / 4294967296;
    };
  }

  var FIRST = ['Lena', 'Marco', 'Sara', 'Yusuf', 'Nina', 'Tom', 'Amir', 'Clara', 'David', 'Mina',
               'Jonas', 'Aylin', 'Felix', 'Reyhan', 'Paul', 'Elif'];
  var LAST = ['Hoffmann', 'Bauer', 'Kaya', 'Fischer', 'Weber', 'Schmidt', 'Aydın', 'Wagner',
              'Becker', 'Schulz', 'Yilmaz', 'Keller'];

  var SAMPLE_ORDERS = (function () {
    var random = rng(DEMO_SEED);
    var rows = [];
    for (var i = 0; i < 24; i++) {
      var first = FIRST[i % FIRST.length];
      var last = LAST[(i * 7) % LAST.length];
      var status = STATUSES[Math.floor(random() * 6)];
      rows.push({
        id: i + 1,
        number: 'AX-24' + String(10 + i).slice(-2) + '-' + String(100 + i).slice(-3),
        user_id: 2 + (i % 6),
        product_id: 1,
        name: first + ' ' + last,
        email: (first + '.' + last).toLowerCase().replace(/[^a-z.]/g, '') + '@example.com',
        phone: '',
        description: 'Illustrative project request used to show the console layout.',
        requirements: '',
        contact_method: 'Email',
        status: status,
        created_at: ago(3 + i * 4),
        updated_at: ago(1 + i * 2),
        product_title: DEMO_PRODUCTS[i % 3].title
      });
    }
    return rows;
  })();

  var SAMPLE_CUSTOMERS = (function () {
    return FIRST.slice(0, 6).map(function (first, i) {
      var last = LAST[i];
      return {
        id: 2 + i, name: first + ' ' + last,
        email: (first + '.' + last).toLowerCase().replace(/[^a-z.]/g, '') + '@example.com',
        phone: '', created_at: ago(40 + i * 11), active: i === 5 ? 0 : 1,
        order_count: 3 + i, ticket_count: i % 3
      };
    });
  })();

  var SAMPLE_TICKETS = (function () {
    var subjects = ['Question about the client portal scope', 'Invoice details for the kickoff',
                    'Can we add a second language?', 'Timeline for the testing phase',
                    'Preview link does not open'];
    return subjects.map(function (subject, i) {
      var person = SAMPLE_CUSTOMERS[i % SAMPLE_CUSTOMERS.length];
      return {
        id: i + 1, ref: 'AXS-24' + String(10 + i), user_id: person.id, email: person.email,
        subject: subject, message: 'Illustrative support message used to show the console layout.',
        status: i === 0 ? 'Open' : (i === 4 ? 'Closed' : 'In progress'),
        priority: 'Normal', created_at: ago(2 + i * 3), messages: []
      };
    });
  })();

  function seedProducts() {
    return snapshot().map(function (p, i) {
      return normalise({
        id: p.id || i + 1,
        slug: p.slug, title: p.title, category: p.category,
        summary: p.summary || 'Illustrative catalog entry for the demo console.',
        description: p.description || 'Illustrative catalog entry for the demo console.',
        cover: p.cover || '', features: p.features || [], technologies: p.technologies || [],
        status: p.status || 'available', price_label: p.price_label || 'Request a quote',
        github_url: p.github_url || '', published: p.published === undefined ? 1 : p.published,
        featured: p.featured || 0, position: p.position || i + 1,
        created_at: p.created_at || ago(70 - i * 6)
      });
    });
  }

  function demoUser() {
    var fa = document.documentElement.lang === 'fa';
    return { id: 1, name: fa ? 'مدیر نمایشی' : 'Demo Administrator', email: 'demo', role: 'admin', phone: '' };
  }
  var DEMO_CREDENTIALS = { email: 'demo', password: 'demo' };

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

  /* --------------------------------------------------------------- audit */
  // A short, believable activity log so the dashboard's "what changed" panel is
  // not empty. Actions the demo visitor actually takes are prepended to it.
  var LOCAL_AUDIT = [];
  function demoAudit() {
    var base = [
      { id: 901, action: 'login', entity: 'session', entity_id: 'demo', created_at: ago(0), actor_name: demoUser().name, actor_email: 'demo' },
      { id: 900, action: 'settings', entity: 'settings', entity_id: 'site', created_at: ago(1), actor_name: demoUser().name, actor_email: 'demo' },
      { id: 899, action: 'create', entity: 'product', entity_id: '2', created_at: ago(2), actor_name: demoUser().name, actor_email: 'demo' },
      { id: 898, action: 'update', entity: 'product', entity_id: '1', created_at: ago(3), actor_name: demoUser().name, actor_email: 'demo' },
      { id: 897, action: 'status_change', entity: 'order', entity_id: '3', created_at: ago(4), actor_name: demoUser().name, actor_email: 'demo' },
      { id: 896, action: 'ticket_reply', entity: 'ticket', entity_id: '2', created_at: ago(5), actor_name: demoUser().name, actor_email: 'demo' }
    ];
    return LOCAL_AUDIT.concat(base);
  }
  function noteAudit(action, entity, eid) {
    LOCAL_AUDIT.unshift({
      id: Date.now(), action: action, entity: entity, entity_id: String(eid),
      created_at: ago(0), actor_name: demoUser().name, actor_email: 'demo'
    });
  }
  window.AXIA_DEMO_AUDIT = demoAudit;

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

    // ---- public storefront settings -------------------------------------
    if (path === '/api/site') {
      return json({ settings: readSettings() });
    }

    // ---- catalog --------------------------------------------------------
    if (path === '/api/products' && method === 'GET') {
      var live = readProducts().filter(function (p) { return p.published; });
      return json(orderProducts(live));
    }
    if (path.indexOf('/api/products/') === 0 && method === 'GET') {
      var slug = decodeURIComponent(path.split('/').pop());
      var found = readProducts().filter(function (p) { return p.slug === slug && p.published; })[0];
      return found ? json(found) : fail('Product not found', 404);
    }

    // ---- admin ----------------------------------------------------------
    if (path.indexOf('/api/admin/') === 0) {
      if (!signedIn()) return fail('Administrator access required', 403);

      if (path === '/api/admin/overview' || path === '/api/admin/dashboard') {
        // With an empty catalog the dashboard has no products to rank, so the
        // ranking falls back to the illustrative orders' product titles.
        var products = orderProducts(readProducts());
        var orders = SAMPLE_ORDERS;
        var settings = readSettings();
        var counts = {
          customers: SAMPLE_CUSTOMERS.length,
          customers_active: SAMPLE_CUSTOMERS.filter(function (c) { return c.active; }).length,
          customers_suspended: SAMPLE_CUSTOMERS.filter(function (c) { return !c.active; }).length,
          orders: orders.length,
          pending: orders.filter(function (o) { return ['Submitted', 'Under Review', 'Requirements Analysis'].indexOf(o.status) >= 0; }).length,
          active: orders.filter(function (o) { return ['In Development', 'Testing'].indexOf(o.status) >= 0; }).length,
          completed: orders.filter(function (o) { return o.status === 'Delivered'; }).length,
          cancelled: orders.filter(function (o) { return o.status === 'Cancelled'; }).length,
          tickets: SAMPLE_TICKETS.filter(function (t) { return t.status === 'Open'; }).length,
          tickets_open: SAMPLE_TICKETS.filter(function (t) { return t.status !== 'Closed'; }).length,
          refunds: 0,
          published: products.filter(function (p) { return p.published; }).length,
          hidden: products.filter(function (p) { return !p.published; }).length,
          featured: products.filter(function (p) { return p.published && p.featured; }).length
        };
        return json({
          counts: counts, orders: orders, products: products,
          tickets: SAMPLE_TICKETS.slice(0, 8), customers: SAMPLE_CUSTOMERS,
          refunds: [], settings: settings, demo: true,
          activity: demoAudit()
        });
      }

      if (path === '/api/admin/settings' && method === 'GET') {
        return json({ settings: readSettings() });
      }

      if (path === '/api/admin/settings' && method === 'PUT') {
        var fieldErrors = validateSettings(payload);
        if (Object.keys(fieldErrors).length) {
          return json({ error: 'Some settings were not saved.', fields: fieldErrors }, 400);
        }
        noteAudit('settings', 'settings', 'site');
        return json({ ok: true, settings: writeSettings(payload) });
      }

      if (path === '/api/admin/customers') {
        return json({ customers: SAMPLE_CUSTOMERS, total: SAMPLE_CUSTOMERS.length });
      }

      /* The console reads these the same way it reads the server's, so the demo
         answers them with its illustrative rows instead of the generic
         "not available" error. */
      if ((path === '/api/support' || path === '/api/orders' || path === '/api/refunds') && method === 'GET') {
        if (path === '/api/support') return json(SAMPLE_TICKETS);
        if (path === '/api/orders') return json(SAMPLE_ORDERS);
        return json([]);
      }

      if (path === '/api/admin/orders' && method === 'GET') {
        return json({ orders: SAMPLE_ORDERS });
      }

      if (path === '/api/admin/refunds') {
        return json({ refunds: [] });
      }

      if (path === '/api/admin/audit') {
        return json(demoAudit());
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
          published: payload.published ? 1 : 0,
          featured: payload.featured ? 1 : 0,
          position: Number(payload.position) || 0,
          created_at: ago(0)
        });
        list.push(created);
        writeProducts(list);
        noteAudit('create', 'product', created.id);
        return json({ id: created.id }, 201);
      }

      if (path === '/api/admin/products' && method === 'PUT') {
        var items = readProducts();
        var id = Number(payload.id);
        var target = byId(items, id);
        if (!target) return fail('Product not found', 404);
        for (var key in payload) {
          if (!Object.prototype.hasOwnProperty.call(payload, key) || key === 'id') continue;
          if (key === 'features' || key === 'technologies') {
            if (Array.isArray(payload[key])) target[key] = payload[key];
          } else if (key === 'published' || key === 'featured') {
            target[key] = payload[key] ? 1 : 0;
          } else if (key === 'position') {
            target[key] = Number(payload[key]) || 0;
          } else {
            target[key] = payload[key];
          }
        }
        writeProducts(items);
        noteAudit('update', 'product', id);
        return json({ ok: true });
      }

      if (path === '/api/admin/products' && method === 'DELETE') {
        var rows = readProducts();
        var pid = Number(payload.id);
        var hit = byId(rows, pid);
        if (!hit) return fail('Product not found', 404);
        hit.published = 0;
        writeProducts(rows);
        noteAudit('unpublish', 'product', pid);
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

  /* The console's "Load sample catalog" button. It is never automatic: the
     published site ships an empty catalog on purpose, and the public storefront
     must not invent products a visitor could mistake for real ones. */
  window.AXIA_DEMO_SAMPLES = function () {
    var list = readProducts();
    DEMO_PRODUCTS.forEach(function (p, i) {
      if (list.some(function (x) { return x.slug === p.slug; })) return;
      list.push(normalise({
        id: nextId(list), slug: p.slug, title: p.title, category: p.category,
        summary: 'Illustrative catalog entry added by the demo console.',
        description: 'Illustrative catalog entry added by the demo console.',
        cover: '', features: [], technologies: [], status: p.status,
        price_label: p.price_label, github_url: p.github_url,
        published: p.published, featured: p.featured, position: p.position,
        created_at: ago(60 - i * 8)
      }));
    });
    writeProducts(list);
    return list.length;
  };

  window.AXIA_DEMO_RESET = function () {
    try { localStorage.removeItem(STORE_KEY); } catch (err) { /* ignore */ }
    window.location.reload();
  };
})();
