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

  function loadSnapshot() {
    if (!productsPromise) {
      // The script tag in index.html normally wins; fetch covers the rest.
      if (Array.isArray(window.AXIA_STATIC && window.AXIA_STATIC.products)) {
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

  function explain(title, body) {
    var root = document.getElementById('modal-root');
    if (!root) {
      window.alert(title + '\n\n' + body);
      return;
    }
    root.innerHTML =
      '<div class="modal-overlay" role="presentation">' +
        '<section class="modal" role="dialog" aria-modal="true" aria-labelledby="static-modal-title">' +
          '<button class="close-button" aria-label="Close" data-static-close>&times;</button>' +
          '<div class="eyebrow">Static preview</div>' +
          '<h2 id="static-modal-title">' + title + '</h2>' +
          '<p class="form-hint" style="line-height:1.8;font-size:12px">' + body + '</p>' +
          '<div style="display:flex;gap:9px;flex-wrap:wrap;margin-top:22px">' +
            '<button class="button button-primary" data-static-close>Got it</button>' +
            '<a class="button button-quiet" href="#/products">Browse the catalog</a>' +
          '</div>' +
        '</section>' +
      '</div>';
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

  function serverMessage(action) {
    explain(
      'This action needs the live server',
      'The GitHub Pages build is a <strong>static preview</strong>: it shows the real design and the ' +
      'product catalog, but it cannot create accounts, take project requests, store support tickets or ' +
      'open the admin console, because those are written to a database by the Python API.<br><br>' +
      'To use ' + action + ', run the site locally with <code>./run_local.sh</code> (the full app) or ' +
      'deploy the container to any Python host.'
    );
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
      return loadSnapshot().then(function (products) { return json(products); });
    }

    if (isProduct(path) && method === 'GET') {
      var slug = decodeURIComponent(path.split('/').pop());
      return loadSnapshot().then(function (products) {
        var found = products.filter(function (p) { return p.slug === slug; })[0];
        return found ? json(found) : json({ error: 'Product not found' }, 404);
      });
    }

    if (isMe(path)) {
      return json({ user: null, csrf: null });
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
        explain('Catalog demo', 'Project requests are switched off in this demo build.');
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

  // Tell anyone opening the console that it lives in the server build.
  if (/\/admin\/?$/.test(location.pathname)) {
    document.addEventListener('DOMContentLoaded', function () {
      explain('The admin console needs the server',
        'This static build only publishes the public interface. Run <code>python3 provision_admin.py</code> ' +
        'from the <code>server</code> directory against a local or hosted instance to use the console.');
    });
  }
})();
