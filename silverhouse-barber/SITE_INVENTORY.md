# Silverhouse Barber — Inventario del sitio

Copia de https://silverhousebarber.vercel.app/ tomada el 2026-10-07.
El sitio es **una sola página estática** (`index.html`) con todo el CSS y el JavaScript embebidos. No hay framework ni build.

## Archivos

| Archivo | Qué es |
|---|---|
| `index.html` | Toda la página: HTML, CSS (`<style>`, líneas 20–427) y JS (`<script>`, líneas 836–1087) |
| `silverhouse-logo.png` | Logo (480×480). Se usa en header, hero, footer y como favicon |
| `silverhouse-badge.jpg` | Sello circular (800×800) del banner "Tu lugar en la silla te espera" |
| `_screenshots/` | Capturas de la copia local (desktop 1440×900 y móvil 390×844) |

No existen en el sitio original: `robots.txt`, `sitemap.xml`, `favicon.ico`, `apple-touch-icon.png`, `manifest.json` / `site.webmanifest` (todos devuelven 404 en vivo).

## Páginas y secciones (en orden)

Única página: `/` (`index.html`). Secciones:

1. **Header** fijo (`#siteHeader`, línea 432) — logo, menú (Esencia, Servicios, Reservar, Galería, Equipo, Reseñas, Ubicación), botón "Reservar Turno", hamburguesa en móvil (menú móvil línea 461).
2. **Hero** (`#inicio`, línea 472) — "Reservá tu silla. El resto lo hacemos nosotros.", indicador Abierto/Cerrado automático, botones, estadísticas: 4.9/5 valoración, +2.000 clientes, desde 2019.
3. **01 La Esencia** (`#esencia`, línea 505) — "No es un corte. Es una declaración." + tarjetas Misión / Visión / Valores.
4. **02 El Menú — Servicios de Autor** (`#servicios`, línea 529) — 6 tarjetas de servicios.
5. **03 Reserva Online** (`#reserva`, línea 592) — asistente de 5 pasos: Servicio → Profesional → Fecha → Horario → Confirmar.
6. **04 El Trabajo — Galería** (`#galeria`, línea 641) — 5 fotos + botón a Instagram.
7. **05 La Casa — Equipo** (`#equipo`, línea 676) — 2 tarjetas.
8. **06 Lo Que Dicen — Reseñas** (`#resenas`, línea 704) — 3 reseñas (el propio sitio aclara que son *ilustrativas de muestra*).
9. **Banner CTA** (línea 732) — "Tu lugar en la silla te espera." + sello + botones Reserva / WhatsApp.
10. **07 Visitanos — Ubicación** (`#ubicacion`, línea 749) — dirección, WhatsApp, horario, Instagram + mapa de Google embebido.
11. **Footer** (línea 788) — logo, navegación, contacto, © 2026 · "Dirección de Omar Silvera · EST. 2019".
12. **Botón flotante de WhatsApp** (línea 830).

## Servicios, precios y duraciones

| Servicio | Precio | Duración | Etiqueta |
|---|---|---|---|
| Corte Clásico | $17.000 | 40 min | |
| Fade / Degradado | $20.000 | 45 min | Más Solicitado |
| Corte con Diseño | $25.000 | 60 min | |
| Arreglo de Barba | $12.000 | 30 min | |
| Texturizado / Crop | $19.000 | 40 min | |
| Combo Corte + Barba | $32.000 | 60 min | Más Solicitado |

Nota en el sitio: "* Duración estimada por servicio. Los precios pueden variar según complejidad."

## Equipo

- **Omar Silvera** — Fundador · Master Barber (en el reservador: "17 años de experiencia").
- **Barberos Silverhouse / Equipo Silverhouse** — equipo genérico, sin nombres individuales ("Barberos Senior").

## Horario

Lunes a Sábado · 09:00 a 20:00 — Domingo cerrado.
(El indicador "Abierto Ahora / Cerrado" del hero lo calcula el JS con zona horaria America/Argentina/Buenos_Aires.)

## Contacto

- **Dirección:** Av. La Plata 1185, CABA — Ciudad Autónoma de Buenos Aires, Argentina
- **WhatsApp / teléfono:** +54 11 3697-0220 → `https://wa.me/541136970220`
- **Email:** el sitio **no publica ningún email**.
- **Instagram:** @silverhousebarber → `https://instagram.com/silverhousebarber`
- No hay otras redes (Facebook, TikTok, etc.).

## Cómo funciona la reserva

