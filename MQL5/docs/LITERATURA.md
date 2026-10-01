# Revisión bibliográfica: ¿dónde puede haber ventaja en XAUUSD?

**Método:** revisión hecha con búsqueda web el 2026-09-29.
- El proxy de este entorno bloqueó la lectura de los textos completos (SSRN, ScienceDirect, arXiv, hfm.com…). Todo sale de resúmenes, abstracts y reseñas.
- Lo que no se pudo comprobar se marca **[sin verificar]**.

**Escala de evidencia:**

| Nivel | Qué significa |
|---|---|
| Fuerte | Revisado por pares, muchas muestras y replicado |
| Moderada | Revisado por pares con limitaciones, o preprint serio |
| Débil | Tesis, blog o backtest de un bróker |

## 1. Tendencia / momentum de serie temporal

**Evidencia en carteras de futuros (fuerte):**
- Moskowitz, Ooi y Pedersen (2012, *JFE*): 58 futuros, oro incluido. El retorno de 1 a 12 meses predice el del mes siguiente.
- Hurst, Ooi y Pedersen (2017, *JPM*): 1880–2016, positivo en todas las décadas.
- Lempérière et al. (2014): el mismo resultado en dos siglos de datos.
- Szakmary, Shen y Sharma (2010, *JBF*): medias móviles y canales, neto de costes, positivo en 22 de 28 commodities.

**Matices para operar un solo activo (moderada/fuerte):**
- Huang, Li, Wang y Zhou (2020, *JFE*): activo por activo la predictibilidad es débil (47 de 55 con t < 1.65). La estrategia se parece mucho a una apuesta por la media histórica, es decir, a ir comprado.
- Kim, Tse y Wald (2016, *JFM*): gran parte del alfa viene de escalar por volatilidad. Sin ese escalado, el resultado es parecido a comprar y mantener.
- Kurth, Eisler, Rej y Bouchaud (2026, arXiv 2607.01550, preprint): desde 2008 la tendencia de corto plazo dejó de pagar en contratos de «tick pequeño», como el oro **[sin verificar la clasificación del oro]**.

**Oro intradía:**
- Batten et al. (2018, *JIFMIM*): las medias móviles intradía no predicen el oro con parámetros estándar.
- El estudio del oro de Shanghái (*JIFMIM*, 2021–22): la predictibilidad es ilusoria tras controlar el *data snooping* y los costes.

**Conclusión:**
- La tendencia está respaldada en **diario y semanal**, con horizontes de semanas a meses.
- No hay evidencia a favor en H1 o H4, lo que coincide con nuestras rondas 1 y 2.
- Una candidata de tendencia debe **superar a «siempre comprado» escalado por volatilidad**, no solo a cero.

## 2. Estacionalidad intradía y por sesiones

- Blose y Gondhalekar (2014, *Applied Economics Letters*): en el futuro COMEX de 1985 a 2012 hay retorno nocturno positivo y diurno negativo. La asimetría **se debilitó con los años**.
- Blose, Gondhalekar y Kort (2018, *J. Economics & Finance*): la misma asimetría aparece en el fixing de Londres, en las mineras y en los ETF.
- Wei (2026, SSRN 7257240, sin revisión por pares): XAUUSD horario de jul-2024 a ago-2026.
  - Asia (00–08 UTC) explica +77 % del retorno logarítmico, Europa +36 % y EE. UU. −13 %.
  - Asia es positiva en todos los años.
  - **Muestra corta y en plena fase alcista.**
- Iwatsubo, Watkins y Xu (2018): en Tokio domina el flujo de liquidez y en Nueva York el flujo informado.
- Breedon y Ranaldo (2013, *JMCB*): las monedas se deprecian en su propio horario. Krohn, Mueller y Whelan (2024, *JF*): patrón intradía del USD alrededor de los fixings.

**Conclusión:**
- El patrón «largo en Asia» tiene décadas de apoyo descriptivo, pero es inestable y depende del régimen.
- Nadie lo ha probado en un CFD neto de spreads asiáticos, que son más anchos.
- Tiene sentido como **hipótesis confirmatoria de una sola configuración**, no como búsqueda entre cientos de ventanas.

## 3. Compresión y rupturas

- Fetna (2026, SSRN 7428398, preprint prerregistrado):
  - 9 futuros de EE. UU., metales incluidos, con datos de 1 minuto de 2010 a 2026 y 225 combinaciones de ruptura del rango de apertura.
  - **Ninguna sobrevive** a unos 25 USD de coste por contrato, es decir, unos 0.25 USD/oz: el coste del CFD minorista.
  - La mejor falla también frente a anclas aleatorias.
- Holmberg et al. (2013) y Sönnert (2015): rupturas rentables en crudo y en el futuro de oro en algunos periodos. Evidencia débil.
- Neely y Weller (2003) y Neely, Weller y Ulrich (2009): las reglas técnicas intradía en divisas desaparecen con costes realistas.
- El agrupamiento de volatilidad sí es robusto (Cai et al., 2001; Baur, 2012). Sirve para **dimensionar**, no para predecir la dirección.

**Conclusión:** prioridad baja. Si se prueba, necesita controles de **anclas aleatorias** y de ruptura **sin filtro de compresión**.

## 4. Reversión a la media de corto plazo (RSI(2))

- Connors y Alvarez (2008): documentada en índices de acciones, no en oro.
- En commodities predomina el momentum y la reversión no es significativa (estudio de Reading; Zhao et al.).
- **No hay evidencia revisada por pares de que funcione en oro.** Coincide con nuestro t = −5.1 en M15.

