/* One icon set for the whole site.
 *
 * Before this file the icons were whatever character happened to be on the
 * keyboard: ⌘ ▣ ◈ for the categories, ↗ after every call to action, ☰ for the
 * menu, × to close. They rendered at three different weights, some sat on the
 * text baseline and some did not, and a Persian page mixed them with Latin
 * numerals. They were also literal arrows - ↗ points up-right, so in an RTL
 * page the eye reads it backwards.
 *
 * Everything here is one family: 24×24 viewBox, stroke only, round caps and
 * joins, no fills, `currentColor` so a button decides the colour. The weight
 * is set in one place (`--icon-stroke`), so the set cannot drift apart.
 *
 * Usage: AXIA_ICON('arrow') returns an <svg> string. Pass a class to size it.
 */
(function () {
  'use strict';

  var PATHS = {
    /* Navigation and movement. */
    arrow: 'M5 12h14M13 6l6 6-6 6',          // forward, direction of reading
    back: 'M19 12H5M11 18l-6-6 6-6',
    external: 'M14 4h6v6M20 4l-9 9M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5',
    chevron: 'M9 6l6 6-6 6',
    close: 'M6 6l12 12M18 6 6 18',
    menu: 'M4 7h16M4 12h16M4 17h16',
    search: 'M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16ZM21 21l-4.3-4.3',

    /* Things a visitor acts on. */
    check: 'M4 12.5 9 17.5 20 6.5',
    plus: 'M12 5v14M5 12h14',
    minus: 'M5 12h14',
    edit: 'M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z',
    trash: 'M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13M10 11v6M14 11v6',
    download: 'M12 3v12M7 11l5 5 5-5M4 20h16',
    upload: 'M12 16V4M7 9l5-5 5 5M4 20h16',
    copy: 'M9 9h9a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1ZM5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1',
    filter: 'M3 5h18l-7 8v6l-4 2v-8Z',
    refresh: 'M20 11a8 8 0 1 0-2.5 5.5M20 5v6h-6',

    /* Identity and access. */
    user: 'M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z',
    lock: 'M6 11h12a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1v-8a1 1 0 0 1 1-1ZM8 11V7a4 4 0 0 1 8 0v4',
    logout: 'M15 4h3a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-3M10 17l-5-5 5-5M5 12h11',
    shield: 'M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6Z',

    /* Products the site sells. */
    globe: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM3 12h18M12 3a15 15 0 0 1 0 18 15 15 0 0 1 0-18Z',
    mobile: 'M8 3h8a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H8a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1ZM11 18h2',
    code: 'M9 18l-6-6 6-6M15 6l6 6-6 6',
    chart: 'M4 20V10M10 20V4M16 20v-7M22 20H2',
    layers: 'M12 3 2 8l10 5 10-5ZM2 14l10 5 10-5',
    terminal: 'M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1ZM8 9l3 3-3 3M14 15h3',
    spark: 'M12 3l2.2 5.8L20 11l-5.8 2.2L12 19l-2.2-5.8L4 11l5.8-2.2Z',

    /* Support and commerce. */
    message: 'M21 12a8 8 0 0 1-8 8H4l3-3a8 8 0 1 1 14-5Z',
    send: 'M22 2 11 13M22 2l-7 20-4-9-9-4Z',
    mail: 'M3 6h18a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1ZM2 7l10 7 10-7',
    phone: 'M22 17v3a1 1 0 0 1-1.1 1A19 19 0 0 1 3 4.1 1 1 0 0 1 4 3h3a1 1 0 0 1 1 .9c.1 1 .4 2 .7 3a1 1 0 0 1-.2 1L7 9.5a16 16 0 0 0 7.5 7.5L16 15.5a1 1 0 0 1 1-.2c1 .3 2 .6 3 .7a1 1 0 0 1 .9 1Z',
    card: 'M3 6h18a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1ZM2 10h20M6 15h4',
    package: 'M21 8l-9-5-9 5 9 5ZM3 8v8l9 5 9-5V8M12 13v8',
    refund: 'M9 14l-4-4 4-4M5 10h9a5 5 0 0 1 0 10h-3',
    order: 'M9 3h6a1 1 0 0 1 1 1v1h2a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h2V4a1 1 0 0 1 1-1ZM8 11h8M8 15h5',

    /* Console. */
    dashboard: 'M4 4h6v7H4ZM14 4h6v4h-6ZM14 12h6v8h-6ZM4 15h6v5H4Z',
    inbox: 'M3 12h5l2 3h4l2-3h5M3 12l3-7h12l3 7v6a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1Z',
    bell: 'M18 8a6 6 0 1 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4',
    settings: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.6 1.6 0 0 0-1-1.5 1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.5-1 1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3H9a1.6 1.6 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8V9a1.6 1.6 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1Z',
    users: 'M17 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9.5 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM22 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8',
    tag: 'M20.6 13.4 12 22l-9-9V3h10l7.6 7.6a2 2 0 0 1 0 2.8ZM7.5 7.5h.01',
    image: 'M3 4h18a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1ZM8.5 10a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3ZM21 15l-5-5L5 21',

    /* Status. */
    info: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM12 16v-5M12 8h.01',
    alert: 'M12 3 2 21h20ZM12 9v5M12 18h.01',
    clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM12 7v5l3 2',
    star: 'M12 3l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 18l-5.9 3 1.2-6.5L2.5 9.9 9.1 9Z',
    heart: 'M20.8 5.6a5 5 0 0 0-7.1 0L12 7.3l-1.7-1.7a5 5 0 1 0-7.1 7.1L12 21l8.8-8.3a5 5 0 0 0 0-7.1Z',
    sun: 'M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10ZM12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4',
    moon: 'M20.5 14.3A8.6 8.6 0 0 1 9.7 3.5a8.6 8.6 0 1 0 10.8 10.8Z',
    up: 'M12 19V5M6 11l6-6 6 6',
    down: 'M12 5v14M6 13l6 6 6-6'
  };

  /* The set is opt-in: a page that does not load icons.js keeps working, and
     AXIA_ICON falls through to an empty string rather than throwing inside a
     template literal, which would blank the whole view. */
  window.AXIA_ICON = function (name, className) {
    var d = PATHS[name];
    if (!d) return '';
    return '<svg class="icon' + (className ? ' ' + className : '') +
           '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" ' +
           'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">' +
           '<path d="' + d + '"/></svg>';
  };

  window.AXIA_ICONS = Object.keys(PATHS);
})();
