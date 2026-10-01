//+------------------------------------------------------------------+
//|                                           EMA_Cross_DayTrade.mq5 |
//|  v4: tendencia EMA 40/200 o reversión RSI(2) - pensado para XAUUSD |
//+------------------------------------------------------------------+
#property copyright   "Kathe"
#property version     "4.00"
#property description "Dos estrategias independientes: tendencia EMA 40/200 (cruce o retroceso) y reversión RSI(2) (Connors)."
#property description "Lote calculado por riesgo con OrderCalcProfit; límites de exposición, pérdida diaria y drawdown."
#property description "Señales sobre velas cerradas, filtro del marco mayor sin datos futuros. Sin martingala ni grid."

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>

//--- Intentos de entrada por señal antes de descartarla (recotizaciones, precio cambiado, etc.)
#define MAX_ENTRY_ATTEMPTS 3
//--- Mínimo de operaciones para que OnTester devuelva una puntuación distinta de 0
#define MIN_TRADES_FOR_SCORE 30

//+------------------------------------------------------------------+
//| Tipos de los parámetros (mismos valores que la v3 para que los   |
//| archivos .set sean compatibles)                                  |
//+------------------------------------------------------------------+
enum ENUM_EA_ENTRY_MODE
{
   EA_ENTRY_CROSS_ONLY     = 0, // Tendencia: solo cruce EMA 40 / EMA 200 (pocas operaciones)
   EA_ENTRY_CROSS_PULLBACK = 1, // Tendencia: cruce + retrocesos a la EMA 40 (más operaciones)
   EA_ENTRY_RSI_REVERSION  = 2  // Reversión: RSI(2) extremo a favor de la EMA 200 (Connors)
};

enum ENUM_EA_DIRECTION
{
   EA_DIR_BOTH      = 0, // Compras y ventas
   EA_DIR_BUY_ONLY  = 1, // Solo compras
   EA_DIR_SELL_ONLY = 2  // Solo ventas
};

enum ENUM_EA_STOP_MODE
{
   EA_STOPS_PIPS = 0, // Pips fijos (Stop Loss y Take Profit en pips)
   EA_STOPS_ATR  = 1  // Según la volatilidad (ATR x multiplicador)
};

enum ENUM_EA_ACCOUNT_UNIT
{
   EA_UNIT_AUTO = 0, // Automático (según la divisa de la cuenta)
   EA_UNIT_USD  = 1, // Dólares (USD)
   EA_UNIT_USC  = 2  // Centavos de dólar (cuenta cent, USC)
};

//+------------------------------------------------------------------+
//| Parámetros de entrada                                            |
//| Los valores por defecto son la configuración de referencia del   |
//| informe de +236 USD. Es una HIPÓTESIS pendiente de validar.      |
//+------------------------------------------------------------------+
input group "=== Estrategia ==="
input ENUM_TIMEFRAMES    InpTimeframe       = PERIOD_CURRENT;         // Marco temporal de las señales
input int                InpFastPeriod      = 40;                     // Periodo EMA rápida (solo modos de tendencia)
input int                InpSlowPeriod      = 200;                    // Periodo EMA lenta (tendencia y reversión)
input ENUM_APPLIED_PRICE InpAppliedPrice    = PRICE_CLOSE;            // Precio aplicado a las EMAs
input ENUM_EA_ENTRY_MODE InpEntryMode       = EA_ENTRY_RSI_REVERSION; // Estrategia / tipo de entrada
input ENUM_EA_DIRECTION  InpDirection       = EA_DIR_BOTH;            // Dirección de las operaciones
input bool               InpCloseOnOpposite = true;                   // Cerrar la posición contraria cuando llega una señal opuesta

input group "=== Tamaño de la posición y riesgo ==="
input double               InpRiskPercent      = 1.0;          // Riesgo por operación en % del balance (0 = no usar)
input double               InpRiskMoneyUsd     = 0.0;          // Riesgo por operación en USD (si el % es 0; 0 = no usar)
input double               InpLots             = 0.01;         // Lote fijo (solo si el % y los USD son 0)
input ENUM_EA_ACCOUNT_UNIT InpAccountUnit      = EA_UNIT_AUTO; // Unidad de la cuenta (USD o USC)
input double               InpCommissionPerLot = 0.0;          // Comisión ida y vuelta por lote (divisa de la cuenta)

input group "=== Stop Loss y Take Profit ==="
input ENUM_EA_STOP_MODE InpStopMode        = EA_STOPS_ATR; // Tipo de Stop Loss / Take Profit
input double            InpStopLossPips    = 20.0;         // Stop Loss (pips, modo pips)
input double            InpTakeProfitPips  = 40.0;         // Take Profit (pips, modo pips)
input int               InpAtrPeriod       = 14;           // Periodo del ATR (stops y trailing)
input double            InpAtrSlMultiplier = 1.5;          // Stop Loss = ATR x este valor (modo ATR)
input double            InpAtrTpMultiplier = 6.0;          // Take Profit = ATR x este valor (modo ATR)
input double            InpPipSize         = 0.0;          // Valor de 1 pip en precio (0 = automático; oro = 0.1)

input group "=== Ejecución ==="
input double InpMaxSpreadPips   = 8.0;         // Spread máximo para entrar (pips, 0 = sin límite)
input int    InpSlippagePoints  = 30;          // Deslizamiento máximo (puntos)
input bool   InpOnePosition     = true;        // Solo una posición abierta a la vez (obligatorio en netting)
input int    InpMaxTradesPerDay = 10;          // Máximo de operaciones por día (0 = sin límite)
input int    InpCooldownBars    = 0;           // Velas de espera tras cerrar una posición (0 = sin espera)
input ulong  InpMagicNumber     = 4020040;     // Número mágico
input string InpTradeComment    = "EMA40x200"; // Comentario de las órdenes

input group "=== Filtro de tendencia del marco mayor ==="
input bool            InpUseHtfFilter = true;      // Operar solo a favor de la tendencia del marco mayor
input ENUM_TIMEFRAMES InpHtfTimeframe = PERIOD_H1; // Marco temporal mayor
input int             InpHtfPeriod    = 200;       // Periodo de la EMA del marco mayor

input group "=== Reversión RSI (solo en el modo Reversión) ==="
input int    InpRsiPeriod    = 2;    // Periodo del RSI
input double InpRsiBuyLevel  = 10.0; // Comprar cuando el RSI baja de este nivel
input double InpRsiSellLevel = 90.0; // Vender cuando el RSI sube de este nivel
input double InpRsiExitBuy   = 70.0; // Cerrar las compras cuando el RSI supera este nivel
input double InpRsiExitSell  = 30.0; // Cerrar las ventas cuando el RSI baja de este nivel

input group "=== Filtro de fuerza de tendencia (ADX) ==="
input int    InpAdxPeriod = 14;   // Periodo del ADX
input double InpAdxMin    = 20.0; // ADX mínimo para entrar (0 = sin filtro)

input group "=== Protección ==="
input double InpMaxDailyLossPercent = 5.0;   // Pérdida máxima diaria en % (0 = sin límite)
input double InpMaxDrawdownPercent  = 20.0;  // Drawdown máximo de la cuenta en % desde su máximo (0 = sin límite)
input bool   InpResetDrawdownLock   = false; // Reiniciar el bloqueo por drawdown al cargar el EA
input double InpMaxTotalLots        = 0.0;   // Lotes abiertos máximos de este EA (0 = sin límite)
input double InpMaxMarginUsePercent = 50.0;  // Margen máximo por operación en % del margen libre
input double InpBreakEvenPips       = 0.0;   // Mover el SL a la entrada tras X pips de ganancia (0 = desactivado)
input double InpBreakEvenLockPips   = 2.0;   // Pips de ganancia que se aseguran al mover a breakeven
input double InpTrailAtrMultiplier  = 2.0;   // Trailing stop a ATR x este valor del precio (0 = desactivado)

input group "=== Horario de operación (hora del servidor del bróker) ==="
input bool InpUseTimeFilter    = true;  // Activar filtro de horario
input int  InpStartHour        = 8;     // Hora de inicio (0-23)
input int  InpStartMinute      = 0;     // Minuto de inicio (0-59)
input int  InpEndHour          = 20;    // Hora de fin (0-23)
input int  InpEndMinute        = 0;     // Minuto de fin (0-59)
input bool InpUsePause         = false; // Pausa sin nuevas entradas (noticias de EE. UU.)
input int  InpPauseStartHour   = 15;    // Hora de inicio de la pausa (0-23)
input int  InpPauseStartMinute = 15;    // Minuto de inicio de la pausa (0-59)
input int  InpPauseEndHour     = 16;    // Hora de fin de la pausa (0-23)
input int  InpPauseEndMinute   = 0;     // Minuto de fin de la pausa (0-59)

input group "=== Días de operación ==="
input bool InpTradeMonday    = true;  // Operar el lunes
input bool InpTradeTuesday   = true;  // Operar el martes
input bool InpTradeWednesday = true;  // Operar el miércoles
input bool InpTradeThursday  = true;  // Operar el jueves
input bool InpTradeFriday    = true;  // Operar el viernes
input bool InpTradeSaturday  = false; // Operar el sábado
input bool InpTradeSunday    = false; // Operar el domingo

input group "=== Day trade (cierre intradía) ==="
input bool InpCloseEndOfDay = true; // Cerrar todas las posiciones al final del día
input int  InpCloseHour     = 22;   // Hora de cierre (0-23)
input int  InpCloseMinute   = 0;    // Minuto de cierre (0-59)

input group "=== Registro y visualización ==="
input bool   InpLogDiscards     = true; // Registrar las señales descartadas
input double InpStressExtraPips = 2.0;  // Coste extra por operación en la prueba de estrés (pips, solo informe)
input bool InpShowPanel   = true; // Mostrar panel informativo en el gráfico

