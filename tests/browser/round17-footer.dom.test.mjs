// The footer claim is a layout assertion, and jsdom has no layout engine. What
// it CAN do is confirm the cascade resolves the way the fix assumes: that no
// later rule overrides body's display, main's flex, or the footer's flex on the
// routes that render. A wrong cascade is the only way this fix silently fails.
import fs from 'fs';
import { fileURLToPath } from 'url';
const D = process.env.STATIC_DIST || fileURLToPath(new URL('../../dist/', import.meta.url));
const css = fs.readFileSync(D + 'styles.css', 'utf8');
const out = [];
const ck = (n, ok, x = '') => out.push(`${ok ? 'PASS' : 'FAIL'}  ${n}${x ? '  (' + x + ')' : ''}`);

// Every rule that could touch body/main/footer, in source order.
/* The stylesheet is minified: many rules share a line and are separated by
   `}` rather than newlines, and comments sit between them. Strip the comments
   first, then read each `selector { ... }` pair. */
const clean = css.replace(/\/\*[\s\S]*?\*\//g, '');
const rules = [...clean.matchAll(/([^{}@]+)\{([^}]*)\}/g)]
  .map((m) => ({ sel: m[1].trim().replace(/^[;,}\s]+/, ''), body: m[2] }));

const forSel = (target) => rules.filter((r) => r.sel.split(',').map((s) => s.trim()).includes(target));

const bodyRules = forSel('body');
ck('exactly one rule targets body', bodyRules.length === 1, `${bodyRules.length}`);
const b = bodyRules[0].body;
ck('body is a column', /display:\s*flex/.test(b) && /flex-direction:\s*column/.test(b));
ck('body has a viewport floor', /min-height:\s*100vh/.test(b));

const mainRules = forSel('main');
ck('main grows into the slack', mainRules.some((r) => /flex:\s*1 0 auto/.test(r.body)),
   mainRules.map((r) => r.body.trim()).join(' | '));

const footerRules = forSel('.footer');
ck('the footer refuses to stretch', footerRules.some((r) => /flex:\s*none/.test(r.body)));
ck('the footer is never fixed', !footerRules.some((r) => /position:\s*fixed/.test(r.body)));

// The blog loads blog.css after styles.css; make sure it does not undo any of it.
const blogCss = fs.readFileSync(D + 'blog.css', 'utf8');
ck('blog.css does not override body display', !/(^|})\s*body\s*\{[^}]*display:/.test(blogCss));
ck('blog.css does not override .footer', !/(^|})\s*\.footer\s*\{/.test(blogCss));

// The announcement bar and the ambients are body's other children; confirm they
// sit in the column without claiming the slack.
const ambient = rules.filter((r) => /\.ambient/.test(r.sel) && /position:\s*fixed/.test(r.body));
ck('the ambients are out of flow', ambient.length > 0);

// The header is sticky, which is fine in a column: it is not a flex item that
// can grow.
ck('the header cannot grow', !rules.some((r) => r.sel === '.topbar' && /flex:\s*1/.test(r.body)));

console.log(out.join('\n'));
const bad = out.filter((l) => l.startsWith('FAIL'));
console.log(bad.length ? `\n${bad.length} FAILURES` : '\nALL PASS');
process.exit(bad.length ? 1 : 0);
