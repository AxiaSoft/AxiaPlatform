/* ==========================================================================
   AXIASOFT — static build adapter (GitHub Pages)

   Generated builds have no Python server, so the two API calls the storefront
   makes during startup are answered locally:

     GET /api/products  -> the catalog snapshot in data/products.json
     GET /api/me        -> always signed out

   Anything that genuinely needs the backend (accounts, project requests,
   support, refunds, the admin console) is intercepted and explained through the
   site's own modal, instead of failing with an unreadable error. The real
   server build never loads this file, so behaviour there is unchanged.

   Everything is scope-guarded: if a real API ever answers on the same origin,
   the adapter backs off and lets the real response through.
   ========================================================================== */
(function () {
  'use strict';

  if (!window.fetch || window.AXIA_STATIC_ADAPTER) return;
  window.AXIA_STATIC_ADAPTER = true;

  var config = window.AXIA_STATIC || {};
  var BASE = config.base || '/';
  var MODE = config.mode || 'static';
  var snapshotUrl = BASE + 'data/products.json';
  var productsPromise = null;

  var needsServer = [
    '/api/register', '/api/login', '/api/logout',
    '/api/orders', '/api/support', '/api/refunds',
    '/api/admin/'
  ];

  // Storefront settings edited in the demo console live next to the products.
  var SETTINGS_KEY = 'axia-demo-settings-v1';

  function isProducts(url) { return url === '/api/products'; }
  function isProduct(url) { return url.indexOf('/api/products/') === 0; }
  function isMe(url) { return url === '/api/me'; }
  function needsBackend(url) {
    for (var i = 0; i < needsServer.length; i++) {
      if (needsServer[i].charAt(needsServer[i].length - 1) === '/' ) {
        if (url.indexOf(needsServer[i]) === 0) return true;
      } else if (url === needsServer[i]) {
        return true;
      }
    }
    return false;
  }

  // Minimal Response stand-in for environments without the Fetch API's Response
  // (very old browsers, and the jsdom test harness). The app only needs .ok,
  // .status, .headers.get() and .json().
  function fallbackResponse(body, status) {
    var text = JSON.stringify(body);
    return {
      ok: status >= 200 && status < 300,
      status: status,
      statusText: '',
      headers: { get: function (name) { return /^content-type$/i.test(name) ? 'application/json; charset=utf-8' : null; } },
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
          headers: { 'Content-Type': 'application/json; charset=utf-8' }
        }));
      } catch (err) { /* fall through to the stand-in */ }
    }
    return Promise.resolve(fallbackResponse(body, code));
  }

  /* The admin console on this static build writes its products to
     localStorage (see demo-backend.js). Those edits are the newest truth, so
     they take precedence over the shipped snapshot - that is what makes a
     product added in the demo panel appear on the public site immediately. */
  var DEMO_STORE_KEY = 'axia-demo-products-v1';

  function demoProducts() {
    var raw = null;
    try { raw = localStorage.getItem(DEMO_STORE_KEY); } catch (err) { return null; }
    if (!raw) return null;
    try {
      var parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : null;
    } catch (err) { return null; }
  }

  function demoOrder(list) {
    return list.slice().sort(function (a, b) {
      return (Number(b.featured) || 0) - (Number(a.featured) || 0)
        || (Number(a.position) || 0) - (Number(b.position) || 0)
        || (Number(a.id) || 0) - (Number(b.id) || 0);
    });
  }

  function demoSettings() {
    var base = (window.AXIA_STATIC && window.AXIA_STATIC.settings) || null;
    var merged = base ? JSON.parse(JSON.stringify(base)) : {};
    try {
      var raw = localStorage.getItem(SETTINGS_KEY);
      if (raw) {
        var stored = JSON.parse(raw);
        if (stored && typeof stored === 'object') {
          for (var k in stored) if (Object.prototype.hasOwnProperty.call(stored, k)) merged[k] = stored[k];
        }
      }
    } catch (err) { /* corrupted value: use the shipped defaults */ }
    return merged;
  }

  function loadSnapshot() {
    if (!productsPromise) {
      var edited = demoProducts();
      if (edited) {
        productsPromise = Promise.resolve(demoOrder(edited));
      } else if (Array.isArray(window.AXIA_STATIC && window.AXIA_STATIC.products)) {
        // The script tag in index.html normally wins; fetch covers the rest.
        productsPromise = Promise.resolve(window.AXIA_STATIC.products);
      } else {
        productsPromise = fetch(snapshotUrl, { credentials: 'same-origin' })
          .then(function (response) {
            if (!response.ok) throw new Error('HTTP ' + response.status);
            return response.json();
          })
          .catch(function () { return []; });
      }
    }
    return productsPromise;
  }

  /* ------------------------------------------------------------ messaging */
  function closeModal() {
    var root = document.getElementById('modal-root');
    if (!root) return;
    root.innerHTML = '';
    document.documentElement.classList.remove('modal-open');
    document.body.style.removeProperty('overflow');
  }

  /* The modal is built as markup, so the text swapper in i18n.js cannot see it
     coming and will not translate it. Build it in the active language instead. */
  var COPY = {
    en: {
      close: 'Close',
      eyebrow: 'Static preview',
      got: 'Got it',
      browse: 'Browse the catalog',
      title: 'This action needs the live server',
      body: 'The GitHub Pages build is <strong>static preview</strong> only: it shows the real design and the ' +
            'product catalog, but it cannot create accounts, take project requests, store support tickets or ' +
            'open the admin console, because those are written to a database by the Python API.<br><br>' +
            'To use ' + '{action}' + ', run the site locally with <code dir="ltr" style="unicode-bidi:isolate">./run_local.sh</code> (the full app) or ' +
            'deploy the container to any Python host.'
    },
    fa: {
      close: 'بستن',
      eyebrow: 'پیش‌نمایش استاتیک',
      got: 'متوجه شدم',
      browse: 'دیدن کاتالوگ',
      title: 'این کار به سرور زنده نیاز دارد',
      body: 'نسخهٔ گیت‌هاب پیجز فقط یک <strong>پیش‌نمایش استاتیک</strong> است: طراحی واقعی و کاتالوگ محصولات را ' +
            'نشان می‌دهد، اما نمی‌تواند حساب بسازد، درخواست پروژه ثبت کند، تیکت پشتیبانی ذخیره کند یا پنل مدیریت ' +
            'را باز کند؛ چون این موارد توسط API پایتون در پایگاه داده نوشته می‌شوند.<br><br>' +
            'برای استفاده از ' + '{action}' + '، سایت را به‌صورت محلی با <code dir="ltr" style="unicode-bidi:isolate">./run_local.sh</code> اجرا کنید ' +
            '(نسخهٔ کامل) یا کانتینر را روی هر میزبان پایتون مستقر کنید.'
    }
  };

  function isPersian() {
    return document.documentElement.lang === 'fa';
  }

  function explain(title, body, actionText) {
    var resolved = actionText === undefined ? body : actionText;
    var root = document.getElementById('modal-root');
    if (!root) {
      window.alert(title + '\n\n' + String(resolved).replace(/<[^>]+>/g, ''));
      return;
    }
    var copy = isPersian() ? COPY.fa : COPY.en;
    root.innerHTML =
      '<div class="modal-overlay" role="presentation">' +
        '<section class="modal" role="dialog" aria-modal="true" aria-labelledby="static-modal-title">' +
          '<button class="close-button" aria-label="' + copy.close + '" data-static-close>&times;</button>' +
          '<div class="eyebrow">' + copy.eyebrow + '</div>' +
          '<h2 id="static-modal-title">' + (isPersian() ? copy.title : title) + '</h2>' +
          '<p class="form-hint" style="line-height:1.8;font-size:12px"></p>' +
          '<div style="display:flex;gap:9px;flex-wrap:wrap;margin-top:22px">' +
            '<button class="button button-primary" data-static-close>' + copy.got + '</button>' +
            '<a class="button button-quiet" href="#/products">' + copy.browse + '</a>' +
          '</div>' +
        '</section>' +
      '</div>';
    // The body is a template with {action}; fill it in and keep the markup.
    var note = root.querySelector('.form-hint');
    if (note) {
      note.innerHTML = copy.body.replace('{action}', resolved);
    }
    root.querySelectorAll('[data-static-close]').forEach(function (el) {
      el.addEventListener('click', closeModal);
    });
    root.querySelector('.modal-overlay').addEventListener('click', function (event) {
      if (event.target.classList.contains('modal-overlay')) closeModal();
    });
    document.addEventListener('keydown', function once(event) {
      if (event.key === 'Escape') { closeModal(); document.removeEventListener('keydown', once); }
    });
    var focusable = root.querySelector('[data-static-close]');
    if (focusable) focusable.focus();
  }

  // Human-readable names for the actions the adapter blocks, in both languages.
  var ACTIONS = {
    'sign-in': { en: 'sign-in', fa: 'ورود به حساب' },
    'an account': { en: 'an account', fa: 'ساخت حساب' },
    'project requests': { en: 'project requests', fa: 'ثبت درخواست پروژه' },
    'a support request': { en: 'a support request', fa: 'ثبت درخواست پشتیبانی' },
    'the admin console': { en: 'the admin console', fa: 'پنل مدیریت' },
    'your account': { en: 'your account', fa: 'حساب کاربری' }
  };

  function serverMessage(action) {
    var known = ACTIONS[action];
    var label = known ? (isPersian() ? known.fa : known.en) : action;
    explain('This action needs the live server', '', label);
  }

  /* --------------------------------------------------------------- fetch */
  var originalFetch = window.fetch.bind(window);

  window.fetch = function (input, init) {
    var url = typeof input === 'string' ? input : (input && input.url) || '';
    var method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
    var path = url.split('?')[0];

    // Let absolute URLs (none today) and the snapshot itself pass straight through.
    if (/^[a-z]+:/i.test(url) || path.indexOf('/data/') === 0) {
      return originalFetch(input, init);
    }

    if (isProducts(path) && method === 'GET') {
      return loadSnapshot().then(function (products) {
        return json(products.filter(function (p) { return p.published === undefined || p.published; }));
      });
    }

    if (isProduct(path) && method === 'GET') {
      var slug = decodeURIComponent(path.split('/').pop());
      return loadSnapshot().then(function (products) {
        var found = products.filter(function (p) {
          return p.slug === slug && (p.published === undefined || p.published);
        })[0];
        return found ? json(found) : json({ error: 'Product not found' }, 404);
      });
    }

    if (isMe(path)) {
      return json({ user: null, csrf: null });
    }

    /* The storefront reads its announcement bar, hero copy and section toggles
       from here. On the admin pages the demo backend answers this itself (and
       validates writes), so the adapter only fills in for the storefront. */
    if (path === '/api/site' && !window.AXIA_DEMO_BACKEND) {
      return json({ settings: demoSettings() });
    }

    if (needsBackend(path)) {
      serverMessage(path.indexOf('/api/admin/') === 0 ? 'the admin console' : 'your account');
      return json({ error: 'This static build has no server. Run the site locally for the full app.' }, 503);
    }

    return originalFetch(input, init);
  };

  /* --------------------------------------------------- intercept the UI */
  // The app delegates clicks to these hooks; capture them first so the user
  // gets an explanation instead of a dead form.
  document.addEventListener('click', function (event) {
    var target = event.target.closest ? event.target.closest('[data-order], #accountButton, [data-open-auth]') : null;
    if (!target) return;
    if (target.id === 'accountButton') {
      event.preventDefault();
      event.stopImmediatePropagation();
      serverMessage('sign-in');
      return;
    }
    if (target.hasAttribute('data-open-auth')) {
      event.preventDefault();
      event.stopImmediatePropagation();
      serverMessage('an account');
      return;
    }
    if (target.hasAttribute('data-order')) {
      event.preventDefault();
      event.stopImmediatePropagation();
      if (MODE === 'demo') {
        explain(isPersian() ? 'نمایش کاتالوگ' : 'Catalog demo',
                isPersian() ? 'درخواست پروژه در این نسخهٔ نمایشی غیرفعال است.'
                            : 'Project requests are switched off in this demo build.');
      } else {
        serverMessage('project requests');
      }
    }
  }, true);

  // Chat: keep it honest rather than letting it promise a follow-up.
  document.addEventListener('click', function (event) {
    if (!event.target.closest) return;
    if (event.target.closest('#chat-launcher')) return; // panel itself still opens
    var human = event.target.closest('.chat-chip');
    if (human && /person|human|انسان|کارشناس/i.test(human.textContent || '')) {
      event.preventDefault();
      event.stopImmediatePropagation();
      serverMessage('a support request');
    }
  }, true);

  // Reset transient UI on route changes so a stale modal never blocks the page.
  window.addEventListener('hashchange', closeModal);

})();
