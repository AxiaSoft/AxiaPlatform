"""Storefront settings: schema, defaults and validation.

The admin console can change how the public website behaves — the announcement
bar, the hero copy, contact details and which sections are visible. Those values
live in one JSON document so they can be written by the SQLite server and by the
GitHub Pages demo (localStorage) from the same definition.

This module is the single source of truth: ``server/app.py`` stores the values,
``tools/build_static.py`` ships the defaults to the browser build, and
``public/demo-backend.js`` reads them back.
"""
from __future__ import annotations

import re

EMAIL_RE = re.compile(r'[^@\s]+@[^@\s]+\.[^@\s]+')
LINK_RE = re.compile(r'^(?:https://[^\s<>"\']+|#/[a-z0-9/_-]*)$', re.I)

# Ordered so the console can render groups without hard-coding them twice.
GROUPS = {
    'announcement': ['announcement_enabled', 'announcement_text', 'announcement_link', 'announcement_tone'],
    'hero': ['hero_title', 'hero_accent', 'hero_subtitle'],
    'contact': ['contact_email', 'contact_phone', 'github_url', 'footer_note'],
    'sections': ['show_catalog', 'show_services', 'show_aurion', 'show_about',
                 'show_contact', 'show_assistant', 'show_prices'],
    'appearance': ['default_theme'],
    # Brands are not a form of scalar fields but a list the console edits with
    # its own editor; it is grouped here so a caller that walks GROUPS to build
    # a settings form knows the key exists and is not silently droppable.
    'brands': ['brands'],
}

SPEC = {
    'announcement_enabled': {'type': 'bool'},
    'announcement_text': {'type': 'text', 'max': 180},
    'announcement_link': {'type': 'link'},
    'announcement_tone': {'type': 'enum', 'values': ('info', 'promo', 'warning')},

    'hero_title': {'type': 'text', 'max': 90},
    'hero_accent': {'type': 'text', 'max': 90},
    'hero_subtitle': {'type': 'text', 'max': 300},

    'contact_email': {'type': 'email'},
    'contact_phone': {'type': 'text', 'max': 40},
    'github_url': {'type': 'link'},
    'footer_note': {'type': 'text', 'max': 120},

    'show_catalog': {'type': 'bool'},
    'show_services': {'type': 'bool'},
    'show_aurion': {'type': 'bool'},
    'show_about': {'type': 'bool'},
    'show_contact': {'type': 'bool'},
    'show_assistant': {'type': 'bool'},
    'show_prices': {'type': 'bool'},

    'default_theme': {'type': 'enum', 'values': ('dark', 'light', 'system')},

    # Which site brands the storefront offers. This used to be a hardcoded list
    # in public/brands.js, which meant adding a brand was a code change and a
    # deploy. It is data now: the console writes it, the storefront reads it.
    'brands': {'type': 'brands'},
}

# A brand is a small record, not free text, so it is checked field by field.
BRAND_FIELDS = ('id', 'name', 'nameFa', 'tagline', 'taglineFa',
                'accent', 'accentSoft', 'mark', 'logo')
BRAND_MAX = 12
COLOUR_RE = re.compile(r'^#[0-9a-f]{6}$', re.I)
# Asset paths are stored the way assetUrl() in the storefront reads them: a
# root-relative path ('/brand/x.png'), a bare relative one ('brand/x.png',
# which assetUrl prefixes with the deploy base) or an absolute https URL. A
# scheme such as javascript: or data: is refused because these values end up in
# an <img src> and in a CSS background.
ASSET_RE = re.compile(r'^(?:/|https://)?[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$', re.I)

# Every value here is also the copy the storefront already ships, so an empty
# settings row renders exactly the site that existed before this feature.
DEFAULTS = {
    'announcement_enabled': False,
    'announcement_text': '',
    'announcement_link': '',
    'announcement_tone': 'info',

    'hero_title': 'Building digital experiences.',
    'hero_accent': "Engineering what's next.",
    'hero_subtitle': ('AXIASOFT creates thoughtful websites, mobile applications and custom software '
                      'that help ambitious teams move forward.'),

    'contact_email': '',
    'contact_phone': '',
    'github_url': '',
    'footer_note': 'Thoughtful software. Built for what comes next.',

    'show_catalog': True,
    'show_services': True,
    'show_aurion': True,
    'show_about': True,
    'show_contact': True,
    'show_assistant': True,
    'show_prices': True,

    'default_theme': 'dark',

    'brands': [
        {'id': 'arya', 'name': 'Arya', 'nameFa': 'آریا',
         'tagline': 'Software with wings.', 'taglineFa': 'نرم‌افزاری با بال‌های پرواز.',
         'accent': '#1f5fa8', 'accentSoft': '#3f8ad8',
         'mark': 'brand/arya-mark.png', 'logo': 'brand/arya-logo.png'},
        {'id': 'ersha', 'name': 'Ersha', 'nameFa': 'ارشا',
         'tagline': 'Built to stand.', 'taglineFa': 'ساخته‌شده برای ماندن.',
         'accent': '#1b64a8', 'accentSoft': '#4d97d8',
         'mark': 'brand/ersha-mark.png', 'logo': 'brand/ersha-logo.png'},
        {'id': 'mino', 'name': 'Mino', 'nameFa': 'مینو',
         'tagline': 'Clarity, by design.', 'taglineFa': 'شفافیت، به‌صورت طراحی‌شده.',
         'accent': '#1a5c9e', 'accentSoft': '#4a8fd0',
         'mark': 'brand/mino-mark.png', 'logo': 'brand/mino-logo.png'},
        {'id': 'homa', 'name': 'Homa', 'nameFa': 'هما',
         'tagline': 'Rise above the noise.', 'taglineFa': 'بالاتر از همهمه.',
         'accent': '#1e5fa6', 'accentSoft': '#4d92d6',
         'mark': 'brand/homa-mark.png', 'logo': 'brand/homa-logo.png'},
    ],
}

