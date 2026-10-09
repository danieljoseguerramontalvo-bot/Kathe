# Silver House Barber · Estudio — inventario del sitio

Una sola página (`index.html`). Para encontrar cada parte, buscá el comentario `<!-- ============ NOMBRE ============ -->` o el `id` indicado.

## Secciones (en orden)

| # | Sección | `id` | Contenido |
|---|---|---|---|
| — | Header fijo | `#siteHeader` | Logo, menú, botón "Reservar Turno", menú móvil. Barra dorada de progreso de scroll arriba. |
| — | Hero | `#inicio` | Foto real del local a pantalla completa (slideshow lento de las 3 fotos) con el **logo grande** y el estado **Abierto/Cerrado** automático (hora de Buenos Aires). "Tu estilo, tu momento, tu mejor versión." + "Construimos confianza, imagen y personalidad", botones de reserva, **Próximo horario para reservar** (calculado en vivo) y estadísticas. En celular la foto ocupa la primera pantalla y el resto queda debajo. |
| — | Cinta animada | `.ticker` | Servicios y frases del flyer en movimiento continuo. |
| 01 | **Paquetes** | `#paquetes` | Premium, Platinum, Oro (tarjetas con foto, ícono por servicio y precio) + tarjeta ancha **Servicio para Jubilados**. |
| 02 | **Reserva online** | `#reserva` | Asistente de 5 pasos: Paquete → Barbero → Día → Horario → Datos y confirmación. Resumen lateral "Tu reserva" (en celular, barra fija abajo). |
| 03 | El Estudio | `#estudio` | 3 fotos reales del local (visor ampliable), 5 comodidades del flyer, frase "Cuidá tu imagen. Cuidá tu bienestar." |
| 04 | La Esencia | `#esencia` | Misión / Visión / Valores. |
| 05 | Los Dueños | `#duenos` | Fotos de los dueños + cita y firma de Omar Silvera. |
| 06 | Galería | `#galeria` | 5 fotos de trabajos (visor ampliable) + botón a Instagram. |
| 07 | Reseñas | `#resenas` | 3 reseñas **de muestra** (el sitio lo aclara) — reemplazar por reseñas reales. |
| — | Banner | `.cta-banner` | "Cuidá tu imagen. Cuidá tu bienestar." con el sello de la barbería. |
| 08 | Ubicación | `#ubicacion` | Dirección (link a Google Maps), WhatsApp, horario, Instagram, botón "Cómo llegar" y mapa. |
| — | Footer + WhatsApp flotante | `footer`, `#waFab` | |

## Paquetes y precios

| Paquete | Precio | Incluye |
|---|---|---|
| Premium | $35.000 | Masaje relajante de 5 minutos · Lavado de cabello · Corte a tu preferencia · Perfilado y arreglo de barba · Café de cortesía al finalizar |
| Platinum | $30.000 | Corte a tu preferencia · Arreglo y perfilado de barba · Café de cortesía |
| Oro | $20.000 | Corte a tu preferencia · Terminación con navaja |
| Servicio para Jubilados | $18.000 | Corte de cabello a su preferencia |

**Para cambiar un precio o un paquete** editá la tarjeta `<article class="pkg" data-pkg="…">`:
- los atributos `data-nombre`, `data-precio`, `data-incluye`, `data-img` y `data-duracion` alimentan el reservador (no hay que tocar el JavaScript);
- el texto visible de la tarjeta (lista y precio `<span>35.000</span>` dentro de `.pkg-price`) está dentro del mismo `<article>`;
- actualizá también el bloque JSON-LD (`makesOffer`) del `<head>` para Google.

`data-duracion` (minutos) solo se usa para el recordatorio de calendario (Premium 75, Platinum 60, Oro 45, Jubilados 40 — estimados, confirmar con la barbería). No se muestra en la página.

## Reservas: cómo funcionan

1. El cliente elige paquete, barbero, día (próximos 28 días; domingos cerrados) y horario (cada 30 min de 09:00 a 19:30, agrupados en "Por la mañana" y "Por la tarde"; los horarios pasados o a menos de 30 min se deshabilitan). Si a un día ya no le quedan horarios, el sitio lo avisa y ofrece elegir otro día.
2. Escribe su nombre (obligatorio), celular y comentario (opcionales). Puede "recordar sus datos" en su dispositivo.
3. Al confirmar se abre **WhatsApp** al +54 11 3697-0220 con el mensaje ya escrito (paquete, precio, barbero, día, hora, nombre, nota y un **código de reserva**, ej. `SH-1210-1530`).
4. Pantalla final con botones **Google Calendar** y **Recordatorio .ics** (alarma 2 h antes) para que el cliente agende el turno.

