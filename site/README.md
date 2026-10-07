# Apart Hotel — enhancements on the real site

This folder is **not** a from-scratch rebuild. It's the actual production
site (https://aparthotel-site.vercel.app/, "Apart Hotel", Edificio K58,
Altos de Riomar, Barranquilla — 3 units: 401A, 502, 702) pulled file-for-file
from the live deployment, with targeted luxury-detail enhancements layered
on top. The earlier `index.html` / `booking.html` / `css/` / `js/` at the
repo root were an unrelated from-scratch build (kept only as reference, see
closed PR #1) and should not be confused with this folder.

Only the files actually touched are included here — this is **not** a full
mirror (no image/video assets, no `/en/` pages, no `apartamentos.html`,
`ubicacion.html`, `experiencias.html`, `contacto.html`, `politicas.html`,
`404.html`, `robots.txt`, `sitemap.xml`, `vercel.json`). To deploy, these
files replace their same-named counterparts in the real site's source
(root-level `index.html`/`reservar.html`/`apartamento-*.html`, and
`assets/styles.css` / `assets/app.js` / `assets/booking.js`); everything
else on the real site is untouched and should be left exactly as it is.

The real site also has `tools/build.mjs`, suggesting these HTML pages may
be generated from a template by a local build script. These are direct
edits to the built output — reconcile them back into that build source if
one exists, rather than letting a future rebuild silently overwrite them.

## What changed and why

1. **Testimonials carousel** (`index.html`, `assets/styles.css`) — the
   existing "Los huéspedes" section was a static 3-column grid of real
   guest quotes (captions honestly marked "Huésped por confirmar" — no
   names were invented). Converted to a one-at-a-time carousel by reusing
   the site's own hero-slider engine (`.slides`/`.tick` in `app.js`), so
   there's no second slideshow implementation. Autoplay, pause-on-hover/
   tab-blur and `prefers-reduced-motion` all come for free from that
   existing engine.

2. **Payment/checkout polish** (`reservar.html`, `assets/styles.css`) —
   the booking flow already had a full demo checkout (payment-method
   chips, a modal with tabs per method, a busy-state button, a confirmation
   panel) clearly labelled "Demostración" throughout — this was not
   touched conceptually. Added: a "Pago seguro" lock-icon trust line next
   to both pay CTAs (`.paybox-f`, `.chk-ft`), subtle depth/hover on the
   payment chips, and replaced the spinning-circle loading state on
   `#chkGo` with a skeleton/shimmer sweep (no generic spinner, per brief).
   No official payment-network logos were fabricated — the existing
   text/icon "wordmark chip" approach was kept and just polished, both
   for trademark safety and because colored brand logos would clash with
   the site's restrained monochrome + single-accent design system.

3. **Global micro-interaction gaps** (`assets/styles.css`) — the site
   already had extensive hover/transition coverage; filled the specific
   gaps found: hover-zoom on `.room-img img` (apartment detail "por
   dentro" photos, previously static), a hover state on the static `.pm`
   payment rows, and `.rv` scroll-reveal added to `.room` articles and
   `.stats .cell` elements that previously popped in instantly instead of
   fading/sliding in like the rest of the page.

4. **Apartment detail pages** (`apartamento-401a.html`, `-502.html`,
   `-702.html`) — same `.rv` reveal-class additions applied consistently
   across all three unit pages.

Verified locally with a static server + Playwright: carousel ticks render
and switch slides, the checkout modal opens with the new trust badge,
`#chkGo` correctly gets the shimmer `is-busy` state and the confirmation
panel appears, and `.rv` reveal classes are present on all three unit
pages — no console errors.