# Section toggles also decide whether a route is reachable.
ROUTE_FLAGS = {
    '/products': 'show_catalog',
    '/services': 'show_services',
    '/aurion': 'show_aurion',
    '/about': 'show_about',
    '/contact': 'show_contact',
}


def _as_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.strip().lower() in ('true', '1', 'yes', 'on'):
        return True
    if isinstance(value, str) and value.strip().lower() in ('false', '0', 'no', 'off', ''):
        return False
    return None


def clean_brand(raw, seen_ids):
    """Validate one brand. Returns ``(brand, error)``; error is a field message.

    A brand drives the header lockup, the accent colour and the page title, so
    a malformed one is worse than a missing one: it would put a broken image in
    the header of every page. Every field is therefore checked here rather than
    trusted, including the two asset paths and the two colours.
    """
    if not isinstance(raw, dict):
        return None, 'A brand must be an object.'
    brand = {}
    for field in BRAND_FIELDS:
        brand[field] = str(raw.get(field) or '').strip()

    brand['id'] = brand['id'].lower()
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,30}', brand['id']):
        return None, 'Brand id must be lowercase letters, numbers and hyphens (max 31).'
    if brand['id'] in seen_ids:
        return None, f'Two brands use the id "{brand["id"]}".'
    if not brand['name']:
        return None, 'A brand needs a name.'
    if len(brand['name']) > 40 or len(brand['nameFa']) > 40:
        return None, 'A brand name must be 40 characters or fewer.'
    if len(brand['tagline']) > 90 or len(brand['taglineFa']) > 90:
        return None, 'A tagline must be 90 characters or fewer.'
    for colour in ('accent', 'accentSoft'):
        if not COLOUR_RE.fullmatch(brand[colour]):
            return None, f'{colour} must be a #rrggbb colour.'
    # The mark is what the header shows; a brand without one would empty the
    # lockup, so it is required. The logo is the larger card artwork and may be
    # left out — the product cover falls back to the default emblem.
    if not ASSET_RE.fullmatch(brand['mark']):
        return None, 'The header mark must be a path such as brand/name-mark.png.'
    if brand['logo'] and not ASSET_RE.fullmatch(brand['logo']):
        return None, 'The logo must be a path such as brand/name-logo.png.'
    return brand, None


def clean_brand_list(value):
    if not isinstance(value, list):
        return False, None
    if len(value) > BRAND_MAX:
        return False, None
    out, seen = [], set()
    for raw in value:
        brand, error = clean_brand(raw, seen)
        if error:
            return False, None
        seen.add(brand['id'])
        out.append(brand)
    return True, out


def clean_value(name, value):
    """Validate one setting. Returns ``(ok, cleaned)``.

    Unknown names are rejected rather than ignored so a typo in the console is a
    visible error instead of a setting that silently never saves.
    """
    rule = SPEC.get(name)
    if not rule:
        return False, None
    kind = rule['type']

    if kind == 'brands':
        return clean_brand_list(value)
    if kind == 'bool':
        parsed = _as_bool(value)
        return (parsed is not None), parsed

    text = str(value if value is not None else '').strip()
    if kind == 'text':
        return len(text) <= rule['max'], text
    if kind == 'email':
        if not text:
            return True, ''
        return bool(EMAIL_RE.fullmatch(text)) and len(text) <= 254, text
    if kind == 'link':
        if not text:
            return True, ''
        return bool(LINK_RE.fullmatch(text)) and len(text) <= 300, text
    if kind == 'enum':
        values = rule['values']
        if text not in values:
            return False, None
        return True, text
    if kind == 'brands':
        # Handled before the text branch, because a list is not text. It is
        # checked here so a caller that only looks at SPEC still works.
        return clean_brand_list(value)
    return False, None


def clean_settings(payload):
    """Validate a partial settings document.

    Returns ``(settings, errors)``. ``errors`` is a dict of field -> message so
    the console can show exactly which control was refused.
    """
    if not isinstance(payload, dict):
        return {}, {'_': 'Settings must be an object.'}
    cleaned = {}
    errors = {}
    for name, value in payload.items():
        ok, result = clean_value(name, value)
        if ok:
            cleaned[name] = result
        else:
            rule = SPEC.get(name) or {}
            if rule.get('type') == 'email':
                errors[name] = 'Enter a valid email address or leave the field empty.'
            elif rule.get('type') == 'link':
                errors[name] = 'Enter an https:// link or an in-site #/ link, or leave it empty.'
            elif rule.get('type') == 'enum':
                errors[name] = 'Choose one of the allowed values.'
            elif not rule:
                errors[name] = 'Unknown setting.'
            else:
                errors[name] = 'This value is too long or invalid.'
    return cleaned, errors


def merge(settings):
    """Return a complete settings document: stored values over the defaults."""
    merged = dict(DEFAULTS)
    for name in SPEC:
        if isinstance(settings, dict) and name in settings:
            ok, value = clean_value(name, settings[name])
            if ok and value is not None:
                merged[name] = value
    return merged
