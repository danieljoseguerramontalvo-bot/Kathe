# Instalación, datos y fase de demo (v5)

## 0. Regla de seguridad

- **Cuenta real:** KatheQuant v5 **nunca envía órdenes**. Muestra la señal (lotes, entrada, SL y TP), la notifica y sigue una «posición virtual» para avisarte de cuándo mover el SL o cerrar. Ejecutas tú a mano.
- **Cuenta demo:** solo opera si activas «Permitir ejecución automática en una cuenta DEMO».
- **Probador:** opera siempre.
- La **v4 (`EMA_Cross_DayTrade`) no tiene esta protección**. No la dejes en una cuenta real.

## 1. Instalar

Para cada archivo: en MetaEditor, **Archivo → Nuevo**, el nombre indicado, pegar el contenido y pulsar **F7**.

| Archivo | Tipo | Nombre en MetaEditor |
|---|---|---|
| `Experts/KatheQuant_v5.mq5` | Asesor experto | `KatheQuant_v5` |
| `Scripts/KQ_AuditoriaEntorno.mq5` | Script | `KQ_AuditoriaEntorno` |
| `Scripts/KQ_ExportarHistorial.mq5` | Script | `KQ_ExportarHistorial` |

- Tiene que salir **0 errores**. Si hay errores, manda una captura de la pestaña Errores. El código solo pasa por un verificador estático aproximado, así que MetaEditor es la prueba real.
- Presets: copia `Presets/v5/*.set` en `MQL5/Profiles/Tester` para el probador. Para un gráfico, usa el botón **Cargar** de la pestaña Parámetros.

## 2. Auditoría del entorno (5 minutos)

Hazlo en **cada cuenta**, la estándar y la Cent:
1. Arrastra `KQ_AuditoriaEntorno` a cualquier gráfico y pulsa **Aceptar**.
2. Los resultados quedan en **Archivo → Abrir carpeta de datos → MQL5 → Files**:
   - `KQ_auditoria_<cuenta>.txt`, el informe legible;
   - `KQ_<SÍMBOLO>_spec.json`, que lee el motor de investigación;
   - `KQ_<SÍMBOLO>_spread_por_hora.csv`.
3. Envía el `.txt`, o una captura de la pestaña Expertos.

## 3. Exportar el historial para la investigación

1. **Herramientas → Opciones → Gráficos → Máx. barras en ventana → «Unlimited»**, y reinicia MT5.
2. Arrastra `KQ_ExportarHistorial` a un gráfico:
   - en la cuenta estándar, símbolo `XAUUSD`;
   - en la cuenta Cent, `XAUUSDc`;
   - temporalidad M1.
3. Aparece `KQ_XAUUSD_M1.csv` en `MQL5/Files`. Son unos 60 MB. Haz clic derecho → **Comprimir en archivo ZIP**.
4. Súbelo al repositorio de GitHub:
   - abre la página del repositorio;
   - elige la rama `claude/mql5-ema-crossover-advisor-awun6l`;
   - pulsa **Add file → Upload files**, arrastra el ZIP y pulsa **Commit changes**.
   - El límite de la web es de 25 MB por archivo, y el ZIP suele pesar 15–20 MB. Si pesa más, exporta M5 en lugar de M1.

**Alternativa con más historial:** habilitar el dominio `datafeed.dukascopy.com` en la configuración de red del entorno de Claude. Da velas de 1 minuto BID/ASK desde 2003, y permite el escenario B del protocolo, con desarrollo y validación limpios.

## 4. Contraste entre el motor nuevo y el probador (v5 frente a v4)

1. En el probador:
   - `KatheQuant_v5`, `XAUUSD`, cualquier gráfico;
   - fechas 2022.01.01–2024.12.31, ticks reales, depósito 10 000, 1:100;
   - carga `KQ5_REF_T0_H4_vs_v4.set`.
2. Debe parecerse a la v4 con `R2_H4_T0_tendencia` (100 operaciones, PF 1.21, +1 370). Puede haber alguna operación más, porque la v5 corrige el rechazo «market closed» de la 01:00.
3. Envía las líneas `[RESULTADO]` del Diario.

## 4b. Montaje rápido en una cuenta demo (unos 10 minutos)

Sirve para comprobar la ejecución, los diarios y los límites **antes** de tener un candidato validado. No es una validación de la estrategia.

