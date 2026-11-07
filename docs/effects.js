/* ==========================================================================
   AXIASOFT — effects engine
   Small, dependency-free animation layer for the public site and the admin
   console. Everything is opt-in and degrades safely:

   * respects prefers-reduced-motion and coarse pointers;
   * pauses all work when the tab is hidden;
   * caps particle count by viewport area and device memory hints;
   * one shared requestAnimationFrame loop instead of many timers;
   * cleans up observers between SPA route changes (no leaks).

   It never changes layout, never fetches anything, and never touches text
   content, so it cannot affect accessibility or the API contract.
   ========================================================================== */
(function () {
  'use strict';

  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)');
  const root = document.documentElement;
  const isAdmin = /\/admin(\/|$)/.test(location.pathname) || document.body.dataset.fx === 'admin';

  let rafId = 0;
  let running = false;
  const frameTasks = new Set();
  let observed = 0;

  /* ---------------------------------------------------------------- utils */
  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
  const prefersReduced = () => reduced.matches;
  const canHover = () => finePointer.matches && !prefersReduced();

  function onFrame(fn) {
    frameTasks.add(fn);
    if (!running) start();
    return () => frameTasks.delete(fn);
  }

  function start() {
    if (running) return;
    running = true;
    rafId = requestAnimationFrame(tick);
  }

  let lastTick = 0;

  function tick(now) {
    if (document.hidden) {
      running = false;
      return;
    }
    // Cap the shared loop to ~60fps even on 120Hz+ displays: cheaper and smooth.
    if (now - lastTick < 15) {
      rafId = requestAnimationFrame(tick);
      return;
    }
    lastTick = now;
    frameTasks.forEach((fn) => {
      try { fn(now); } catch (err) { frameTasks.delete(fn); }
    });
    if (frameTasks.size && !document.hidden) {
      rafId = requestAnimationFrame(tick);
    } else {
      running = false;
    }
  }

  /* ------------------------------------------------- 1. scroll progress */
  function initScrollProgress() {
    const bar = document.createElement('div');
    bar.className = 'scroll-progress';
    bar.setAttribute('aria-hidden', 'true');
    document.body.appendChild(bar);

    const apply = () => {
      const doc = document.documentElement;
      const max = doc.scrollHeight - window.innerHeight;
      const value = max > 0 ? clamp(window.scrollY / max, 0, 1) : 0;
      doc.style.setProperty('--scroll-progress', value.toFixed(4));
      document.body.classList.toggle('is-scrolled', window.scrollY > 12);
    };

    let queued = false;
    const schedule = () => {
      if (queued) return;
      queued = true;
      requestAnimationFrame(() => { queued = false; apply(); });
    };
    window.addEventListener('scroll', schedule, { passive: true });
    window.addEventListener('resize', schedule, { passive: true });
    apply();
  }

  /* ------------------------------------------------ 2. pointer spotlight */
  function initSpotlight() {
    if (!canHover()) return;
    const spot = document.createElement('div');
    spot.className = 'fx-spotlight';
    spot.setAttribute('aria-hidden', 'true');
    document.body.appendChild(spot);

    let targetX = -1000, targetY = -1000, x = -1000, y = -1000, live = false;

    window.addEventListener('pointermove', (event) => {
      targetX = event.clientX;
      targetY = event.clientY;
      if (!live) {
        live = true;
        x = targetX; y = targetY;
        spot.classList.add('is-live');
      }
    }, { passive: true });

    window.addEventListener('pointerleave', () => {
      live = false;
      spot.classList.remove('is-live');
    }, { passive: true });

    document.addEventListener('mouseleave', () => {
      live = false;
      spot.classList.remove('is-live');
    });

    onFrame(() => {
      if (!live) return;
      x += (targetX - x) * 0.14;
      y += (targetY - y) * 0.14;
      spot.style.transform = `translate3d(${x.toFixed(1)}px, ${y.toFixed(1)}px, 0)`;
    });
  }

  /* ------------------------------------------------- 3. particle field */
  function initParticles() {
    if (prefersReduced()) return;
    const canvas = document.createElement('canvas');
    canvas.id = 'fx-canvas';
    canvas.setAttribute('aria-hidden', 'true');
    document.body.appendChild(canvas);
    const ctx = canvas.getContext('2d', { alpha: true });
    if (!ctx) { canvas.remove(); return; }

    let dpr = 1, w = 0, h = 0, particles = [];
    let pointer = { x: -9999, y: -9999 };

    const count = () => {
      const area = window.innerWidth * window.innerHeight;
      const base = clamp(Math.round(area / 26000), 14, 58);
      // Weak devices get a lighter field.
      const mem = navigator.deviceMemory || 8;
      return Math.round(clamp(base * (mem < 4 ? 0.5 : 1), 8, 58));
    };

    function resize() {
      dpr = clamp(window.devicePixelRatio || 1, 1, 2);
      w = window.innerWidth;
      h = window.innerHeight;
      canvas.width = Math.floor(w * dpr);
      canvas.height = Math.floor(h * dpr);
      canvas.style.width = w + 'px';
      canvas.style.height = h + 'px';
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const total = count();
      if (particles.length > total) particles.length = total;
      while (particles.length < total) particles.push(spawn());
    }

    function spawn() {
      return {
        x: Math.random() * w,
        y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.18,
        vy: (Math.random() - 0.5) * 0.18,
        r: 0.6 + Math.random() * 1.5,
        a: 0.18 + Math.random() * 0.42,
        tw: 0.4 + Math.random() * 1.6
      };
    }

    const isLight = () => root.dataset.theme === 'light';

    window.addEventListener('resize', resize, { passive: true });
    window.addEventListener('pointermove', (e) => { pointer.x = e.clientX; pointer.y = e.clientY; }, { passive: true });
    document.addEventListener('mouseleave', () => { pointer.x = -9999; pointer.y = -9999; });

    let time = 0;
    onFrame((now) => {
      if (!time) time = now;
      const dt = clamp(now - time, 1, 48) / 16.67;
      time = now;
      ctx.clearRect(0, 0, w, h);
      const light = isLight();
      const dot = light ? '43, 79, 140' : '150, 196, 255';
      const link = light ? '43, 79, 140' : '110, 168, 255';

      for (const p of particles) {
        p.x += p.vx * dt;
        p.y += p.vy * dt;

        // Soft repulsion from the pointer: keeps the field feeling physical.
        const dx = p.x - pointer.x, dy = p.y - pointer.y;
        const d2 = dx * dx + dy * dy;
        if (d2 < 26000 && d2 > 1) {
          const force = (1 - d2 / 26000) * 0.9;
          const d = Math.sqrt(d2);
          p.x += (dx / d) * force * dt;
          p.y += (dy / d) * force * dt;
        }

        if (p.x < -20) p.x = w + 20; else if (p.x > w + 20) p.x = -20;
        if (p.y < -20) p.y = h + 20; else if (p.y > h + 20) p.y = -20;

        const twinkle = 0.72 + Math.sin((now / 1000) * p.tw + p.x) * 0.28;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${dot}, ${(p.a * twinkle).toFixed(3)})`;
        ctx.fill();
      }

      // Constellation links — bounded by the small particle count.
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const a = particles[i], b = particles[j];
          const dx = a.x - b.x, dy = a.y - b.y;
          const dist2 = dx * dx + dy * dy;
          if (dist2 > 16800) continue;
          const alpha = (1 - dist2 / 16800) * 0.16;
          ctx.strokeStyle = `rgba(${link}, ${alpha.toFixed(3)})`;
          ctx.lineWidth = 0.6;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
    });

    resize();
    requestAnimationFrame(() => canvas.classList.add('is-ready'));
  }

  /* -------------------------------------------------- 4. aurora backdrop */
  function initAurora() {
    if (document.querySelector('.aurora-field')) return;
    const field = document.createElement('div');
    field.className = 'aurora-field';
    field.setAttribute('aria-hidden', 'true');
    document.body.insertBefore(field, document.body.firstChild);
  }

  /* ----------------------------------------------------- 5. scroll reveal */
  let revealObserver = null;

  function initReveal() {
    if (prefersReduced()) {
      document.querySelectorAll('.reveal').forEach((el) => el.classList.add('is-visible'));
      return;
    }
    if (!revealObserver) {
      revealObserver = new IntersectionObserver((entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          entry.target.classList.add('is-visible');
          revealObserver.unobserve(entry.target);
        }
      }, { rootMargin: '0px 0px -8% 0px', threshold: 0.06 });
    }
    decorateReveal();
  }

  /** Mark natural content blocks for reveal, with a small stagger. */
  function decorateReveal() {
    const groups = [
      ['.section-heading', 0],
      ['.category-card', 70],
      ['.product-card', 60],
      ['.process .step', 55],
      ['.trust-strip span', 45],
      ['.two-col > *', 90],
      ['.cta-band', 0],
      ['.page-head', 0],
      ['.stat-card', 50],
      ['.package', 45],
      ['.feature-list .feature-item', 40],
      ['.workflow-card', 60],
      ['.detail-copy > *', 55]
    ];
    for (const [selector, step] of groups) {
      const nodes = document.querySelectorAll(selector);
      nodes.forEach((el, index) => {
        if (el.classList.contains('reveal') || el.dataset.fxNoReveal) return;
        // A card that already animates on hover keeps its own transform logic.
        el.classList.add('reveal');
        if (step) el.style.setProperty('--reveal-delay', Math.min(index * step, 420) + 'ms');
        el.dataset.reveal = el.dataset.reveal || 'up';
        observed++;
        revealObserver.observe(el);
      });
    }
  }

  function resetReveal() {
    document.querySelectorAll('.reveal').forEach((el) => {
      el.classList.remove('is-visible');
      if (revealObserver) revealObserver.unobserve(el);
      el.classList.remove('reveal');
      el.style.removeProperty('--reveal-delay');
    });
    observed = 0;
  }

  /* ------------------------------------------------------------ 6. ripple */
  function initRipple() {
    document.addEventListener('pointerdown', (event) => {
      if (prefersReduced() || event.button !== 0) return;
      const target = event.target.closest('.button, .btn, .tab, .side-link, .chat-chip, .icon-button');
      if (!target || target.dataset.noRipple === '1') return;
      const rect = target.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      const size = Math.max(rect.width, rect.height) * 2.1;
      const span = document.createElement('span');
      span.className = 'fx-ripple' + (target.classList.contains('button-primary') || target.classList.contains('btn-primary') ? '' : ' dark');
      span.style.width = span.style.height = size + 'px';
      span.style.left = (event.clientX - rect.left) + 'px';
      span.style.top = (event.clientY - rect.top) + 'px';
      if (getComputedStyle(target).position === 'static') target.style.position = 'relative';
      target.appendChild(span);
      span.addEventListener('animationend', () => span.remove(), { once: true });
      setTimeout(() => span.remove(), 900);
    }, { passive: true });
  }

  /* ------------------------------------------------- 7. subtle parallax */
  function initParallax() {
    if (!canHover() || isAdmin) return;
    const heroArt = document.querySelector('.hero-art');
    if (!heroArt) return;
    let current = 0, target = 0;
    window.addEventListener('scroll', () => {
      target = clamp(window.scrollY * 0.08, 0, 60);
    }, { passive: true });
    onFrame(() => {
      if (Math.abs(target - current) < 0.2) return;
      current += (target - current) * 0.12;
      heroArt.style.setProperty('--parallax-y', current.toFixed(1) + 'px');
    });
  }

  /* ----------------------------------------------- 8. view-transition hook */
  function animateRoute() {
    const app = document.getElementById('app');
    if (!app || prefersReduced()) return;
    app.classList.remove('fx-enter');
    // Force a reflow so the animation restarts on each navigation.
    void app.offsetWidth;
    app.classList.add('fx-enter');
    setTimeout(() => app.classList.remove('fx-enter'), 900);
  }

  /* ------------------------------------------------- 9. navbar underline */
  function initNavUnderline() {
    document.querySelectorAll('.nav-links a').forEach((link) => {
      link.addEventListener('pointerenter', () => {
        const rtl = root.dir === 'rtl';
        link.style.setProperty('--nav-origin', rtl ? '100%' : '0%');
      }, { passive: true });
    });
  }

  /* ---------------------------------------------- 10. re-init after render */
  let reinitTimer = 0;

  function reinit(options = {}) {
    clearTimeout(reinitTimer);
    reinitTimer = setTimeout(() => {
      if (revealObserver) {
        document.querySelectorAll('.reveal').forEach((el) => {
          if (!el.classList.contains('is-visible')) revealObserver.observe(el);
        });
      }
      decorateReveal();
      initParallax();
      initNavUnderline();
      if (options.route) animateRoute();
    }, 30);
  }

  /* ------------------------------------------------------------ bootstrap */
  function boot() {
    if (prefersReduced()) {
      root.classList.add('fx-calm');
    } else {
      initAurora();
      initParticles();
      initSpotlight();
    }
    initScrollProgress();
    initRipple();
    initReveal();
    initParallax();
    initNavUnderline();

    // The SPA replaces #app.innerHTML on every route change.
    const app = document.getElementById('app');
    if (app) {
      new MutationObserver(() => reinit({ route: true })).observe(app, { childList: true });
    }
    const adminRoot = document.getElementById('adminApp');
    if (adminRoot) {
      new MutationObserver(() => reinit()).observe(adminRoot, { childList: true, subtree: false });
    }

    reduced.addEventListener?.('change', () => {
      if (prefersReduced()) {
        document.querySelectorAll('.reveal').forEach((el) => el.classList.add('is-visible'));
        root.classList.add('fx-calm');
      }
    });

    // Pause the shared loop while the tab is in the background.
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden && frameTasks.size) start();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }

  window.AXIAEffects = { reinit, animateRoute, resetReveal };
})();
