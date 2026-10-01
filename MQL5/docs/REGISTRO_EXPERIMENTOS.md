# Registro de todos los intentos (v4 y v5)

Aquí figuran todas las configuraciones que se han ejecutado **con datos reales**, incluidas las que salieron mal y las que quedaron fuera del protocolo.

- Sirve para contar cuántas pruebas se han hecho: el *Deflated Sharpe* las penaliza (`PROTOCOLO_V5.md`, enmienda 2, punto 4).
- Los registros automáticos de la v5 van en `research/registry/experiments.jsonl`, que solo admite añadidos y está encadenado por hashes. Los bloqueos de la reserva final van dentro del mismo archivo. Su cabecera, `experiments.jsonl.head`, y el historial de git impiden borrar las últimas líneas sin que se note.
- **Estado a 2026-09-29:** el registro está vacío, porque la v5 no ha tocado todavía ningún dato real.

## Fase v4 (probador de MT5 del usuario, XAUUSD HF Markets, riesgo 1 %)

| # | Configuración | Marco | Periodo | Oper. | PF | t | Resultado | Distinta | Fuente |
|---|---|---|---|---|---|---|---|---|---|
| 0 | Referencia +236 (RSI(2) + trailing + H1 + ADX), v3/v4 | M15 | 2025-09 → 2026-09 | 506 | 1.09 | 0.74 | +236.02 | = F7 | `PROTOCOLO.md` §5 |
| 1 | F7 con lote fijo 0.01 | M15 | 2022–2024 | 1 483 | 0.79 | −3.62 | pierde | = F7 | §5 |
| 2 | **F7** (la del +236) | M15 | 2022–2024 | 1 482 | 0.76 | −4.15 | −80 % | **1** | §5 |
| 3 | **F0** (RSI(2) sin filtros) | M15 | 2022–2024 | 1 905 | 0.72 | −5.13 | −92 % | **2** | §5 |
| 4 | **T0** (EMA 40/200 cruce + retroceso) | M15 | 2022–2024 | 989 | 0.75 | −3.90 | −77 % | **3** | §5 |
| 5 | **T1** (T0 + trailing, TP 6 ATR) | M15 | 2022–2024 | 1 024 | 0.67 | −4.43 | −81 % | **4** | §5 |
| 6 | **R2_H4_F0** | H4 | 2022–2024 | 230 | 0.96 | −0.25 | −3.1 % | **5** | §7 |
| 7 | **R2_H4_T0** (la que se puso en real) | H4 | 2022–2024 | 100 | 1.21 | 0.89 | +13.7 % | **6** | §7 |
| 8 | **R2_H4_T1** | H4 | 2022–2024 | 107 | 0.81 | −1.09 | −9.1 % | **7** | §7 |
| 9 | T0-H4 en XAUUSDc (cuenta Cent) | H4 | 2022–2024 | 62 | 0.76 | −1.04 | −9.3 % | = T0-H4 | §7.3 |
| 10 | **T0-H1** en XAUUSDc | H1 | 2022–2024 | 254 | 0.86 | – | −21.5 % | **8** | §7.3 |

- F1–F6 y S1–S3 no llegaron a ejecutarse (motivo en `PROTOCOLO.md` §6), así que no cuentan como pruebas.
- **Configuraciones distintas ejecutadas: 8.** Es el `PRIOR_TRIALS` de `research/kq/protocol.py`.
- **Datos contaminados por esta fase:**
  - 2022-01 → 2024-12 y 2025-09 → 2026-09, con símbolos XAUUSD y XAUUSDc;
  - el equipo también conoce la trayectoria general del precio del oro de 2022 a 2026.

## Fase v5 (prerregistrada)

| Fecha | Qué | Datos | Resultado |
|---|---|---|---|
| 2026-09-29 | Validación del ejecutor del protocolo | **Sintéticos** (paseo aleatorio y derivas plantadas) | Ver la enmienda 2, punto 16. No son pruebas de hipótesis sobre el oro y no cuentan como pruebas |
| (pendiente) | `kq.protocol devval`, escenario A o B | Exportación de MT5 o Dukascopy | – |
| (pendiente) | `kq.protocol holdout` (solo si hay candidatas) | Reserva final, una vez | – |
| (pendiente) | Demo prospectiva con los parámetros congelados | Cuenta demo | – |

Cada ejecución real de la v5 añade:
- una línea por familia en `experiments.jsonl`, con los hashes de los datos y del código (commit de git);
- una fila en esta tabla.
