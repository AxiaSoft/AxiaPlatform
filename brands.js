/* The product-brand catalog shown on the storefront's Websites tab.
 *
 * A brand is a starting point a visitor can pick before browsing: choosing one
 * applies that brand to the whole site — its logo in the header, its accent
 * colour, its name in the page title — so a prospect who clicks "Arya" sees the
 * product as Arya rather than as AXIASOFT.
 *
 * The list is DATA, not code. It lives in the site settings document, which the
 * admin console writes (GET/PUT /api/admin/settings) and the static build ships
 * as data/settings.json. This file therefore only supplies two things:
 *
 *   1. a fallback, used when a build has no settings snapshot at all, so a
 *      half-installed site still renders rather than throwing, and
 *   2. window.AXIA_BRANDS as a live view of the settings, refreshed whenever
 *      settings load.
 *
 * Before this, the four brands were hardcoded here, so adding a fifth meant
 * editing source and redeploying. Nothing below is consulted once settings
 * arrive; the array is replaced wholesale.
 */

(function () {
  'use strict';

  /* Used only when no settings document exists — never merged with one, so a
     brand the administrator deleted cannot reappear from this list. */
  var FALLBACK = [];

  /* The storefront reads window.AXIA_BRANDS directly, in several places, and
     caches nothing, so the array object itself must stay stable and have its
     contents replaced in place. Reassigning the window property would leave
     any code that already captured the old array looking at stale brands. */
  var live = [];
  window.AXIA_BRANDS = live;

  /* A brand is only usable when it can drive the header: an id to key state on,
     a name to show, a mark to draw and an accent to colour. Anything missing a
     piece is dropped rather than half-applied. */
  function usable(brand) {
    return brand && typeof brand === 'object' &&
      String(brand.id || '').trim() &&
      String(brand.name || '').trim() &&
      String(brand.mark || '').trim() &&
      /^#[0-9a-f]{6}$/i.test(String(brand.accent || ''));
  }

  function apply(list) {
    var source = Array.isArray(list) && list.length ? list : FALLBACK;
    live.length = 0;
    for (var i = 0; i < source.length; i++) {
      if (!usable(source[i])) continue;
      live.push({
        id: String(source[i].id).toLowerCase(),
        name: String(source[i].name),
        nameFa: String(source[i].nameFa || source[i].name),
        tagline: String(source[i].tagline || ''),
        taglineFa: String(source[i].taglineFa || source[i].tagline || ''),
        accent: String(source[i].accent),
        accentSoft: String(source[i].accentSoft || source[i].accent),
        mark: String(source[i].mark),
        logo: String(source[i].logo || source[i].mark)
      });
    }
    // A brand that no longer exists must not stay applied to the header.
    try {
      var chosen = localStorage.getItem('axia-brand');
      if (chosen && !live.some(function (b) { return b.id === chosen; })) {
        localStorage.removeItem('axia-brand');
      }
    } catch (e) { /* private mode: nothing to clean up */ }
    return live;
  }

  /* Shared with the browser demo backend, which has to refuse the same input
     the Python server refuses. Keeping one implementation means the two cannot
     drift into accepting different brands. Mirrors clean_brand in
     server/site_settings.py. */
  var MARK_RE = /^(?:\/|https:\/\/)?[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$/i;
  var COLOUR_RE = /^#[0-9a-f]{6}$/i;
  var BRAND_FIELDS = ['id', 'name', 'nameFa', 'tagline', 'taglineFa',
                      'accent', 'accentSoft', 'mark', 'logo'];

  window.AXIA_BRANDS_VALIDATE = function (value) {
    if (!Array.isArray(value)) return { ok: false, error: 'Expected a list of brands.' };
    if (value.length > 12) return { ok: false, error: 'At most 12 brands.' };
    var out = [], seen = {};
    for (var i = 0; i < value.length; i++) {
      var raw = value[i], b = {}, field;
      if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
        return { ok: false, error: 'Each brand must be an object.' };
      }
      for (var f = 0; f < BRAND_FIELDS.length; f++) {
        field = BRAND_FIELDS[f];
        b[field] = String(raw[field] == null ? '' : raw[field]).trim();
      }
      b.id = b.id.toLowerCase();
      if (!/^[a-z0-9][a-z0-9-]{0,30}$/.test(b.id)) {
        return { ok: false, error: 'Brand id must be lowercase letters, numbers and hyphens.' };
      }
      if (seen[b.id]) return { ok: false, error: 'Two brands use the id "' + b.id + '".' };
      if (!b.name) return { ok: false, error: 'A brand needs a name.' };
      if (b.name.length > 40 || b.nameFa.length > 40) {
        return { ok: false, error: 'A brand name must be 40 characters or fewer.' };
      }
      if (b.tagline.length > 90 || b.taglineFa.length > 90) {
        return { ok: false, error: 'A tagline must be 90 characters or fewer.' };
      }
      if (!COLOUR_RE.test(b.accent) || !COLOUR_RE.test(b.accentSoft)) {
        return { ok: false, error: 'Brand colours must be #rrggbb.' };
      }
      if (!MARK_RE.test(b.mark)) {
        return { ok: false, error: 'The header mark must be a path such as brand/name-mark.png.' };
      }
      if (b.logo && !MARK_RE.test(b.logo)) {
        return { ok: false, error: 'The logo must be a path such as brand/name-logo.png.' };
      }
      seen[b.id] = true;
      out.push(b);
    }
    return { ok: true, brands: out };
  };

  window.AXIA_BRANDS_APPLY = apply;
  apply(window.AXIA_STATIC && window.AXIA_STATIC.settings && window.AXIA_STATIC.settings.brands);
})();
