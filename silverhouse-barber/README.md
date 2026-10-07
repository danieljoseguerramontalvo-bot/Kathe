# Silverhouse Barber — sitio web

Copia completa de https://silverhousebarber.vercel.app/ (fuente oficial a partir de ahora).
Sitio estático: `index.html` + 2 imágenes. Sin build, sin dependencias.

Ver `SITE_INVENTORY.md` para el contenido y qué línea editar para cada cosa.

## Ver en local

```bash
cd silverhouse-barber
python3 -m http.server 8000   # abrir http://localhost:8000
```

## Publicar en Vercel

1. En Vercel: **Add New… → Project** e importar este repositorio de GitHub (o, en el proyecto existente `silverhousebarber`, ir a **Settings → Git** y conectarlo a este repo).
2. En **Settings → Build & Deployment** (o al importar):
   - **Root Directory:** `silverhouse-barber`
   - **Framework Preset:** `Other`
   - **Build Command:** vacío (desactivado)
   - **Output Directory:** vacío / `.`
   - **Install Command:** vacío
3. **Deploy.** Cada push a la rama de producción vuelve a publicar el sitio.

La carpeta `_screenshots/` y los `.md` también se publican pero no molestan; si se prefiere excluirlos, agregar un `.vercelignore` con `_screenshots/` y `*.md`.
