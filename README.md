# AZUR Aparthotel

Sitio boutique para apartamentos en **Wayaca (Aruba)** y **Barranquilla (Colombia)**.
Sin build ni dependencias: HTML, CSS y JavaScript vanilla.

## Ver el sitio localmente

```bash
python3 -m http.server 8000
```

Luego entra a `http://localhost:8000`.

## Estructura

- `index.html` — landing: hero, apartamentos, experiencias por ciudad, galería, testimonios.
- `booking.html` — flujo de reserva: fechas → apartamento → datos → pago.
- `css/styles.css` — tokens de diseño, componentes y estados de scroll/reduced-motion.
- `js/data.js` — datos de apartamentos, experiencias y testimonios (edítalo para cambiar contenido).
- `js/main.js` — navegación, hero, scroll-reveal, tabs, galería/lightbox, carrusel.
- `js/booking.js` — stepper, calendario, resumen persistente y simulación de pago.

## Reemplazar contenido de marcador por assets reales

El sitio no usa fotos externas: en su lugar hay un sistema de "tiles" con gradientes
(`css/styles.css`, clases `.tile-1` … `.tile-6`) para no depender de imágenes de stock
sin licencia. Para usar fotografía real:

1. Agrega tus archivos en `assets/images/` y `assets/video/`.
2. En `index.html` / `js/main.js` / `js/data.js`, reemplaza los `<div class="tile tile-N">`
   por `<img src="assets/images/...">` donde corresponda.
3. Para el video del hero, coloca el archivo en `assets/video/hero-loop.mp4`
   (y opcionalmente un poster en `assets/images/hero-poster.jpg`). El hero ya está
   preparado para reproducirlo automáticamente; si el archivo no existe, muestra un
   degradado animado de respaldo — no hay que cambiar código.

Los mapas de cada apartamento/experiencia usan `iframe` de Google Maps sin API key
(`js/data.js` define las coordenadas aproximadas de cada zona).

## Métodos de pago

El paso de pago es una simulación (sin backend ni procesador real). Los badges de
Visa/Mastercard/Amex/PSE son representaciones tipográficas simplificadas — al conectar
un procesador real, reemplázalos por los logos oficiales con licencia del proveedor.

## Despliegue

Publicado en Vercel como proyecto estático (sin framework).
