# Silver House Barber · Estudio — sitio web

Sitio estático de una sola página (`index.html`), sin build ni dependencias externas obligatorias.
Las animaciones son CSS livianas (sin librerías) y las tipografías están incluidas en el propio sitio, así que no depende de ningún CDN.

```
silverhouse-barber/
├── index.html              ← todo el sitio (HTML + CSS + JS)
├── fonts/                  ← Cinzel, Cormorant Garamond, Hanken Grotesk, Space Mono (auto-alojadas)
├── img/
│   ├── estudio/            ← fotos reales del local (hero y sección "El Estudio")
│   ├── equipo/             ← fotos de los dueños
│   ├── paquetes/           ← fotos de cada paquete (Unsplash, ver CREDITS.md)
│   └── og-silverhouse.jpg  ← imagen para compartir en WhatsApp / redes
├── silverhouse-logo.png    ← logo (también favicon)
├── silverhouse-badge.jpg   ← sello circular del banner
└── SITE_INVENTORY.md       ← qué hay en el sitio y dónde se edita cada cosa
```

## Ver en local

```bash
cd silverhouse-barber
python3 -m http.server 8000   # abrir http://localhost:8000
```

## Publicar en Vercel

1. En vercel.com → **Add New… → Project** → importar el repo de GitHub `danieljoseguerramontalvo-bot/Kathe`
   (o, en el proyecto existente `silverhousebarber`, **Settings → Git** → conectar este repo).
2. Configuración del proyecto:
   - **Root Directory:** `silverhouse-barber`
   - **Framework Preset:** `Other`
   - **Build Command / Output Directory / Install Command:** vacíos
3. **Deploy.** Cada push a la rama de producción vuelve a publicar el sitio.

Alternativa sin Git: arrastrar la carpeta `silverhouse-barber/` a vercel.com/new (o `npx vercel --prod` dentro de la carpeta).
El archivo `.vercelignore` evita publicar las capturas y los `.md`.