//+------------------------------------------------------------------+
//| Variables globales                                               |
//+------------------------------------------------------------------+
CTrade          g_trade;
CPositionInfo   g_position;

int             g_fastHandle      = INVALID_HANDLE;
int             g_slowHandle      = INVALID_HANDLE;
int             g_atrHandle       = INVALID_HANDLE;
int             g_adxHandle       = INVALID_HANDLE; // solo con filtro ADX
int             g_htfHandle       = INVALID_HANDLE; // solo con filtro del marco mayor
int             g_rsiHandle       = INVALID_HANDLE; // solo en modo Reversión RSI
ENUM_TIMEFRAMES g_timeframe       = PERIOD_CURRENT;
ENUM_TIMEFRAMES g_htfTimeframe    = PERIOD_H1;
double          g_pip             = 0.0;
double          g_unitsPerUsd     = 1.0;   // 1 = USD, 100 = USC, 0 = otra divisa
bool            g_isNetting       = false;
bool            g_warmingUp       = false; // la EMA lenta aún no tiene historial suficiente

datetime        g_lastBarTime      = 0;  // última vela evaluada
datetime        g_signalBarTime    = 0;  // vela con una señal pendiente de ejecutar (0 = ninguna)
datetime        g_lastEntryBarTime = 0;  // vela en la que se abrió la última operación
int             g_signalDir        = 0;  // 1 = compra, -1 = venta
string          g_signalKind       = ""; // descripción de la señal pendiente
int             g_entryAttempts    = 0;
bool            g_waitWarned       = false;
string          g_lastSignalText   = "ninguna todavía";

datetime        g_lastPanelUpdate = 0;
datetime        g_lastLossCheck   = 0;
datetime        g_lossLimitDay    = 0;     // día en que se alcanzó el límite de pérdida
bool            g_ddLocked        = false; // bloqueo por drawdown activo
string          g_gvPeak          = "";    // variable global: máximo de la equidad
string          g_gvLock          = "";    // variable global: bloqueo por drawdown

//+------------------------------------------------------------------+
//| Utilidades de tiempo                                             |
//+------------------------------------------------------------------+
bool IsValidTime(const int hour, const int minute)
{
   return (hour >= 0 && hour <= 23 && minute >= 0 && minute <= 59);
}

int StartMinutes()
{
   return InpStartHour * 60 + InpStartMinute;
}

int EndMinutes()
{
   return InpEndHour * 60 + InpEndMinute;
}

int CloseMinutes()
{
   return InpCloseHour * 60 + InpCloseMinute;
}

int MinutesOfDay(const datetime t)
{
   MqlDateTime dt;
   TimeToStruct(t, dt);
   return dt.hour * 60 + dt.min;
}

datetime DayStart(const datetime t)
{
   MqlDateTime dt;
   TimeToStruct(t, dt);
   dt.hour = 0;
   dt.min  = 0;
   dt.sec  = 0;
   return StructToTime(dt);
}

string FormatHM(const int hour, const int minute)
{
   return StringFormat("%02d:%02d", hour, minute);
}

bool IsTradingDay(const datetime t)
{
   MqlDateTime dt;
   TimeToStruct(t, dt);
   if(dt.day_of_week == 0) return InpTradeSunday;
   if(dt.day_of_week == 1) return InpTradeMonday;
   if(dt.day_of_week == 2) return InpTradeTuesday;
   if(dt.day_of_week == 3) return InpTradeWednesday;
   if(dt.day_of_week == 4) return InpTradeThursday;
   if(dt.day_of_week == 5) return InpTradeFriday;
   return InpTradeSaturday;
}

//--- Si inicio == fin la franja es todo el día; si inicio > fin la franja cruza la medianoche
bool IsInWindow(const datetime t, const int start, const int end)
{
   int current = MinutesOfDay(t);
   if(start == end)
      return true;
   if(start < end)
      return (current >= start && current < end);
   return (current >= start || current < end);
}

bool IsInTradingWindow(const datetime t)
{
   if(!InpUseTimeFilter)
      return true;
   return IsInWindow(t, StartMinutes(), EndMinutes());
}

bool IsInPauseWindow(const datetime t)
{
   if(!InpUsePause)
      return false;
   int start = InpPauseStartHour * 60 + InpPauseStartMinute;
   int end   = InpPauseEndHour * 60 + InpPauseEndMinute;
   if(start == end)
      return false;
   return IsInWindow(t, start, end);
}

bool IsAfterDailyClose(const datetime t)
{
   if(!InpCloseEndOfDay)
      return false;
   return (MinutesOfDay(t) >= CloseMinutes());
}

//+------------------------------------------------------------------+
//| Utilidades de texto                                              |
//+------------------------------------------------------------------+
string DirName(const int dir)
{
   if(dir > 0)
      return "COMPRA";
   return "VENTA";
}

string EntryModeName()
{
   if(InpEntryMode == EA_ENTRY_CROSS_ONLY)
      return "Tendencia: solo cruces";
   if(InpEntryMode == EA_ENTRY_RSI_REVERSION)
      return "Reversión RSI(" + IntegerToString(InpRsiPeriod) + ")";
   return "Tendencia: cruces + retrocesos";
}

string TrendName(const int trend)
{
   if(trend > 0)
      return "ALCISTA";
   if(trend < 0)
      return "BAJISTA";
   return "sin datos";
}

string DirectionName()
{
   if(InpDirection == EA_DIR_BUY_ONLY)
      return "Solo compras";
   if(InpDirection == EA_DIR_SELL_ONLY)
      return "Solo ventas";
   return "Compras y ventas";
}

string YesNo(const bool value)
{
   if(value)
      return "Sí";
   return "No";
}

string TimeframeToString(const ENUM_TIMEFRAMES tf)
{
   return StringSubstr(EnumToString(tf), 7); // "PERIOD_M15" -> "M15"
}

string AccountUnitName()
{
   if(g_unitsPerUsd == 100.0)
      return "USC";
   if(g_unitsPerUsd == 1.0)
      return "USD";
   return AccountInfoString(ACCOUNT_CURRENCY);
}

string RiskModeText()
{
   if(InpRiskPercent > 0.0)
      return "Riesgo " + DoubleToString(InpRiskPercent, 2) + "% del balance";
   if(InpRiskMoneyUsd > 0.0)
      return "Riesgo " + DoubleToString(InpRiskMoneyUsd, 2) + " USD";
   return "Lote fijo " + DoubleToString(InpLots, 2) + " (riesgo no limitado por el EA)";
}

int InitError(const string message)
{
   Print("[ERROR] Parámetros incorrectos: ", message);
   return INIT_PARAMETERS_INCORRECT;
}

//+------------------------------------------------------------------+
//| Utilidades de precio, volumen y cuenta                           |
//+------------------------------------------------------------------+
//--- Oro: 1 pip = 0.1 | Plata: 0.01 | Divisas: 10 puntos con 3 y 5 decimales, 1 punto en el resto
double AutoPipSize()
{
   string name = _Symbol;
   StringToUpper(name);
   if(StringFind(name, "XAU") >= 0 || StringFind(name, "GOLD") >= 0)
      return 0.1;
   if(StringFind(name, "XAG") >= 0 || StringFind(name, "SILVER") >= 0)
      return 0.01;

   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   if(digits == 3 || digits == 5)
      return _Point * 10.0;
   return _Point;
}

//--- Unidades de la divisa de la cuenta por cada USD: 1 (USD), 100 (USC) o 0 (otra divisa)
double DetectUnitsPerUsd()
{
   if(InpAccountUnit == EA_UNIT_USD)
      return 1.0;
   if(InpAccountUnit == EA_UNIT_USC)
      return 100.0;
   string currency = AccountInfoString(ACCOUNT_CURRENCY);
   StringToUpper(currency);
   if(currency == "USD")
      return 1.0;
   if(currency == "USC")
      return 100.0;
   return 0.0;
}

double CurrentSpreadPips()
{
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick) || g_pip <= 0.0)
      return 0.0;
   return (tick.ask - tick.bid) / g_pip;
}

double NormalizePrice(const double price)
{
   double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tickSize > 0.0)
      return NormalizeDouble(MathRound(price / tickSize) * tickSize, _Digits);
   return NormalizeDouble(price, _Digits);
}