No hay backend ni widget externo. El asistente de 5 pasos (JS en `index.html`) arma un mensaje y, al tocar **"Confirmar Reserva"**, abre WhatsApp (`wa.me/541136970220`) con el texto: servicio, profesional, fecha y hora. El turno lo confirma la barbería por WhatsApp.
- Domingos y fechas pasadas aparecen deshabilitados.
- Horarios: cada 30 min de 09:00 a 19:30.
- **Ojo:** los horarios "ocupados" son **simulados** (función `pseudoOccupied`, línea 1003, marca ~1 de cada 4 al azar de forma fija). No reflejan la agenda real.
- Los botones "Reservar este servicio →" de cada tarjeta preseleccionan el servicio y saltan al paso 2.

## Colores y tipografías

Variables CSS en `:root` (`index.html` líneas 21–41):

| Variable | Valor | Uso |
|---|---|---|
| `--obsidian` | `#111111` | Fondo principal (también `theme-color`) |
| `--obsidian-2` | `#0D0D0D` | Fondo alternativo |
| `--carbon` / `--carbon-2` | `#171717` / `#161616` | Tarjetas |
| `--text` | `#C7CACF` | Texto |
| `--text-dim` / `--text-mute` / `--text-faint` | `#9CA0A7` / `#7E838B` / `#5C6168` | Textos secundarios |
| `--white-ish` | `#E6E8EC` | Títulos |
| `--cyan` | `#4FD1E5` | Color de acento |
| `--cyan-bright` | `#7BE0EE` | Acento claro |
| Títulos | degradado plateado `#FFFFFF → #9DA0A6 → #F4F5F7` (`.gradient-text`) |
| WhatsApp FAB | verde WhatsApp |

Tipografías (Google Fonts, línea 18):
- **Cinzel** — títulos (`--font-display`)
- **Cinzel Decorative** — decorativa (`--font-deco`)
- **Hanken Grotesk** — texto (`--font-body`)
- **Space Mono** — etiquetas/números (`--font-mono`)

## Recursos externos (no descargados, quedan como links)

- Google Fonts (tipografías).
- GSAP 3.12.5 + ScrollTrigger desde cdnjs (animaciones).
- Google Maps embebido (mapa de ubicación).
- **Fotos de Unsplash** (stock, no propias): fondo del hero, 5 fotos de galería y 2 de equipo. Si se quiere reemplazarlas por fotos reales, ver tabla de abajo.
- Links a WhatsApp e Instagram.

## Qué archivo/línea editar

Todo está en `silverhouse-barber/index.html`:

| Qué cambiar | Dónde |
|---|---|
| Título de la pestaña / descripción SEO / Open Graph | líneas 6–14 |
| Colores | variables `:root`, líneas 21–41 |
| Tipografías | línea 18 (Google Fonts) y líneas 37–40 |
| Foto de fondo del hero | línea 137 (`background-image:url(...)`) |
| Texto del hero y estadísticas (4.9/5, +2.000, 2019) | líneas 478–497 |
| Misión / Visión / Valores | líneas 507–523 |
| **Precios y duraciones (tarjetas visibles)** | líneas 536–585 |
| **Precios y duraciones (reservador)** | array `SERVICES`, líneas 900–907 — **cambiar en los dos lugares** |
| Profesionales del reservador | array `PROFESSIONALS`, líneas 908–911 |
| Horario de atención (texto) | línea 768 |
| Horario (indicador Abierto/Cerrado) | línea 891 (`9*60` y `20*60`, domingo cerrado) |
| Horarios de turnos del reservador | `generateTimes()`, líneas 994–1001 |
| Horarios "ocupados" simulados | `pseudoOccupied()`, líneas 1003–1008 |
| Fotos de galería | líneas 647–667 |
| Equipo (fotos, nombres, textos) | líneas 682–699 |
| Reseñas | líneas 710–727 |
| Banner CTA | líneas 732–746 |
| Dirección / WhatsApp / horario / Instagram (sección Ubicación) | líneas 758–773 |
| Mapa | línea 781 |
| Footer | líneas 788–827 |
| Número de WhatsApp | buscar `541136970220` (líneas 743, 809, 821, 830 y 1082) |
| Usuario de Instagram | buscar `silverhousebarber` (líneas 670, 772, 777, 810, 818) |
| Logo / sello | reemplazar `silverhouse-logo.png` / `silverhouse-badge.jpg` (mismo nombre) |

## Observaciones

- En móvil (390 px) el documento mide ~457 px de ancho (algún elemento desborda); ocurre igual en el sitio original, no es un problema de la copia.
- Las reseñas son de muestra (lo dice el propio sitio, línea 727).
