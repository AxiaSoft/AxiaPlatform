"""The products the demo build ships with.

The published catalog is empty on purpose: products are created in the console.
The static/demo build (GitHub Pages) is the one exception, because a visitor who
cannot run the server still needs something to look at.

Two groups, and the split is deliberate:

- the four website builds are the *site brands* — picking one restyles the whole
  site under that name, logo and accent colour. Their artwork is the operator's
  own, so a card shows a real picture.
- the six concept products are ordinary catalog rows: a grocery storefront, a
  clinic site, a field-service app and so on. They carry no brand, so their
  cards draw the studio emblem, and they exist so that both catalog tabs have
  something behind them — an Applications tab that opens an empty grid is worse
  than no tab at all.

Every English string here is also in public/i18n.js, so the Persian site shows
Persian copy for the same products rather than a half-translated card.

Order matters: it is the order the cards appear in.
"""

DEMO_CATALOG = [
    {
        'slug': 'arya',
        'title': 'Arya — Software with wings.',
        'titleFa': '',
        'category': 'websites',
        'summary': 'Arya is a complete website build presented under the Arya brand: software with wings.',
        'description': 'Arya is one of the site brands AXIASOFT builds under. Choosing Arya launches this website with its own logo in the header, its own accent colour and its own name in the page title, so a visitor sees the product as Arya rather than as an agency pitch. Scope, pages and content are agreed before the build starts.',
        'cover': 'brand/arya-logo.webp',
        'features': ['Branded header and title', 'Responsive layout', 'Content structure agreed first', 'No payment on this site'],
        'technologies': ['HTML', 'CSS', 'JavaScript'],
        'status': 'available',
        'price_label': 'Request a quote',
        'published': 1,
        'featured': 0,
        'position': 0,
    },
    {
        'slug': 'ersha',
        'title': 'Ersha — Built to stand.',
        'titleFa': '',
        'category': 'websites',
        'summary': 'Ersha is a complete website build presented under the Ersha brand: built to stand.',
        'description': 'Ersha is one of the site brands AXIASOFT builds under. Choosing Ersha launches this website with its own logo in the header, its own accent colour and its own name in the page title, so a visitor sees the product as Ersha rather than as an agency pitch. Scope, pages and content are agreed before the build starts.',
        'cover': 'brand/ersha-logo.webp',
        'features': ['Branded header and title', 'Responsive layout', 'Content structure agreed first', 'No payment on this site'],
        'technologies': ['HTML', 'CSS', 'JavaScript'],
        'status': 'available',
        'price_label': 'Request a quote',
        'published': 1,
        'featured': 0,
        'position': 1,
    },
    {
        'slug': 'mino',
        'title': 'Mino — Clarity, by design.',
        'titleFa': '',
        'category': 'websites',
        'summary': 'Mino is a complete website build presented under the Mino brand: clarity, by design.',
        'description': 'Mino is one of the site brands AXIASOFT builds under. Choosing Mino launches this website with its own logo in the header, its own accent colour and its own name in the page title, so a visitor sees the product as Mino rather than as an agency pitch. Scope, pages and content are agreed before the build starts.',
        'cover': 'brand/mino-logo.webp',
        'features': ['Branded header and title', 'Responsive layout', 'Content structure agreed first', 'No payment on this site'],
        'technologies': ['HTML', 'CSS', 'JavaScript'],
        'status': 'available',
        'price_label': 'Request a quote',
        'published': 1,
        'featured': 0,
        'position': 2,
    },
    {
        'slug': 'homa',
        'title': 'Homa — Rise above the noise.',
        'titleFa': '',
        'category': 'websites',
        'summary': 'Homa is a complete website build presented under the Homa brand: rise above the noise.',
        'description': 'Homa is one of the site brands AXIASOFT builds under. Choosing Homa launches this website with its own logo in the header, its own accent colour and its own name in the page title, so a visitor sees the product as Homa rather than as an agency pitch. Scope, pages and content are agreed before the build starts.',
        'cover': 'brand/homa-logo.webp',
        'features': ['Branded header and title', 'Responsive layout', 'Content structure agreed first', 'No payment on this site'],
        'technologies': ['HTML', 'CSS', 'JavaScript'],
        'status': 'available',
        'price_label': 'Request a quote',
        'published': 1,
        'featured': 0,
        'position': 3,
    },
]

# The categories the demo build offers. The published site ships none — an
# operator creates them in the console — but a visitor trying the demo without a
# server still needs the catalog to be browsable, so the demo carries its own
# list. Ids match the `category` values the products above use.
DEMO_CATEGORIES = [
    {'id': 'websites', 'name': 'Websites', 'nameFa': 'وب‌سایت‌ها'},
    {'id': 'applications', 'name': 'Applications', 'nameFa': 'اپلیکیشن‌ها'},
]