double MinStopDistance()
{
   return (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
}

double FreezeDistance()
{
   return (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL) * _Point;
}

//--- El bróker no permite modificar una posición cuyo SL o TP está dentro de la distancia de congelación
bool OutsideFreezeLevel(const int dir, const double sl, const double tp, const MqlTick &tick)
{
   double freeze = FreezeDistance();
   if(freeze <= 0.0)
      return true;
   double closePrice = tick.bid;
   if(dir < 0)
      closePrice = tick.ask;
   if(sl > 0.0 && MathAbs(closePrice - sl) <= freeze)
      return false;
   if(tp > 0.0 && MathAbs(tp - closePrice) <= freeze)
      return false;
   return true;
}

//--- Ajusta el lote al paso del símbolo redondeando hacia abajo; 0 si queda por debajo del mínimo
double NormalizeLots(const double lots)
{
   double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double step   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(step <= 0.0)
      return 0.0;

   double volume = MathFloor(lots / step + 0.0000001) * step;
   if(volume < minLot)
      return 0.0;
   if(maxLot > 0.0 && volume > maxLot)
      volume = maxLot;

   int volumeDigits = 0;
   if(step < 1.0)
      volumeDigits = (int)MathCeil(-MathLog10(step));
   return NormalizeDouble(volume, volumeDigits);
}

bool IsRetcodeSuccess(const uint retcode)
{
   return (retcode == TRADE_RETCODE_DONE ||
           retcode == TRADE_RETCODE_DONE_PARTIAL ||
           retcode == TRADE_RETCODE_PLACED);
}

//--- Tipo de llenado de órdenes admitido por el símbolo
void ConfigureFilling()
{
   long filling = SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
   if((filling & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK)
      g_trade.SetTypeFilling(ORDER_FILLING_FOK);
   else if((filling & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC)
      g_trade.SetTypeFilling(ORDER_FILLING_IOC);
   else
      g_trade.SetTypeFilling(ORDER_FILLING_RETURN);
}

//+------------------------------------------------------------------+
//| Indicadores (siempre sobre velas cerradas)                       |
//+------------------------------------------------------------------+
//--- ATR de la última vela cerrada; 0 si no hay datos
double CurrentAtr()
{
   double atr[];
   if(g_atrHandle == INVALID_HANDLE || BarsCalculated(g_atrHandle) <= InpAtrPeriod)
      return 0.0;
   if(CopyBuffer(g_atrHandle, 0, 1, 1, atr) != 1)
      return 0.0;
   return atr[0];
}

//--- Distancias de SL y TP en precio: pips fijos o ATR de la última vela cerrada
bool GetStopDistances(double &slDistance, double &tpDistance)
{
   slDistance = InpStopLossPips * g_pip;
   tpDistance = InpTakeProfitPips * g_pip;
   if(InpStopMode != EA_STOPS_ATR)
      return true;

   double atr = CurrentAtr();
   if(atr <= 0.0)
      return false;
   slDistance = atr * InpAtrSlMultiplier;
   tpDistance = atr * InpAtrTpMultiplier;
   return true;
}

//--- Tendencia del marco mayor con su última vela CERRADA: 1 alcista, -1 bajista, 0 igual.
//--- La EMA y el cierre se leen por la hora de apertura de esa vela, así ambos datos son de la
//--- misma vela y ya estaban disponibles en el momento de la señal. ready = false si faltan datos.
int HigherTimeframeTrend(bool &ready)
{
   ready = false;
   if(g_htfHandle == INVALID_HANDLE)
      return 0;
   if(Bars(_Symbol, g_htfTimeframe) < InpHtfPeriod * 2 || BarsCalculated(g_htfHandle) < InpHtfPeriod * 2)
      return 0;

   datetime closedBar = iTime(_Symbol, g_htfTimeframe, 1);
   if(closedBar == 0)
      return 0;

   double ema[];
   double closes[];
   if(CopyBuffer(g_htfHandle, 0, closedBar, 1, ema) != 1)
      return 0;
   if(CopyClose(_Symbol, g_htfTimeframe, closedBar, 1, closes) != 1)
      return 0;

   ready = true;
   if(closes[0] > ema[0])
      return 1;
   if(closes[0] < ema[0])
      return -1;
   return 0;
}

//--- ADX (línea principal) de la última vela cerrada. ready = false si faltan datos
double CurrentAdx(bool &ready)
{
   ready = false;
   if(g_adxHandle == INVALID_HANDLE || BarsCalculated(g_adxHandle) <= InpAdxPeriod * 2)
      return 0.0;
   double adx[];
   if(CopyBuffer(g_adxHandle, 0, 1, 1, adx) != 1)
      return 0.0;
   ready = true;
   return adx[0];
}

//+------------------------------------------------------------------+
//| Riesgo y tamaño de la posición                                   |
//+------------------------------------------------------------------+
//--- Dinero máximo a perder si se toca el SL (divisa de la cuenta); 0 = lote fijo
double RiskMoneyTarget()
{
   if(InpRiskPercent > 0.0)
      return AccountInfoDouble(ACCOUNT_BALANCE) * InpRiskPercent / 100.0;
   if(InpRiskMoneyUsd > 0.0 && g_unitsPerUsd > 0.0)
      return InpRiskMoneyUsd * g_unitsPerUsd;
   return 0.0;
}

//--- Pérdida de 1 lote entre la entrada y el SL (divisa de la cuenta, con comisión); -1 si no se puede calcular
double LossPerLotAtStop(const int dir, const double entry, const double sl)
{
   ENUM_ORDER_TYPE type = ORDER_TYPE_BUY;
   if(dir < 0)
      type = ORDER_TYPE_SELL;
   double profit = 0.0;
   if(!OrderCalcProfit(type, _Symbol, 1.0, entry, sl, profit))
      return -1.0;
   if(profit >= 0.0)
      return -1.0;
   return -profit + InpCommissionPerLot;
}

//--- Lote para la operación. Nunca redondea hacia arriba: si el lote mínimo arriesga más de lo
//--- permitido, devuelve 0 y la operación se omite
double CalculateLots(const int dir, const double entry, const double sl, double &riskOfTrade, string &reason)
{
   riskOfTrade = 0.0;
   double lossPerLot = LossPerLotAtStop(dir, entry, sl);
   if(lossPerLot <= 0.0)
   {
      reason = "no se pudo calcular la pérdida al stop (OrderCalcProfit)";
      return 0.0;
   }

   double riskMoney = RiskMoneyTarget();
   double lots      = 0.0;
   if(riskMoney <= 0.0)
   {
      lots = NormalizeLots(InpLots);
      if(lots <= 0.0)
      {
         reason = "el lote fijo " + DoubleToString(InpLots, 2) + " es menor que el mínimo del símbolo";
         return 0.0;
      }
   }
   else
   {
      lots = NormalizeLots(riskMoney / lossPerLot);
      if(lots <= 0.0)
      {
         double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
         reason = "el lote mínimo (" + DoubleToString(minLot, 2) + ") perdería " +
                  DoubleToString(lossPerLot * minLot, 2) + " " + AccountUnitName() +
                  " en el stop, más que el riesgo permitido (" + DoubleToString(riskMoney, 2) + ")";
         return 0.0;
      }
   }
   riskOfTrade = lossPerLot * lots;
   return lots;
}

//+------------------------------------------------------------------+
//| Posiciones y operaciones de este EA                              |
//+------------------------------------------------------------------+
bool IsOwnPosition()
{
   return (g_position.Symbol() == _Symbol && (ulong)g_position.Magic() == InpMagicNumber);
}

//--- Dirección de la posición seleccionada: 1 = compra, -1 = venta
int SelectedPositionDir()
{
   if(g_position.PositionType() == POSITION_TYPE_BUY)
      return 1;
   return -1;
}

//--- dirFilter: 0 = todas, 1 = compras, -1 = ventas
int CountOpenPositions(const int dirFilter)
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(!g_position.SelectByIndex(i) || !IsOwnPosition())
         continue;
      if(dirFilter == 0 || SelectedPositionDir() == dirFilter)
         count++;
   }
   return count;
}

double TotalOpenLots()
{
   double total = 0.0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(g_position.SelectByIndex(i) && IsOwnPosition())
         total += g_position.Volume();
   }
   return total;
}

//--- Ganancia o pérdida flotante de las posiciones abiertas del EA
double OpenProfit()
{
   double total = 0.0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(g_position.SelectByIndex(i) && IsOwnPosition())
         total += g_position.Profit() + g_position.Swap();
   }
   return total;
}

//--- dirFilter: 0 = todas, 1 = compras, -1 = ventas
void ClosePositions(const int dirFilter, const string why)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(!g_position.SelectByIndex(i) || !IsOwnPosition())
         continue;
      if(dirFilter != 0 && SelectedPositionDir() != dirFilter)
         continue;

      ulong ticket = g_position.Ticket();
      if(g_trade.PositionClose(ticket) && IsRetcodeSuccess(g_trade.ResultRetcode()))
         Print("[SALIDA] Posición #", ticket, " cerrada: ", why);
      else
         Print("[ERROR] No se pudo cerrar la posición #", ticket, " (", why, "). Código ",
               g_trade.ResultRetcode(), ": ", g_trade.ResultRetcodeDescription());
   }
}

//--- Day trade: cierra al llegar la hora de cierre y cualquier posición de un día anterior
void CloseDayTradePositions(const datetime now)
{
   bool     closeTimeReached = IsAfterDailyClose(now);
   datetime today            = DayStart(now);

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(!g_position.SelectByIndex(i) || !IsOwnPosition())
         continue;
      if(!closeTimeReached && g_position.Time() >= today)
         continue;

      ulong ticket = g_position.Ticket();
      if(g_trade.PositionClose(ticket) && IsRetcodeSuccess(g_trade.ResultRetcode()))
         Print("[SALIDA] Day trade: posición #", ticket, " cerrada (cierre intradía ",
               FormatHM(InpCloseHour, InpCloseMinute), ")");
      else
         Print("[ERROR] Day trade: no se pudo cerrar la posición #", ticket, ". Código ",
               g_trade.ResultRetcode(), ": ", g_trade.ResultRetcodeDescription());
   }
}

//--- Operaciones abiertas hoy y resultado cerrado de hoy (según el historial)
void GetTodayStats(const datetime now, int &trades, double &closedProfit)
{
   trades       = 0;
   closedProfit = 0.0;
   if(!HistorySelect(DayStart(now), (datetime)(now + 60)))
      return;

   int total = HistoryDealsTotal();
   for(int i = 0; i < total; i++)
   {
      ulong deal = HistoryDealGetTicket(i);
      if(deal == 0)
         continue;
      if(HistoryDealGetString(deal, DEAL_SYMBOL) != _Symbol)
         continue;
      if((ulong)HistoryDealGetInteger(deal, DEAL_MAGIC) != InpMagicNumber)
         continue;
      if(HistoryDealGetInteger(deal, DEAL_ENTRY) == DEAL_ENTRY_IN)
         trades++;
      closedProfit += HistoryDealGetDouble(deal, DEAL_PROFIT) +
                      HistoryDealGetDouble(deal, DEAL_SWAP) +
                      HistoryDealGetDouble(deal, DEAL_COMMISSION);
   }
}