1. En HF Markets, abre una **cuenta demo**. En MT5: Archivo → Abrir una cuenta → HFMarkets → Demo.
2. Entra en MT5 con esa cuenta demo.
3. Compila `KatheQuant_v5` (apartado 1): tiene que salir 0 errores.
4. Pulsa el botón **Algo Trading** de la barra superior. Tiene que quedar en verde.
5. Abre un gráfico de `XAUUSD` y arrastra `KatheQuant_v5` sobre él.
   - En la pestaña **Común**, marca «Permitir Algo Trading».
   - En la pestaña **Parámetros**, pulsa **Cargar** y elige `KQ5_DEMO_listo_T0_H4.set`.
   - Pulsa **Aceptar**.
6. En la pestaña **Expertos** tiene que aparecer `[INICIO] ... AUTOMATICO en cuenta DEMO ... T0`. Si dice «SOLO SENALES», estás en la cuenta real.
7. El PC tiene que quedarse encendido. Si no, usa un VPS: en MT5, clic derecho en la cuenta → «Registrar un servidor virtual».

**No hace falta ninguna API key:** el EA opera a través del MT5 en el que has iniciado sesión.

## 5. Fase prospectiva en demo (solo con un candidato aprobado)

**Requisitos:**
- un candidato que cumpla el apartado 5 de `PROTOCOLO_V5.md`;
- parámetros **congelados**: se usa el `.set` exacto que pasó la validación, sin tocarlo.

**Montaje:**
1. Abre una **cuenta demo** en HF Markets, del mismo tipo que la real y con un balance parecido.
2. Gráfico del símbolo. La temporalidad del gráfico da igual: la estrategia usa la suya.
3. Arrastra `KatheQuant_v5`:
   - pestaña **Común**: «Permitir Algo Trading»;
   - pestaña **Parámetros**:
     - carga primero **`KQ5_DEMO_plantilla.set`**, que trae todas las protecciones activas;
     - después cambia **solo** la estrategia y sus parámetros a los del candidato congelado.
   - **No uses** los `.set` de investigación: tienen el drawdown máximo y la pérdida diaria desactivados. En demo automática el EA **se niega a arrancar** sin esos límites.
4. En Expertos, la línea `[INICIO]` tiene que decir `AUTOMATICO en cuenta DEMO` y mostrar la estrategia correcta.
5. Deja el PC encendido o usa un VPS.

**Registro automático.** Los diarios CSV van a la carpeta común (`%APPDATA%\MetaQuotes\Terminal\Common\Files`):
- `KQ5_<cuenta>_<símbolo>_<mágico>_senales.csv`: cada señal con su decisión (ejecutada, descartada y por qué), el precio esperado, el SL, el TP, los lotes, el riesgo y el spread;
- `KQ5_<cuenta>_<símbolo>_<mágico>_operaciones.csv`, con estos eventos:

  | Evento | Qué registra |
  |---|---|
  | `ENTRY` | El envío de la orden |
  | `FILL` | La ejecución real: precio pedido frente al ejecutado |
  | `MODIFY` | Cambios de SL o TP |
  | `EXIT` | El cierre: nivel de SL o TP frente al precio ejecutado |
  | `ERROR` | Errores temporales y reintentos |
  | `VIRTUAL_*` | Solo en modo señales |

  - Columnas: el deslizamiento en puntos (positivo = en contra), el spread, el resultado neto, la comisión, el swap y el múltiplo R.
  - En las filas `EXIT`, `dir` es la dirección del deal de cierre, que es la contraria a la posición.
  - En el probador, los diarios se llaman `KQ5T_…` y se reescriben en cada prueba. Al optimizar no se escriben.

**Revisión cada 2 semanas:** envía los dos CSV. Se comparan con el backtest del mismo periodo (mismas señales, deslizamiento y costes).

**Continuar, suspender o descartar**, con los criterios fijados en `PROTOCOLO_V5.md`, apartado 7:
- **Suspender** si:
  - el drawdown pasa del 10 %;
  - o, después de 30 operaciones, la esperanza en R está por debajo del percentil 10 del bootstrap;
  - o más del 5 % de las señales no se ejecutan.
- **Descartar** si:
  - el drawdown pasa del 15 %;
  - o, después de 30 operaciones, la esperanza en R está por debajo del percentil 5;
  - o más del 10 % de las señales no coinciden con el backtest.

## 6. Panel del gráfico

| Línea | Qué muestra |
|---|---|
| Modo | AUTOMÁTICO (probador o demo habilitada) o SOLO SEÑALES |
| Estrategia | Estrategia activa y temporalidad de la señal |
| Riesgo | Riesgo por operación, límites y drawdown actual |
| Hoy | Resultado del día del EA y bloqueos |
| Mercado | Régimen (ER diario, percentil del ATR), spread y sesión |
| Hora | Hora del servidor y hora UTC |
| Posición | Posición real o virtual, con SL y TP |
| Señales | Última señal, decisión y último motivo de espera o descarte |
