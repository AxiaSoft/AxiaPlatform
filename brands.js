/* The product-brand catalog shown on the storefront's Websites tab.
 *
 * Each brand is a starting point a visitor can pick before browsing: choosing
 * one applies that brand to the whole site — its logo in the header, its
 * accent colour, its name in the page title — so a prospect who clicks "Arya"
 * sees the product as Arya rather than as AXIASOFT.
 *
 * A brand is only offered when the catalog actually contains a published
 * product for it, so a button never leads to an empty page. The mapping is by
 * product slug, and also by title, so a product added as "Homa" appears under
 * the Homa brand without the admin having to know a slug convention.
 */
window.AXIA_BRANDS = [
  {
    id: 'arya',
    name: 'Arya',
    nameFa: 'آریا',
    tagline: 'Software with wings.',
    taglineFa: 'نرم‌افزاری با بال‌های پرواز.',
    accent: '#1f5fa8',
    accentSoft: '#3f8ad8',
    mark: 'brand/arya-mark.png',
    logo: 'brand/arya-logo.png',
  },
  {
    id: 'ersha',
    name: 'Ersha',
    nameFa: 'ارشا',
    tagline: 'Built to stand.',
    taglineFa: 'ساخته‌شده برای ماندن.',
    accent: '#1b64a8',
    accentSoft: '#4d97d8',
    mark: 'brand/ersha-mark.png',
    logo: 'brand/ersha-logo.png',
  },
  {
    id: 'mino',
    name: 'Mino',
    nameFa: 'مینو',
    tagline: 'Clarity, by design.',
    taglineFa: 'شفافیت، به‌صورت طراحی‌شده.',
    accent: '#1a5c9e',
    accentSoft: '#4a8fd0',
    mark: 'brand/mino-mark.png',
    logo: 'brand/mino-logo.png',
  },
  {
    id: 'homa',
    name: 'Homa',
    nameFa: 'هما',
    tagline: 'Rise above the noise.',
    taglineFa: 'بالاتر از همهمه.',
    accent: '#1e5fa6',
    accentSoft: '#4d92d6',
    mark: 'brand/homa-mark.png',
    logo: 'brand/homa-logo.png',
  },
];