//--- Hora del último cierre de una posición de este EA en los últimos 7 días (0 si no hay)
datetime LastExitTime(const datetime now)
{
   if(!HistorySelect((datetime)(now - 7 * 86400), (datetime)(now + 60)))
      return 0;

   datetime last  = 0;
   int      total = HistoryDealsTotal();
   for(int i = 0; i < total; i++)
   {
      ulong deal = HistoryDealGetTicket(i);
      if(deal == 0)
         continue;
      if(HistoryDealGetString(deal, DEAL_SYMBOL) != _Symbol)
         continue;
      if((ulong)HistoryDealGetInteger(deal, DEAL_MAGIC) != InpMagicNumber)
         continue;
      long entry = HistoryDealGetInteger(deal, DEAL_ENTRY);
      if(entry != DEAL_ENTRY_OUT && entry != DEAL_ENTRY_INOUT && entry != DEAL_ENTRY_OUT_BY)
         continue;
      datetime dealTime = (datetime)HistoryDealGetInteger(deal, DEAL_TIME);
      if(dealTime > last)
         last = dealTime;
   }
   return last;
}

//+------------------------------------------------------------------+
//| Protección                                                       |
//+------------------------------------------------------------------+
bool IsLossLimitReached(const datetime now)
{
   return (InpMaxDailyLossPercent > 0.0 && g_lossLimitDay == DayStart(now));
}

//--- Pérdida diaria (cerrado + flotante de este EA) frente al balance al inicio del día
void CheckDailyLoss(const datetime now)
{
   if(InpMaxDailyLossPercent <= 0.0)
      return;
   datetime today = DayStart(now);
   if(g_lossLimitDay == today)
      return;
   if(now - g_lastLossCheck < 10)
      return; // como máximo una comprobación cada 10 segundos
   g_lastLossCheck = now;

   int    trades       = 0;
   double closedProfit = 0.0;
   GetTodayStats(now, trades, closedProfit);
   double dayResult    = closedProfit + OpenProfit();
   double startBalance = AccountInfoDouble(ACCOUNT_BALANCE) - closedProfit;
   if(startBalance <= 0.0)
      return;

   double maxLoss = startBalance * InpMaxDailyLossPercent / 100.0;
   if(dayResult <= -maxLoss)
   {
      g_lossLimitDay = today;
      Print("[RIESGO] Límite de pérdida diaria alcanzado (", DoubleToString(dayResult, 2), " / máximo -",
            DoubleToString(maxLoss, 2), "). Se cierran las posiciones y no se opera más hoy");
      ClosePositions(0, "límite de pérdida diaria");
   }
}

//--- Drawdown de la cuenta desde el máximo de la equidad. El máximo y el bloqueo se guardan en
//--- variables globales del terminal para que sobrevivan a un reinicio
void InitDrawdownGuard()
{
   g_gvPeak = "EA4_" + _Symbol + "_" + IntegerToString((long)InpMagicNumber) + "_peak";
   g_gvLock = "EA4_" + _Symbol + "_" + IntegerToString((long)InpMagicNumber) + "_lock";

   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(InpResetDrawdownLock)
   {
      GlobalVariableDel(g_gvLock);
      GlobalVariableSet(g_gvPeak, equity);
      Print("[RIESGO] Bloqueo por drawdown reiniciado. Nuevo máximo de equidad: ", DoubleToString(equity, 2));
   }
   if(!GlobalVariableCheck(g_gvPeak))
      GlobalVariableSet(g_gvPeak, equity);

   g_ddLocked = GlobalVariableCheck(g_gvLock);
   if(g_ddLocked)
      Print("[RIESGO] El EA está bloqueado por drawdown. Para reanudar, cárguelo con 'Reiniciar el bloqueo por drawdown' = true");
}

void CheckDrawdown()
{
   if(InpMaxDrawdownPercent <= 0.0 || g_ddLocked)
      return;

   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double peak   = GlobalVariableGet(g_gvPeak);
   if(equity > peak)
   {
      GlobalVariableSet(g_gvPeak, equity);
      return;
   }
   if(peak <= 0.0)
      return;

   double drawdown = (peak - equity) / peak * 100.0;
   if(drawdown >= InpMaxDrawdownPercent)
   {
      g_ddLocked = true;
      GlobalVariableSet(g_gvLock, 1.0);
      Print("[RIESGO] Drawdown de la cuenta ", DoubleToString(drawdown, 2), "% >= ",
            DoubleToString(InpMaxDrawdownPercent, 2), "% (máximo ", DoubleToString(peak, 2),
            ", equidad ", DoubleToString(equity, 2), "). Se cierran las posiciones y se bloquean nuevas entradas");
      ClosePositions(0, "límite de drawdown");
   }
}

//--- Toda posición del EA debe tener SL. Si le falta, se añade; si no se puede, se cierra
void ProtectUnprotectedPositions()
{
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick))
      return;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(!g_position.SelectByIndex(i) || !IsOwnPosition())
         continue;
      if(g_position.StopLoss() > 0.0)
         continue;

      double slDistance = 0.0;
      double tpDistance = 0.0;
      if(!GetStopDistances(slDistance, tpDistance))
         continue; // sin ATR todavía: se intenta en el siguiente tick

      ulong  ticket    = g_position.Ticket();
      int    dir       = SelectedPositionDir();
      double openPrice = g_position.PriceOpen();
      double sl        = NormalizePrice(openPrice - slDistance);
      bool   valid     = (tick.bid - sl > MinStopDistance());
      if(dir < 0)
      {
         sl    = NormalizePrice(openPrice + slDistance);
         valid = (sl - tick.ask > MinStopDistance());
      }

      if(valid && g_trade.PositionModify(ticket, sl, g_position.TakeProfit()) &&
         IsRetcodeSuccess(g_trade.ResultRetcode()))
      {
         Print("[RIESGO] La posición #", ticket, " no tenía SL. Se añadió en ", DoubleToString(sl, _Digits));
         continue;
      }
      Print("[RIESGO] La posición #", ticket, " no tiene SL y no se pudo proteger: se cierra");
      if(!(g_trade.PositionClose(ticket) && IsRetcodeSuccess(g_trade.ResultRetcode())))
         Print("[ERROR] No se pudo cerrar la posición sin SL #", ticket, ". Código ",
               g_trade.ResultRetcode(), ": ", g_trade.ResultRetcodeDescription());
   }
}

//--- Breakeven: solo acerca el SL a favor de la operación, nunca lo aleja
void ManageBreakEven()
{
   if(InpBreakEvenPips <= 0.0)
      return;

   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick))
      return;
   double minDistance = MinStopDistance();

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(!g_position.SelectByIndex(i) || !IsOwnPosition())
         continue;

      int    dir       = SelectedPositionDir();
      double openPrice = g_position.PriceOpen();
      double currentSl = g_position.StopLoss();
      double tp        = g_position.TakeProfit();
      double newSl     = 0.0;
      bool   move      = false;

      if(dir > 0)
      {
         newSl = NormalizePrice(openPrice + InpBreakEvenLockPips * g_pip);
         move  = (tick.bid - openPrice >= InpBreakEvenPips * g_pip &&
                  (currentSl == 0.0 || currentSl < newSl - _Point * 0.5) &&
                  tick.bid - newSl > minDistance);
      }
      else
      {
         newSl = NormalizePrice(openPrice - InpBreakEvenLockPips * g_pip);
         move  = (openPrice - tick.ask >= InpBreakEvenPips * g_pip &&
                  (currentSl == 0.0 || currentSl > newSl + _Point * 0.5) &&
                  newSl - tick.ask > minDistance);
      }
      if(!move || !OutsideFreezeLevel(dir, currentSl, tp, tick))
         continue;

      ulong ticket = g_position.Ticket();
      if(g_trade.PositionModify(ticket, newSl, tp) && IsRetcodeSuccess(g_trade.ResultRetcode()))
         Print("[BREAKEVEN] SL de la posición #", ticket, " movido a ", DoubleToString(newSl, _Digits));
      else
         Print("[ERROR] Breakeven: no se pudo mover el SL de la posición #", ticket, ". Código ",
               g_trade.ResultRetcode(), ": ", g_trade.ResultRetcodeDescription());
   }
}

//--- Trailing stop: el SL sigue al precio a ATR x multiplicador. Solo se mueve a favor de la
//--- operación (nunca aumenta el riesgo) y en saltos de al menos max(1 pip, 0.1 ATR)
void ManageTrailing()
{
   if(InpTrailAtrMultiplier <= 0.0)
      return;
   double atr = CurrentAtr();
   if(atr <= 0.0)
      return;
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick))
      return;

   double distance    = atr * InpTrailAtrMultiplier;
   double step        = MathMax(g_pip, atr * 0.1);
   double minDistance = MinStopDistance();

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(!g_position.SelectByIndex(i) || !IsOwnPosition())
         continue;

      int    dir       = SelectedPositionDir();
      double currentSl = g_position.StopLoss();
      double tp        = g_position.TakeProfit();
      double newSl     = 0.0;
      bool   move      = false;
      if(dir > 0)
      {
         newSl = NormalizePrice(tick.bid - distance);
         move  = ((currentSl == 0.0 || newSl > currentSl + step) && tick.bid - newSl > minDistance);
      }
      else
      {
         newSl = NormalizePrice(tick.ask + distance);
         move  = ((currentSl == 0.0 || newSl < currentSl - step) && newSl - tick.ask > minDistance);
      }
      if(!move || !OutsideFreezeLevel(dir, currentSl, tp, tick))
         continue;

      ulong ticket = g_position.Ticket();
      if(g_trade.PositionModify(ticket, newSl, tp) && IsRetcodeSuccess(g_trade.ResultRetcode()))
         Print("[TRAILING] SL de la posición #", ticket, " movido a ", DoubleToString(newSl, _Digits));
      else
         Print("[ERROR] Trailing: no se pudo mover el SL de la posición #", ticket, ". Código ",
               g_trade.ResultRetcode(), ": ", g_trade.ResultRetcodeDescription());
   }
}