## 5. Régimen y macro

- Erb y Harvey (2013, *FAJ*): la relación con los tipos reales es probablemente espuria, y se rompió en 2022–24 con las compras de los bancos centrales.
- Baur, Dichtl, Drobetz y Wendt (2020, *IRFA*): más de 4 000 reglas de timing en oro no son robustas al *data snooping*.
- Harvey et al. (2018, *JPM*): el objetivo de volatilidad reduce las colas sin mejorar el Sharpe en commodities.

**Conclusión:** el condicionamiento por régimen es **exploratorio**. El control de volatilidad sirve para el riesgo, no como fuente de ventaja.

## 6. Costes del CFD XAUUSD minorista

Cifras de práctica y de agregadores **[sin verificar con HFM]**; se miden con `Scripts/KQ_AuditoriaEntorno.mq5`.

**Spread por momento del día:**

| Momento | Spread orientativo (USD/oz) |
|---|---|
| Solape Londres–Nueva York | 0.15–0.25 |
| Asia | 0.30–0.50 |
| Rollover (17:00 Nueva York = 00:00 del servidor) | 5–10 veces más ancho |
| Apertura del domingo, noticias (NFP) | 1–3 |

**Swap y cuentas:**
- Swap largo de referencia (otro bróker, 2026): unos −74 USD por lote y noche, alrededor de un **6 % anual**, con triple el miércoles.
- HFM ofrece cuentas **sin swap**, también la Cent. Podría haber un límite de días **[sin verificar]**.
- 0.01 lotes de la cuenta estándar = 1 oz. Hay que **verificar el tamaño del contrato en la cuenta Cent**.

**Reglas de coste comunes:**
- No entrar en el rollover.
- No entrar alrededor de datos de primer nivel.
- Usar spread variable real.

Sobre las noticias: el calendario económico de MQL5 no está disponible en el probador, así que ese filtro solo podría aplicarse en vivo.

## 7. Trampas del backtest

**Data snooping y sobreajuste:**
- White (2000); Hansen (2005, SPA).
- Bailey, Borwein, López de Prado y Zhu (PBO); *Deflated Sharpe Ratio*.
- Harvey, Liu y Zhu (2016), que proponen t > 3.
- McLean y Pontiff (2016): los retornos caen un 58 % tras la publicación.

**Datos y probador:**
- En MT5, los ticks generados desde barras de 1 minuto favorecen las entradas por ruptura (artículo MQL5 2612). Hay que usar «ticks reales» o, como hace nuestro motor, resolver dentro de la vela de forma **pesimista**.
- Un error en la hora del servidor o en el cambio de horario desplaza una hora las ventanas de sesión.
- El campo de spread de las velas puede ser el mínimo y no el medio. El script de auditoría lo compara con el spread de los ticks.
- El probador aplica el swap actual, no el histórico.

## Hipótesis priorizadas según la literatura

| # | Hipótesis | Evidencia | Uso en el protocolo v5 |
|---|---|---|---|
| 1 | Tendencia diaria o semanal, comparada con «siempre comprado» escalado por volatilidad | Fuerte en carteras, débil para un solo activo | H1 (D1). Necesita historial largo (escenario B) para tener potencia |
| 2 | Largo en la sesión asiática (00–08 UTC) | Moderada a débil, dependiente del régimen | **H3a confirmatoria** (1 configuración) |
| 3 | Expansión tras compresión | Débil. Negativa neta de costes en el mejor estudio | H2, con controles de anclas aleatorias |
| 4 | RSI(2) a favor de la tendencia | Sin evidencia en oro | H4, solo como control |

## Fuentes principales

- Moskowitz, Ooi y Pedersen (2012): https://w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf
- Hurst, Ooi y Pedersen (2017): https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing
- Lempérière et al. (2014): https://arxiv.org/abs/1404.3274
- Szakmary, Shen y Sharma (2010): https://www.sciencedirect.com/science/article/abs/pii/S037842660900199X
- Huang et al. (2020): https://www.sciencedirect.com/science/article/abs/pii/S0304405X19301953
- Kim, Tse y Wald (2016): https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2652637
- Kurth et al. (2026): https://arxiv.org/abs/2607.01550
- Batten et al. (2018): https://www.sciencedirect.com/science/article/abs/pii/S1042443117301087
- Blose y Gondhalekar (2014): https://www.tandfonline.com/doi/full/10.1080/13504851.2014.922661
- Blose, Gondhalekar y Kort (2018): https://link.springer.com/article/10.1007/s12197-017-9403-0
- Wei (2026): https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7257240
- Fetna (2026): https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7428398
- Neely y Weller (2003): https://www.sciencedirect.com/science/article/abs/pii/S0261560602001018
- Baur et al. (2020): https://www.sciencedirect.com/science/article/abs/pii/S1057521918306227
- Erb y Harvey (2013): https://www.nber.org/papers/w18706
- Artículo MQL5 2612 (generación de ticks): https://www.mql5.com/en/articles/2612
- Quantpedia, anomalías por usar precios OHLC: https://quantpedia.com/dangers-of-relying-on-ohlc-prices-the-case-of-overnight-drift-in-gdx-etf/
- HFM, cuenta Cent: https://www.hfm.com/int/en/trading-accounts/cent-account
- HFM, sin swap: https://www.hfm.com/int/en/funding/swap-free-trading
