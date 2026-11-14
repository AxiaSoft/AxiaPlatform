"""The products the demo build ships with.

The published catalog is empty on purpose: products are created in the console.
The static/demo build (GitHub Pages) is the one exception, because a visitor who
cannot run the server still needs something to look at. These four website builds
are the same rows the console's Load sample catalog button installs, kept here so
a build with --demo needs no database and no browser storage.

Order matters: it is the order the cards appear in.
"""

DEMO_CATALOG = [
    {
        'slug': 'arya',
        'title': 'Arya — Software with wings.',
        'titleFa': '',
        'category': 'Websites',
        'summary': 'Arya is a complete website build presented under the Arya brand: software with wings.',
        'description': 'Arya is one of the site brands AXIASOFT builds under. Choosing Arya launches this website with its own logo in the header, its own accent colour and its own name in the page title, so a visitor sees the product as Arya rather than as an agency pitch. Scope, pages and content are agreed before the build starts.',
        'cover': 'brand/arya-logo.png',
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
        'category': 'Websites',
        'summary': 'Ersha is a complete website build presented under the Ersha brand: built to stand.',
        'description': 'Ersha is one of the site brands AXIASOFT builds under. Choosing Ersha launches this website with its own logo in the header, its own accent colour and its own name in the page title, so a visitor sees the product as Ersha rather than as an agency pitch. Scope, pages and content are agreed before the build starts.',
        'cover': 'brand/ersha-logo.png',
        'features': ['Branded header and title', 'Responsive layout', 'Content structure agreed first', 'No payment on this site'],
        'technologies': ['HTML', 'CSS', 'JavaScript'],
        'status': 'available',
        'price_label': 'Request a quote',
        'published': 1,
        'featured': 0,
        'position': 0,
    },
    {
        'slug': 'mino',
        'title': 'Mino — Clarity, by design.',
        'titleFa': '',
        'category': 'Websites',
        'summary': 'Mino is a complete website build presented under the Mino brand: clarity, by design.',
        'description': 'Mino is one of the site brands AXIASOFT builds under. Choosing Mino launches this website with its own logo in the header, its own accent colour and its own name in the page title, so a visitor sees the product as Mino rather than as an agency pitch. Scope, pages and content are agreed before the build starts.',
        'cover': 'brand/mino-logo.png',
        'features': ['Branded header and title', 'Responsive layout', 'Content structure agreed first', 'No payment on this site'],
        'technologies': ['HTML', 'CSS', 'JavaScript'],
        'status': 'available',
        'price_label': 'Request a quote',
        'published': 1,
        'featured': 0,
        'position': 0,
    },
    {
        'slug': 'homa',
        'title': 'Homa — Rise above the noise.',
        'titleFa': '',
        'category': 'Websites',
        'summary': 'Homa is a complete website build presented under the Homa brand: rise above the noise.',
        'description': 'Homa is one of the site brands AXIASOFT builds under. Choosing Homa launches this website with its own logo in the header, its own accent colour and its own name in the page title, so a visitor sees the product as Homa rather than as an agency pitch. Scope, pages and content are agreed before the build starts.',
        'cover': 'brand/homa-logo.png',
        'features': ['Branded header and title', 'Responsive layout', 'Content structure agreed first', 'No payment on this site'],
        'technologies': ['HTML', 'CSS', 'JavaScript'],
        'status': 'available',
        'price_label': 'Request a quote',
        'published': 1,
        'featured': 0,
        'position': 0,
    },
]