//--- Modo Reversión RSI: cerrar cuando el RSI de la vela cerrada vuelve a la zona contraria
void ManageRsiExits()
{
   if(InpEntryMode != EA_ENTRY_RSI_REVERSION || g_rsiHandle == INVALID_HANDLE)
      return;
   double rsi[];
   if(CopyBuffer(g_rsiHandle, 0, 1, 1, rsi) != 1)
      return;

   if(rsi[0] > InpRsiExitBuy && CountOpenPositions(1) > 0)
      ClosePositions(1, "salida por RSI (" + DoubleToString(rsi[0], 1) + " > " + DoubleToString(InpRsiExitBuy, 1) + ")");
   if(rsi[0] < InpRsiExitSell && CountOpenPositions(-1) > 0)
      ClosePositions(-1, "salida por RSI (" + DoubleToString(rsi[0], 1) + " < " + DoubleToString(InpRsiExitSell, 1) + ")");
}

//+------------------------------------------------------------------+
//| Permisos y filtros de entrada                                    |
//+------------------------------------------------------------------+
bool IsDirectionAllowed(const int dir)
{
   if(dir > 0)
      return (InpDirection != EA_DIR_SELL_ONLY);
   if(dir < 0)
      return (InpDirection != EA_DIR_BUY_ONLY);
   return false;
}

//--- Comprueba que el terminal, la cuenta y el símbolo permiten operar en esa dirección
bool IsTradingPermitted(const int dir, string &reason)
{
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
   {
      reason = "el trading algorítmico está desactivado en el terminal (botón Algo Trading)";
      return false;
   }
   if(!MQLInfoInteger(MQL_TRADE_ALLOWED))
   {
      reason = "el asesor no tiene permiso para operar (propiedades del EA > Permitir Algo Trading)";
      return false;
   }
   if(!AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) || !AccountInfoInteger(ACCOUNT_TRADE_EXPERT))
   {
      reason = "la cuenta no permite operar con asesores expertos";
      return false;
   }

   long mode = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_MODE);
   if(mode == SYMBOL_TRADE_MODE_FULL)
      return true;
   if(dir > 0 && mode == SYMBOL_TRADE_MODE_LONGONLY)
      return true;
   if(dir < 0 && mode == SYMBOL_TRADE_MODE_SHORTONLY)
      return true;
   reason = "el símbolo no admite nuevas operaciones en esa dirección en este momento";
   return false;
}

//--- Condiciones que descartan la señal
bool PassesHardFilters(const datetime now, const int dir, string &reason)
{
   if(g_lastEntryBarTime != 0 && g_lastEntryBarTime == g_signalBarTime)
   {
      reason = "ya se abrió una operación en esta vela";
      return false;
   }
   if(!IsTradingDay(now))
   {
      reason = "día no habilitado para operar";
      return false;
   }
   if(!IsInTradingWindow(now))
   {
      reason = "fuera del horario de operación (" + FormatHM(InpStartHour, InpStartMinute) +
               " - " + FormatHM(InpEndHour, InpEndMinute) + ")";
      return false;
   }
   if(IsAfterDailyClose(now))
   {
      reason = "ya pasó la hora de cierre intradía (" + FormatHM(InpCloseHour, InpCloseMinute) + ")";
      return false;
   }
   if(IsInPauseWindow(now))
   {
      reason = "pausa de noticias (" + FormatHM(InpPauseStartHour, InpPauseStartMinute) + " - " +
               FormatHM(InpPauseEndHour, InpPauseEndMinute) + ")";
      return false;
   }
   if(g_ddLocked)
   {
      reason = "bloqueado por el límite de drawdown";
      return false;
   }
   if(IsLossLimitReached(now))
   {
      reason = "se alcanzó el límite de pérdida diaria";
      return false;
   }
   if(!IsTradingPermitted(dir, reason))
      return false;
   if((InpOnePosition || g_isNetting) && CountOpenPositions(0) > 0)
   {
      reason = "ya hay una posición abierta";
      return false;
   }
   if(InpMaxTradesPerDay > 0)
   {
      int    trades       = 0;
      double closedProfit = 0.0;
      GetTodayStats(now, trades, closedProfit);
      if(trades >= InpMaxTradesPerDay)
      {
         reason = "se alcanzó el máximo de " + IntegerToString(InpMaxTradesPerDay) + " operaciones por día";
         return false;
      }
   }
   if(InpCooldownBars > 0)
   {
      datetime lastExit = LastExitTime(now);
      if(lastExit > 0 && now - lastExit < (long)InpCooldownBars * PeriodSeconds(g_timeframe))
      {
         reason = "espera de " + IntegerToString(InpCooldownBars) + " velas tras el último cierre";
         return false;
      }
   }
   return true;
}

//--- Condiciones de mercado: 1 = entrar, 0 = esperar dentro de la vela, -1 = descartar
int MarketConditions(const int dir, string &reason)
{
   if(InpUseHtfFilter)
   {
      bool ready = false;
      int  trend = HigherTimeframeTrend(ready);
      if(!ready)
      {
         reason = "datos del marco " + TimeframeToString(g_htfTimeframe) + " todavía no disponibles";
         return 0;
      }
      if(trend != dir)
      {
         reason = "va contra la tendencia de " + TimeframeToString(g_htfTimeframe) +
                  " (EMA " + IntegerToString(InpHtfPeriod) + "), que está " + TrendName(trend);
         return -1;
      }
   }
   if(InpAdxMin > 0.0)
   {
      bool   ready = false;
      double adx   = CurrentAdx(ready);
      if(!ready)
      {
         reason = "ADX todavía no disponible";
         return 0;
      }
      if(adx < InpAdxMin)
      {
         reason = "tendencia débil (ADX " + DoubleToString(adx, 1) + " < " + DoubleToString(InpAdxMin, 1) + ")";
         return -1;
      }
   }
   double spreadPips = CurrentSpreadPips();
   if(InpMaxSpreadPips > 0.0 && spreadPips > InpMaxSpreadPips)
   {
      reason = "spread demasiado alto (" + DoubleToString(spreadPips, 1) + " pips > " +
               DoubleToString(InpMaxSpreadPips, 1) + ")";
      return 0;
   }
   return 1;
}

//+------------------------------------------------------------------+
//| Abre la operación (1 = compra, -1 = venta)                       |
//| Devuelve 1 si abre, 0 si conviene reintentar, -1 si se descarta  |
//+------------------------------------------------------------------+
int OpenPosition(const int dir, string &reason)
{
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick) || tick.ask <= 0.0 || tick.bid <= 0.0)
   {
      reason = "no se pudo obtener el precio actual";
      return 0;
   }

   double slDistance = 0.0;
   double tpDistance = 0.0;
   if(!GetStopDistances(slDistance, tpDistance))
   {
      reason = "ATR todavía no disponible para el Stop Loss";
      return 0;
   }

   double price = tick.ask;
   double sl    = NormalizePrice(tick.ask - slDistance);
   double tp    = NormalizePrice(tick.ask + tpDistance);
   if(dir < 0)
   {
      price = tick.bid;
      sl    = NormalizePrice(tick.bid + slDistance);
      tp    = NormalizePrice(tick.bid - tpDistance);
   }

   //--- Los stops se miden contra el precio de cierre: Bid en compras, Ask en ventas
   double minDistance = MinStopDistance();
   bool   stopsOk     = true;
   if(dir > 0)
      stopsOk = (tick.bid - sl > minDistance && tp - tick.bid > minDistance);
   else
      stopsOk = (sl - tick.ask > minDistance && tick.ask - tp > minDistance);
   if(!stopsOk)
   {
      reason = "SL/TP dentro del spread o de la distancia mínima del bróker (SL a " +
               DoubleToString(slDistance, _Digits) + ")";
      return 0;
   }

   //--- Tamaño por riesgo: si el lote mínimo arriesga demasiado, no se opera
   double riskOfTrade = 0.0;
   double lots        = CalculateLots(dir, price, sl, riskOfTrade, reason);
   if(lots <= 0.0)
      return -1;

   if(InpMaxTotalLots > 0.0 && TotalOpenLots() + lots > InpMaxTotalLots + 0.0000001)
   {
      reason = "se superaría el máximo de " + DoubleToString(InpMaxTotalLots, 2) + " lotes abiertos";
      return -1;
   }

   //--- Margen: la operación no puede usar más del % permitido del margen libre
   ENUM_ORDER_TYPE orderType = ORDER_TYPE_BUY;
   if(dir < 0)
      orderType = ORDER_TYPE_SELL;
   double margin     = 0.0;
   double freeMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   if(!OrderCalcMargin(orderType, _Symbol, lots, price, margin))
   {
      reason = "no se pudo calcular el margen (OrderCalcMargin)";
      return 0;
   }
   if(margin > freeMargin * InpMaxMarginUsePercent / 100.0)
   {
      reason = "margen insuficiente: se necesitan " + DoubleToString(margin, 2) + " y el máximo permitido es " +
               DoubleToString(freeMargin * InpMaxMarginUsePercent / 100.0, 2);
      return -1;
   }

   bool sent = false;
   if(dir > 0)
      sent = g_trade.Buy(lots, _Symbol, price, sl, tp, InpTradeComment);
   else
      sent = g_trade.Sell(lots, _Symbol, price, sl, tp, InpTradeComment);

   if(!sent || !IsRetcodeSuccess(g_trade.ResultRetcode()))
   {
      reason = "error del servidor. Código " + IntegerToString((long)g_trade.ResultRetcode()) + ": " +
               g_trade.ResultRetcodeDescription();
      return 0;
   }

   Print("[ENTRADA] ", DirName(dir), " ", DoubleToString(lots, 2), " lotes a ",
         DoubleToString(g_trade.ResultPrice(), _Digits),
         " | SL ", DoubleToString(sl, _Digits), " | TP ", DoubleToString(tp, _Digits),
         " | Riesgo al SL ", DoubleToString(riskOfTrade, 2), " ", AccountUnitName(),
         " | Motivo: ", g_signalKind);
   return 1;
}

