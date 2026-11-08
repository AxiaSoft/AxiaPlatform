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
}

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


def clean_value(name, value):
    """Validate one setting. Returns ``(ok, cleaned)``.

    Unknown names are rejected rather than ignored so a typo in the console is a
    visible error instead of a setting that silently never saves.
    """
    rule = SPEC.get(name)
    if not rule:
        return False, None
    kind = rule['type']

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