# --------------------------------------------------------------------------- #
# Concept products
#
# The catalog used to hold only the four website brands, so the Applications tab
# and every non-brand card were empty: a visitor who could not run the server saw
# four cards and two of them pointed at an empty grid. These are ordinary
# products — no brand, no accent colour, no claim to be live — and they are
# written in the same voice as the brand rows: what the thing is, and what is
# deliberately not included.
#
# The English wording matches public/i18n.js entry for entry, which is where the
# Persian comes from. A paraphrase here would show up as a half-translated card
# on the Persian site.
CONCEPT_PRODUCTS = [
    {
        'slug': 'northstar-corporate',
        'title': 'Northstar Corporate',
        'category': 'websites',
        'summary': 'A confident digital home for ambitious teams.',
        'description': 'A responsive corporate website designed to clarify your value and turn visits into conversations. Includes an editorial-ready page system and a polished contact journey.',
        'cover': '',
        'features': ['Responsive pages', 'CMS-ready structure', 'Accessibility-minded', 'Lead capture'],
        'technologies': ['HTML', 'CSS', 'JavaScript', 'CMS'],
        'status': 'available',
        'price_label': 'From €4,800',
        'published': 1,
        'featured': 0,
        'position': 4,
    },
    {
        'slug': 'atelier-commerce',
        'title': 'Atelier Commerce',
        'category': 'websites',
        'summary': 'A considered storefront built for modern retail.',
        'description': 'A conversion-focused commerce experience with product storytelling, clear navigation and an extensible foundation. Scope and integrations are confirmed during discovery.',
        'cover': '',
        'features': ['Product discovery', 'Mobile-first checkout design', 'Catalog structure', 'Analytics-ready'],
        'technologies': ['HTML', 'CSS', 'JavaScript', 'Payments'],
        'status': 'available',
        'price_label': 'From €6,200',
        'published': 1,
        'featured': 0,
        'position': 5,
    },
    {
        'slug': 'careline-clinic',
        'title': 'Careline Clinic',
        'category': 'websites',
        'summary': 'A calmer, more accessible patient experience.',
        'description': 'A clean healthcare website concept with service information, provider profiles and a booking journey designed around clarity.',
        'cover': '',
        'features': ['Service directory', 'Provider profiles', 'Appointment inquiry', 'Accessible UI'],
        'technologies': ['HTML', 'CSS', 'JavaScript'],
        'status': 'showcase',
        'price_label': 'From €3,900',
        'published': 1,
        'featured': 0,
        'position': 6,
    },
    {
        'slug': 'grove-grocer',
        'title': 'Grove Grocer',
        'category': 'websites',
        'summary': 'A weekly shop that fits in a pocket.',
        'description': 'A grocery storefront concept built around a short, repeatable basket: seasonal produce up front, a saved list that survives between visits, and a checkout that asks for nothing it does not need. Delivery slots and payment integration are agreed during discovery.',
        'cover': '',
        'features': ['Saved baskets', 'Seasonal produce shelf', 'Delivery slot picker', 'Privacy-aware forms'],
        'technologies': ['HTML', 'CSS', 'JavaScript'],
        'status': 'available',
        'price_label': 'From €5,400',
        'published': 1,
        'featured': 0,
        'position': 7,
    },
    {
        'slug': 'fieldwork-mobile',
        'title': 'Fieldwork Mobile',
        'category': 'applications',
        'summary': 'Keep field teams connected and work moving.',
        'description': 'A cross-platform mobile product concept for task coordination, updates and field operations. Final feature scope is agreed with your team.',
        'cover': '',
        'features': ['Team task flows', 'Status updates', 'Offline-first planning', 'Role-aware screens'],
        'technologies': ['React Native', 'TypeScript', 'REST API'],
        'status': 'showcase',
        'price_label': 'From €7,800',
        'published': 1,
        'featured': 0,
        'position': 8,
    },
    {
        'slug': 'orbit-booking',
        'title': 'Orbit Booking',
        'category': 'applications',
        'summary': 'A friction-light booking experience for services.',
        'description': 'A mobile booking application concept with service discovery, schedule selection and clear customer communication.',
        'cover': '',
        'features': ['Booking flow', 'Availability interface', 'Customer profile', 'Notifications-ready'],
        'technologies': ['React Native', 'TypeScript'],
        'status': 'available',
        'price_label': 'From €6,100',
        'published': 1,
        'featured': 0,
        'position': 9,
    },
    {
        'slug': 'atlas-client-portal',
        'title': 'Atlas Client Portal',
        'category': 'applications',
        'summary': 'One place for every project a client has with you.',
        'description': 'A client-facing portal concept: project status, shared documents, invoices and a single thread per engagement. Access is role-aware from the first screen, and nothing is shared until somebody chooses to share it.',
        'cover': '',
        'features': ['Role-aware access', 'Shared documents', 'Status timeline', 'Secure sign-in'],
        'technologies': ['TypeScript', 'PostgreSQL', 'REST API'],
        'status': 'available',
        'price_label': 'From €11,500',
        'published': 1,
        'featured': 0,
        'position': 10,
    },
    {
        'slug': 'signal-desk',
        'title': 'Signal Desk',
        'category': 'applications',
        'summary': 'Support conversations that keep their context.',
        'description': 'A support desk concept for small teams: one queue, every channel, and the account history beside the reply box so nobody asks a customer to repeat themselves. Reporting is read-only in this concept; billing integration is out of scope.',
        'cover': '',
        'features': ['Unified inbox', 'Account history', 'Canned replies', 'Read-only reporting'],
        'technologies': ['TypeScript', 'PostgreSQL'],
        'status': 'showcase',
        'price_label': 'From €9,300',
        'published': 1,
        'featured': 0,
        'position': 11,
    },
]

# One list, so a caller cannot ship the brands and forget the rest — which is
# exactly how the Applications tab ended up empty.
DEMO_CATALOG = DEMO_CATALOG + CONCEPT_PRODUCTS