//+------------------------------------------------------------------+
//| Señales sobre velas cerradas                                     |
//| signal: 1 = compra, -1 = venta, 0 = nada                         |
//| Devuelve false si los datos del indicador aún no están listos    |
//+------------------------------------------------------------------+
bool GetSignal(int &signal, string &kind)
{
   signal = 0;
   kind   = "";

   if(BarsCalculated(g_fastHandle) <= InpFastPeriod || BarsCalculated(g_slowHandle) <= InpSlowPeriod)
      return false;

   //--- Calentamiento: la EMA lenta necesita historial suficiente para dar valores fiables
   g_warmingUp = (Bars(_Symbol, g_timeframe) < InpSlowPeriod * 3);
   if(g_warmingUp)
      return true;

   //--- Orden cronológico: [0] = vela 2 (anterior), [1] = vela 1 (última cerrada)
   double fast[];
   double slow[];
   double closes[];
   if(CopyBuffer(g_fastHandle, 0, 1, 2, fast) != 2)
      return false;
   if(CopyBuffer(g_slowHandle, 0, 1, 2, slow) != 2)
      return false;
   if(CopyClose(_Symbol, g_timeframe, 1, 2, closes) != 2)
      return false;

   string emas = "EMA " + IntegerToString(InpFastPeriod) + "/" + IntegerToString(InpSlowPeriod);

   //--- Estrategia B, Reversión (Connors): RSI extremo en la dirección que marca la EMA lenta.
   //--- En este modo la EMA rápida no interviene
   if(InpEntryMode == EA_ENTRY_RSI_REVERSION)
   {
      if(BarsCalculated(g_rsiHandle) <= InpRsiPeriod)
         return false;
      double rsi[];
      if(CopyBuffer(g_rsiHandle, 0, 1, 1, rsi) != 1)
         return false;
      string rsiText = "RSI(" + IntegerToString(InpRsiPeriod) + ") = " + DoubleToString(rsi[0], 1);
      if(closes[1] > slow[1] && rsi[0] < InpRsiBuyLevel)
      {
         signal = 1;
         kind   = rsiText + " sobrevendido con el precio sobre la EMA " + IntegerToString(InpSlowPeriod);
      }
      else if(closes[1] < slow[1] && rsi[0] > InpRsiSellLevel)
      {
         signal = -1;
         kind   = rsiText + " sobrecomprado con el precio bajo la EMA " + IntegerToString(InpSlowPeriod);
      }
      return true;
   }

   //--- Estrategia A, Tendencia. 1) Cruce de las medias
   if(fast[0] <= slow[0] && fast[1] > slow[1])
   {
      signal = 1;
      kind   = "cruce alcista " + emas;
      return true;
   }
   if(fast[0] >= slow[0] && fast[1] < slow[1])
   {
      signal = -1;
      kind   = "cruce bajista " + emas;
      return true;
   }

   //--- 2) Retroceso a favor de la tendencia: el precio vuelve a cerrar al otro lado de la EMA rápida
   if(InpEntryMode == EA_ENTRY_CROSS_PULLBACK)
   {
      if(fast[1] > slow[1] && closes[0] <= fast[0] && closes[1] > fast[1])
      {
         signal = 1;
         kind   = "retroceso alcista (cierre de nuevo sobre la EMA " + IntegerToString(InpFastPeriod) + ")";
      }
      else if(fast[1] < slow[1] && closes[0] >= fast[0] && closes[1] < fast[1])
      {
         signal = -1;
         kind   = "retroceso bajista (cierre de nuevo bajo la EMA " + IntegerToString(InpFastPeriod) + ")";
      }
   }
   return true;
}

void ClearSignal()
{
   g_signalBarTime = 0;
   g_signalDir     = 0;
   g_signalKind    = "";
}

void DiscardSignal(const string reason)
{
   if(InpLogDiscards)
      Print("[DESCARTE] Señal de ", DirName(g_signalDir), ": ", reason);
   ClearSignal();
}

//+------------------------------------------------------------------+
//| Intenta abrir la operación de la señal pendiente                 |
//+------------------------------------------------------------------+
void TryEnter(const datetime now)
{
   string reason = "";
   if(!PassesHardFilters(now, g_signalDir, reason))
   {
      DiscardSignal(reason);
      return;
   }

   int market = MarketConditions(g_signalDir, reason);
   if(market < 0)
   {
      DiscardSignal(reason);
      return;
   }
   if(market == 0)
   {
      if(!g_waitWarned)
      {
         Print("[ESPERA] Señal de ", DirName(g_signalDir), ": ", reason, ". Se esperará dentro de la vela actual");
         g_waitWarned = true;
      }
      return;
   }

   int result = OpenPosition(g_signalDir, reason);
   if(result > 0)
   {
      g_lastEntryBarTime = g_signalBarTime;
      ClearSignal();
      return;
   }
   if(result < 0)
   {
      DiscardSignal(reason);
      return;
   }

   g_entryAttempts++;
   Print("[ERROR] Intento ", g_entryAttempts, " de ", MAX_ENTRY_ATTEMPTS, " fallido: ", reason);
   if(g_entryAttempts >= MAX_ENTRY_ATTEMPTS)
      DiscardSignal("tras " + IntegerToString(MAX_ENTRY_ATTEMPTS) + " intentos fallidos");
}

//+------------------------------------------------------------------+
//| Panel informativo en el gráfico                                  |
//+------------------------------------------------------------------+
void UpdatePanel(const datetime now)
{
   if(now == g_lastPanelUpdate)
      return; // como máximo una actualización por segundo
   g_lastPanelUpdate = now;

   if(MQLInfoInteger(MQL_TESTER) && !MQLInfoInteger(MQL_VISUAL_MODE))
      return;

   string trendLine = "EMAs: calculando...";
   if(g_warmingUp)
      trendLine = "Calentando indicadores (faltan velas de historial)";
   else
   {
      double fast[];
      double slow[];
      if(CopyBuffer(g_fastHandle, 0, 1, 1, fast) == 1 && CopyBuffer(g_slowHandle, 0, 1, 1, slow) == 1)
      {
         string trend = "BAJISTA";
         if(fast[0] > slow[0])
            trend = "ALCISTA";
         trendLine = "EMA " + IntegerToString(InpFastPeriod) + ": " + DoubleToString(fast[0], _Digits) +
                     " | EMA " + IntegerToString(InpSlowPeriod) + ": " + DoubleToString(slow[0], _Digits) +
                     " | EMA rápida vs lenta: " + trend;
      }
   }

   double slDistance = 0.0;
   double tpDistance = 0.0;
   bool   stopsReady = GetStopDistances(slDistance, tpDistance);
   string stopsText  = "SL " + DoubleToString(slDistance, _Digits) + " | TP " + DoubleToString(tpDistance, _Digits);
   if(InpStopMode == EA_STOPS_ATR)
   {
      stopsText = "SL ATR x" + DoubleToString(InpAtrSlMultiplier, 1) + " | TP ATR x" + DoubleToString(InpAtrTpMultiplier, 1);
      if(stopsReady)
         stopsText += " (ahora " + DoubleToString(slDistance, _Digits) + " / " + DoubleToString(tpDistance, _Digits) + ")";
   }

   string filterText = "Filtro " + TimeframeToString(g_htfTimeframe) + ": no";
   if(InpUseHtfFilter)
   {
      bool ready = false;
      int  trend = HigherTimeframeTrend(ready);
      filterText = "Filtro " + TimeframeToString(g_htfTimeframe) + ": " + TrendName(trend);
   }
   string adxText = "ADX: sin filtro";
   if(InpAdxMin > 0.0)
   {
      bool   ready = false;
      double adx   = CurrentAdx(ready);
      adxText = "ADX " + DoubleToString(adx, 1) + " (mínimo " + DoubleToString(InpAdxMin, 1) + ")";
   }
   string trailText = "Trailing: no";
   if(InpTrailAtrMultiplier > 0.0)
      trailText = "Trailing: ATR x" + DoubleToString(InpTrailAtrMultiplier, 1);

   int    trades       = 0;
   double closedProfit = 0.0;
   GetTodayStats(now, trades, closedProfit);
   double dayResult = closedProfit + OpenProfit();

   string text = "Robot v4 - " + EntryModeName() + " - " + _Symbol + " " + TimeframeToString(g_timeframe) + "\n";
   text += RiskModeText() + " | Cuenta en " + AccountUnitName() + " | " + stopsText + "\n";
   text += trendLine + "\n";
   text += filterText + " | " + adxText + " | " + trailText + " | " + DirectionName() + "\n";
   text += "Hora servidor: " + TimeToString(now, TIME_MINUTES) +
           " | Hora PC: " + TimeToString(TimeLocal(), TIME_MINUTES) +
           " | Día habilitado: " + YesNo(IsTradingDay(now)) +
           " | En horario: " + YesNo(IsInTradingWindow(now)) + "\n";
   text += "Posiciones: " + IntegerToString(CountOpenPositions(1)) + " compras / " +
           IntegerToString(CountOpenPositions(-1)) + " ventas" +
           " | Operaciones hoy: " + IntegerToString(trades) +
           " | Resultado hoy: " + DoubleToString(dayResult, 2) +
           " | Spread: " + DoubleToString(CurrentSpreadPips(), 1) + " pips\n";
   text += "Última señal: " + g_lastSignalText;
   if(IsLossLimitReached(now))
      text += "\n*** LÍMITE DE PÉRDIDA DIARIA ALCANZADO: sin operar hasta mañana ***";
   if(g_ddLocked)
      text += "\n*** BLOQUEADO POR DRAWDOWN: ver el registro de Expertos ***";
   Comment(text);
}