Atajos automáticos: botón "Próximo horario para reservar" en el hero, chips "Primer horario" y "Este sábado" en el paso de fecha, botones "Reservar" en cada paquete, y links directos `?paquete=premium` o `#reservar-oro`.

No hay base de datos: la barbería confirma cada turno por WhatsApp (el sitio lo aclara). Ya no se muestran horarios "ocupados" inventados.

**Configuración** (al principio del `<script>` principal, bloque "CONFIGURACIÓN"):
- `WA_NUMBER` — número de WhatsApp.
- `HORARIO` — apertura/cierre en minutos, `ultimoTurno` (último horario en que puede empezar un turno, hoy 19:30), intervalo de turnos, anticipación mínima, días cerrados (0 = domingo).
- `BARBEROS` — lista de profesionales del paso 2 (agregar acá a los dueños / barberos con su nombre).
- `DIAS_A_MOSTRAR` — cuántos días se pueden reservar.

## Fotos

| Carpeta | Uso | Notas |
|---|---|---|
| `img/estudio/estudio-1/2/3.webp` (+ `-sm`) | Hero y sección El Estudio | Fotos reales del local, con ajuste de color/contraste. |
| `img/equipo/dueno-1.webp`, `dueno-2.webp` | Los Dueños | Para poner nombres, editar los `<figcaption class="owner-cap">`. |
| `img/paquetes/*.webp` | Tarjetas de paquetes y una foto de la galería | Unsplash (uso comercial gratuito), ver `img/paquetes/CREDITS.md`. Las tarjetas usan recortes livianos (`premium-800.webp` / `-1200.webp`; Jubilados también `-v640`/`-v960` verticales para escritorio) y el reservador las miniaturas `*-thumb.webp` (`data-img`). Para cambiar una foto, reemplazar el original y regenerar los recortes con los comandos de abajo. |
| Galería (4 fotos) | `#galeria` | Fotos de stock de Unsplash del sitio original. Ideal: reemplazar por trabajos reales. |

## Contacto y datos

- Dirección: Av. La Plata 1185, CABA, Argentina
- WhatsApp: +54 11 3697-0220 (`wa.me/541136970220`) — buscar `541136970220` para cambiarlo en todos lados.
- Instagram: @silverhousebarber
- Horario: lunes a sábado 09:00–20:00, domingo cerrado.

## Estilo

- Colores de la marca: negro (`--bg #0B0B0C`) y plateado cromado (`--accent`, `--silver-grad`, `--chrome-grad`, botones `--btn-primary`). El dorado (`--gold`, `--gold-grad`) queda para detalles: corona, nombre y precio de Premium y Oro (como en el flyer), números de sección, líneas finas, estrellas, comillas y la barra de progreso. Variables en `:root`.
- Tipografías: Cinzel (títulos), Cormorant Garamond itálica (frases), Hanken Grotesk (texto), Space Mono (etiquetas).
- Animaciones sobrias en CSS: entrada suave del hero, aparición de cada bloque al entrar en pantalla, slideshow lento de fotos del local y la cinta de servicios. Respetan "reducir movimiento" del sistema; sin JavaScript todo el contenido queda visible.

## Regenerar fotos livianas (ImageMagick)

```bash
cd img/paquetes
for n in premium platinum oro; do
  convert $n.webp -gravity center -crop 1280x880+0+0 +repage -resize 800x550  -quality 78 $n-800.webp
  convert $n.webp -gravity center -crop 1280x880+0+0 +repage -resize 1200x825 -quality 78 $n-1200.webp
done
convert jubilados.webp -gravity center -crop 1280x800+0+0 +repage -resize 800x500  -quality 78 jubilados-800.webp
convert jubilados.webp -gravity center -crop 1280x800+0+0 +repage -resize 1200x750 -quality 78 jubilados-1200.webp
convert jubilados.webp -resize 640x800 -quality 78 jubilados-v640.webp
convert jubilados.webp -resize 960x1200 -quality 78 jubilados-v960.webp
for n in premium platinum oro jubilados; do convert $n.webp -gravity center -crop 1280x1280+0+0 +repage -resize 174x174 -quality 75 $n-thumb.webp; done
```