//+------------------------------------------------------------------+
//| Informe al final de cada prueba (se ve en el Diario del probador)|
//| Agrupa los deals por posición para obtener el resultado neto de  |
//| cada operación y calcula la estadística del protocolo            |
//+------------------------------------------------------------------+
void PrintTradeStatistics()
{
   if(!HistorySelect(0, (datetime)(TimeCurrent() + 86400)))
      return;

   long     ids[];
   double   netResult[];
   double   volumes[];
   datetime exitTimes[];

   int total = HistoryDealsTotal();
   for(int i = 0; i < total; i++)
   {
      ulong deal = HistoryDealGetTicket(i);
      if(deal == 0)
         continue;
      if(HistoryDealGetString(deal, DEAL_SYMBOL) != _Symbol)
         continue;
      if((ulong)HistoryDealGetInteger(deal, DEAL_MAGIC) != InpMagicNumber)
         continue;

      long positionId = HistoryDealGetInteger(deal, DEAL_POSITION_ID);
      int  slot       = -1;
      for(int j = ArraySize(ids) - 1; j >= 0; j--)
      {
         if(ids[j] == positionId)
         {
            slot = j;
            break;
         }
      }
      if(slot < 0)
      {
         slot = ArraySize(ids);
         ArrayResize(ids, slot + 1);
         ArrayResize(netResult, slot + 1);
         ArrayResize(volumes, slot + 1);
         ArrayResize(exitTimes, slot + 1);
         ids[slot]       = positionId;
         netResult[slot] = 0.0;
         volumes[slot]   = 0.0;
         exitTimes[slot] = 0;
      }

      netResult[slot] += HistoryDealGetDouble(deal, DEAL_PROFIT) +
                         HistoryDealGetDouble(deal, DEAL_SWAP) +
                         HistoryDealGetDouble(deal, DEAL_COMMISSION);
      if(HistoryDealGetInteger(deal, DEAL_ENTRY) == DEAL_ENTRY_IN)
         volumes[slot] += HistoryDealGetDouble(deal, DEAL_VOLUME);
      else
         exitTimes[slot] = (datetime)HistoryDealGetInteger(deal, DEAL_TIME);
   }

   //--- Estadística por operación cerrada
   int    n          = 0;
   double sum        = 0.0;
   double best       = 0.0;
   double stressCost = 0.0;
   double contract   = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   int    years[];
   double yearResults[];
   int    yearCounts[];

   for(int j = 0; j < ArraySize(ids); j++)
   {
      if(exitTimes[j] == 0)
         continue;
      n++;
      sum += netResult[j];
      if(netResult[j] > best)
         best = netResult[j];
      //--- Coste extra supuesto: InpStressExtraPips de precio por operación (divisa de cotización en USD)
      stressCost += InpStressExtraPips * g_pip * contract * volumes[j] * g_unitsPerUsd;

      MqlDateTime dt;
      TimeToStruct(exitTimes[j], dt);
      int ySlot = -1;
      for(int k = 0; k < ArraySize(years); k++)
      {
         if(years[k] == dt.year)
         {
            ySlot = k;
            break;
         }
      }
      if(ySlot < 0)
      {
         ySlot = ArraySize(years);
         ArrayResize(years, ySlot + 1);
         ArrayResize(yearResults, ySlot + 1);
         ArrayResize(yearCounts, ySlot + 1);
         years[ySlot]       = dt.year;
         yearResults[ySlot] = 0.0;
         yearCounts[ySlot]  = 0;
      }
      yearResults[ySlot] += netResult[j];
      yearCounts[ySlot]++;
   }
   if(n < 2)
   {
      Print("[RESULTADO] Menos de 2 operaciones cerradas: sin estadística");
      return;
   }

   double mean     = sum / n;
   double variance = 0.0;
   for(int j = 0; j < ArraySize(ids); j++)
   {
      if(exitTimes[j] == 0)
         continue;
      variance += (netResult[j] - mean) * (netResult[j] - mean);
   }
   double sd         = MathSqrt(variance / (n - 1));
   double tStat      = 0.0;
   if(sd > 0.0)
      tStat = mean / (sd / MathSqrt((double)n));
   double stressMean = mean - stressCost / n;

   Print("[RESULTADO] Por operación: n = ", n, " | media ", DoubleToString(mean, 2),
         " | desviación ", DoubleToString(sd, 2), " | t = ", DoubleToString(tStat, 2),
         " | media con estrés de +", DoubleToString(InpStressExtraPips, 1), " pips: ", DoubleToString(stressMean, 2));

   string text = "[RESULTADO] Por año:";
   for(int k = 0; k < ArraySize(years); k++)
      text += " " + IntegerToString(years[k]) + ": " + DoubleToString(yearResults[k], 2) +
              " (" + IntegerToString(yearCounts[k]) + " op.)";
   Print(text);
   if(sum > 0.0)
      Print("[RESULTADO] Mayor operación ganadora: ", DoubleToString(best, 2), " = ",
            DoubleToString(best / sum * 100.0, 1), "% del beneficio neto");
}

double OnTester()
{
   double trades   = TesterStatistics(STAT_TRADES);
   double wins     = TesterStatistics(STAT_PROFIT_TRADES);
   double profit   = TesterStatistics(STAT_PROFIT);
   double pf       = TesterStatistics(STAT_PROFIT_FACTOR);
   double expected = TesterStatistics(STAT_EXPECTED_PAYOFF);
   double recovery = TesterStatistics(STAT_RECOVERY_FACTOR);
   double ddEqPct  = TesterStatistics(STAT_EQUITY_DDREL_PERCENT);
   double ddEq     = TesterStatistics(STAT_EQUITY_DD);
   double ddBalPct = TesterStatistics(STAT_BALANCE_DDREL_PERCENT);
   double ddBal    = TesterStatistics(STAT_BALANCE_DD);

   double winRate = 0.0;
   if(trades > 0.0)
      winRate = wins / trades * 100.0;

   Print("[RESULTADO] ", EntryModeName(), " | Operaciones ", DoubleToString(trades, 0),
         " | Acierto ", DoubleToString(winRate, 1), "%",
         " | Beneficio neto ", DoubleToString(profit, 2),
         " | Factor de beneficio ", DoubleToString(pf, 2),
         " | Esperanza ", DoubleToString(expected, 2),
         " | Factor de recuperación ", DoubleToString(recovery, 2));
   Print("[RESULTADO] Drawdown de equidad ", DoubleToString(ddEq, 2), " (", DoubleToString(ddEqPct, 2), "%)",
         " | Drawdown de balance ", DoubleToString(ddBal, 2), " (", DoubleToString(ddBalPct, 2), "%)");
   PrintTradeStatistics();

   //--- Criterio personalizado para el optimizador: factor de recuperación, 0 si hay pocas operaciones
   if(trades < MIN_TRADES_FOR_SCORE)
      return 0.0;
   return recovery;
}

//+------------------------------------------------------------------+
//| Inicialización                                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   //--- Validación de parámetros
   if(InpFastPeriod < 1 || InpSlowPeriod < 1 || InpFastPeriod >= InpSlowPeriod)
      return InitError("el periodo de la EMA rápida debe ser menor que el de la EMA lenta");
   if(InpRiskPercent < 0.0 || InpRiskPercent > 10.0)
      return InitError("el riesgo por operación debe estar entre 0 y 10 %");
   if(InpRiskMoneyUsd < 0.0 || InpLots < 0.0 || InpCommissionPerLot < 0.0)
      return InitError("el riesgo en USD, el lote y la comisión no pueden ser negativos");
   if(InpRiskPercent <= 0.0 && InpRiskMoneyUsd <= 0.0 && InpLots <= 0.0)
      return InitError("indique un riesgo en %, un riesgo en USD o un lote fijo");
   if(InpStopLossPips <= 0.0 || InpTakeProfitPips <= 0.0)
      return InitError("el stop loss y el take profit en pips deben ser mayores que 0");
   if(InpAtrPeriod < 1 || InpTrailAtrMultiplier < 0.0)
      return InitError("el periodo del ATR debe ser mayor que 0 y el trailing no puede ser negativo");
   if(InpStopMode == EA_STOPS_ATR && (InpAtrSlMultiplier <= 0.0 || InpAtrTpMultiplier <= 0.0))
      return InitError("en modo ATR, los multiplicadores del SL y del TP deben ser mayores que 0");
   if(InpPipSize < 0.0 || InpMaxSpreadPips < 0.0 || InpSlippagePoints < 0 || InpMaxTradesPerDay < 0 || InpCooldownBars < 0)
      return InitError("pip, spread, deslizamiento, máximo diario y espera no pueden ser negativos");
   if(InpHtfPeriod < 1)
      return InitError("el periodo de la EMA del marco mayor debe ser mayor que 0");
   if(InpRsiPeriod < 1 || InpRsiBuyLevel <= 0.0 || InpRsiSellLevel >= 100.0 || InpRsiBuyLevel >= InpRsiSellLevel)
      return InitError("RSI: el periodo debe ser mayor que 0 y el nivel de compra menor que el de venta (entre 0 y 100)");
   if(InpAdxPeriod < 1 || InpAdxMin < 0.0 || InpAdxMin > 100.0)
      return InitError("el periodo del ADX debe ser mayor que 0 y el ADX mínimo estar entre 0 y 100");
   if(InpMaxDailyLossPercent < 0.0 || InpMaxDrawdownPercent < 0.0 || InpMaxDrawdownPercent > 100.0)
      return InitError("la pérdida diaria y el drawdown máximo deben estar entre 0 y 100 %");
   if(InpMaxTotalLots < 0.0 || InpMaxMarginUsePercent <= 0.0 || InpMaxMarginUsePercent > 100.0)
      return InitError("lotes máximos no negativos y margen máximo entre 0 y 100 %");
   if(InpBreakEvenPips < 0.0 || InpBreakEvenLockPips < 0.0)
      return InitError("el breakeven no puede ser negativo");
   if(InpBreakEvenPips > 0.0 && InpBreakEvenLockPips >= InpBreakEvenPips)
      return InitError("los pips asegurados deben ser menores que los pips para activar el breakeven");
   if(!IsValidTime(InpStartHour, InpStartMinute) || !IsValidTime(InpEndHour, InpEndMinute))
      return InitError("horario de operación inválido (horas 0-23, minutos 0-59)");
   if(!IsValidTime(InpPauseStartHour, InpPauseStartMinute) || !IsValidTime(InpPauseEndHour, InpPauseEndMinute))
      return InitError("horario de la pausa inválido (horas 0-23, minutos 0-59)");
   if(!IsValidTime(InpCloseHour, InpCloseMinute))
      return InitError("hora de cierre intradía inválida (horas 0-23, minutos 0-59)");
   if(InpCloseEndOfDay && CloseMinutes() == 0)
      return InitError("la hora de cierre intradía no puede ser 00:00 (use, por ejemplo, 23:55)");

   g_timeframe = InpTimeframe;
   if(g_timeframe == PERIOD_CURRENT)
      g_timeframe = (ENUM_TIMEFRAMES)Period();
   g_htfTimeframe = InpHtfTimeframe;
   if(g_htfTimeframe == PERIOD_CURRENT)
      g_htfTimeframe = (ENUM_TIMEFRAMES)Period();

   //--- Tamaño del pip
   g_pip = InpPipSize;
   if(g_pip <= 0.0)
      g_pip = AutoPipSize();
   if(g_pip <= 0.0)
      return InitError("no se pudo determinar el tamaño del pip; indíquelo manualmente");

   //--- Divisa de la cuenta (USD o USC)
   g_unitsPerUsd = DetectUnitsPerUsd();
   if(InpRiskPercent <= 0.0 && InpRiskMoneyUsd > 0.0 && g_unitsPerUsd <= 0.0)
      return InitError("la cuenta está en " + AccountInfoString(ACCOUNT_CURRENCY) +
                       ": use el riesgo en % o indique la unidad de la cuenta");

   //--- Tipo de cuenta: en netting solo puede haber una posición por símbolo
   long marginMode = AccountInfoInteger(ACCOUNT_MARGIN_MODE);
   g_isNetting = (marginMode != ACCOUNT_MARGIN_MODE_RETAIL_HEDGING);
   if(g_isNetting && !InpOnePosition)
      Print("[INICIO] Cuenta netting: se opera con una sola posición aunque 'Solo una posición' sea false");

   //--- Lote fijo válido para el símbolo
   if(InpRiskPercent <= 0.0 && InpRiskMoneyUsd <= 0.0)
   {
      double lots = NormalizeLots(InpLots);
      if(lots <= 0.0)
         return InitError("el lote " + DoubleToString(InpLots, 2) + " es menor que el mínimo del símbolo (" +
                          DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN), 2) + ")");
      if(MathAbs(lots - InpLots) > 0.00000001)
         Print("[INICIO] Aviso: el lote ", DoubleToString(InpLots, 2), " se ajustará a ", DoubleToString(lots, 2),
               " según las reglas del símbolo");
   }

   //--- Indicadores
   g_fastHandle = iMA(_Symbol, g_timeframe, InpFastPeriod, 0, MODE_EMA, InpAppliedPrice);
   g_slowHandle = iMA(_Symbol, g_timeframe, InpSlowPeriod, 0, MODE_EMA, InpAppliedPrice);
   g_atrHandle  = iATR(_Symbol, g_timeframe, InpAtrPeriod);
   if(g_fastHandle == INVALID_HANDLE || g_slowHandle == INVALID_HANDLE || g_atrHandle == INVALID_HANDLE)
   {
      Print("[ERROR] No se pudieron crear las EMAs o el ATR. Código ", GetLastError());
      return INIT_FAILED;
   }
   if(InpUseHtfFilter)
   {
      g_htfHandle = iMA(_Symbol, g_htfTimeframe, InpHtfPeriod, 0, MODE_EMA, PRICE_CLOSE);
      if(g_htfHandle == INVALID_HANDLE)
      {
         Print("[ERROR] No se pudo crear la EMA del marco mayor. Código ", GetLastError());
         return INIT_FAILED;
      }
   }
   if(InpEntryMode == EA_ENTRY_RSI_REVERSION)
   {
      g_rsiHandle = iRSI(_Symbol, g_timeframe, InpRsiPeriod, PRICE_CLOSE);
      if(g_rsiHandle == INVALID_HANDLE)
      {
         Print("[ERROR] No se pudo crear el RSI. Código ", GetLastError());
         return INIT_FAILED;
      }
   }
   if(InpAdxMin > 0.0)
   {
      g_adxHandle = iADX(_Symbol, g_timeframe, InpAdxPeriod);
      if(g_adxHandle == INVALID_HANDLE)
      {
         Print("[ERROR] No se pudo crear el ADX. Código ", GetLastError());
         return INIT_FAILED;
      }
   }

   //--- Configuración de ejecución
   g_trade.SetExpertMagicNumber(InpMagicNumber);
   g_trade.SetDeviationInPoints((ulong)InpSlippagePoints);
   ConfigureFilling();

   InitDrawdownGuard();

   //--- No operar una señal antigua: la primera evaluación será en la próxima vela
   g_lastBarTime = iTime(_Symbol, g_timeframe, 0);
   ClearSignal();

   string stopsText = "SL " + DoubleToString(InpStopLossPips, 1) + " pips | TP " + DoubleToString(InpTakeProfitPips, 1) + " pips";
   if(InpStopMode == EA_STOPS_ATR)
      stopsText = "SL ATR(" + IntegerToString(InpAtrPeriod) + ") x" + DoubleToString(InpAtrSlMultiplier, 1) +
                  " | TP ATR x" + DoubleToString(InpAtrTpMultiplier, 1);
   string filterText = "sin filtro de marco mayor";
   if(InpUseHtfFilter)
      filterText = "filtro " + TimeframeToString(g_htfTimeframe) + " EMA " + IntegerToString(InpHtfPeriod);
   string adxText = "sin filtro ADX";
   if(InpAdxMin > 0.0)
      adxText = "ADX(" + IntegerToString(InpAdxPeriod) + ") >= " + DoubleToString(InpAdxMin, 1);
   string trailText = "sin trailing";
   if(InpTrailAtrMultiplier > 0.0)
      trailText = "trailing ATR x" + DoubleToString(InpTrailAtrMultiplier, 1);
   string accountType = "hedging";
   if(g_isNetting)
      accountType = "netting";

   Print("[INICIO] Robot v4 en ", _Symbol, " ", TimeframeToString(g_timeframe), " | ", EntryModeName(),
         " | ", DirectionName(), " | ", stopsText, " | ", filterText, " | ", adxText, " | ", trailText);
   Print("[INICIO] ", RiskModeText(), " | Cuenta ", accountType, " en ", AccountUnitName(),
         " | 1 pip = ", DoubleToString(g_pip, _Digits), " | Pérdida diaria máx. ",
         DoubleToString(InpMaxDailyLossPercent, 1), "% | Drawdown máx. ", DoubleToString(InpMaxDrawdownPercent, 1), "%");
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Desinicialización                                                |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   if(g_fastHandle != INVALID_HANDLE)
      IndicatorRelease(g_fastHandle);
   if(g_slowHandle != INVALID_HANDLE)
      IndicatorRelease(g_slowHandle);
   if(g_atrHandle != INVALID_HANDLE)
      IndicatorRelease(g_atrHandle);
   if(g_adxHandle != INVALID_HANDLE)
      IndicatorRelease(g_adxHandle);
   if(g_htfHandle != INVALID_HANDLE)
      IndicatorRelease(g_htfHandle);
   if(g_rsiHandle != INVALID_HANDLE)
      IndicatorRelease(g_rsiHandle);
   Comment("");
}

//+------------------------------------------------------------------+
//| Cada tick                                                        |
//+------------------------------------------------------------------+
void OnTick()
{
   datetime now = TimeCurrent();

   //--- 1) Protección y gestión de las posiciones abiertas
   if(InpCloseEndOfDay)
      CloseDayTradePositions(now);
   CheckDailyLoss(now);
   CheckDrawdown();
   ProtectUnprotectedPositions();
   ManageBreakEven();
   ManageTrailing();

   //--- 2) En cada vela nueva, buscar señales en las velas cerradas
   datetime barTime = iTime(_Symbol, g_timeframe, 0);
   if(barTime == 0)
      return;

   if(barTime != g_lastBarTime)
   {
      int    signal = 0;
      string kind   = "";
      if(!GetSignal(signal, kind))
         return; // datos del indicador aún no listos: reintentar en el siguiente tick

      g_lastBarTime = barTime;
      ManageRsiExits();
      if(signal != 0)
      {
         g_lastSignalText = DirName(signal) + " - " + kind + " (" + TimeToString(barTime, TIME_DATE | TIME_MINUTES) + ")";
         Print("[SEÑAL] ", DirName(signal), ": ", kind,
               " (vela cerrada ", TimeToString(iTime(_Symbol, g_timeframe, 1), TIME_DATE | TIME_MINUTES), ")");

         //--- La señal contraria cierra la posición abierta en la otra dirección
         if(InpCloseOnOpposite && CountOpenPositions(-signal) > 0)
            ClosePositions(-signal, "señal contraria (" + kind + ")");

         if(IsDirectionAllowed(signal))
         {
            ClearSignal();
            g_signalBarTime = barTime;
            g_signalDir     = signal;
            g_signalKind    = kind;
            g_entryAttempts = 0;
            g_waitWarned    = false;
         }
         else if(InpLogDiscards)
            Print("[DESCARTE] Señal de ", DirName(signal), ": esa dirección está desactivada en los parámetros");
      }
   }

   //--- 3) Ejecutar la señal pendiente, solo dentro de la vela en la que se generó
   if(g_signalBarTime != 0)
   {
      if(g_signalBarTime != barTime)
         DiscardSignal("caducada: no se pudo ejecutar dentro de su vela");
      else
         TryEnter(now);
   }

   //--- 4) Panel informativo
   if(InpShowPanel)
      UpdatePanel(now);
}
//+------------------------------------------------------------------+
