//+------------------------------------------------------------------+
//|                                           EMA_Cross_DayTrade.mq5 |
//|       Asesor experto: cruce alcista EMA 40 / EMA 200 (compras)   |
//+------------------------------------------------------------------+
#property copyright   "Kathe"
#property version     "1.00"
#property description "Abre una compra cuando la EMA rápida (40) cruza hacia arriba la EMA lenta (200)."
#property description "Stop loss y take profit en pips, filtro de horario y de días, y cierre intradía (day trade)."
#property description "Las señales se evalúan sobre velas cerradas para no operar cruces que luego desaparecen."

#include <Trade/Trade.mqh>
#include <Trade/PositionInfo.mqh>

//--- Intentos de entrada por señal antes de descartarla (recotizaciones, precio cambiado, etc.)
#define MAX_ENTRY_ATTEMPTS 3

//+------------------------------------------------------------------+
//| Parámetros de entrada                                            |
//+------------------------------------------------------------------+
input group "=== Estrategia ==="
input ENUM_TIMEFRAMES    InpTimeframe    = PERIOD_CURRENT; // Marco temporal de las EMAs
input int                InpFastPeriod   = 40;             // Periodo EMA rápida
input int                InpSlowPeriod   = 200;            // Periodo EMA lenta
input ENUM_APPLIED_PRICE InpAppliedPrice = PRICE_CLOSE;    // Precio aplicado a las EMAs

input group "=== Gestión de la operación ==="
input double InpLots            = 0.5;         // Tamaño del lote
input double InpStopLossPips    = 20.0;        // Stop Loss (pips)
input double InpTakeProfitPips  = 40.0;        // Take Profit (pips)
input double InpPipSize         = 0.0;         // Valor de 1 pip en precio (0 = automático)
input double InpMaxSpreadPips   = 3.0;         // Spread máximo para entrar (pips, 0 = sin límite)
input int    InpSlippagePoints  = 10;          // Deslizamiento máximo (puntos)
input bool   InpOnePosition     = true;        // Solo una posición abierta a la vez
input int    InpMaxTradesPerDay = 0;           // Máximo de operaciones por día (0 = sin límite)
input ulong  InpMagicNumber     = 4020040;     // Número mágico
input string InpTradeComment    = "EMA40x200"; // Comentario de las órdenes

input group "=== Horario de operación (hora del servidor del bróker) ==="
input bool InpUseTimeFilter = true; // Activar filtro de horario
input int  InpStartHour     = 8;    // Hora de inicio (0-23)
input int  InpStartMinute   = 0;    // Minuto de inicio (0-59)
input int  InpEndHour       = 20;   // Hora de fin (0-23)
input int  InpEndMinute     = 0;    // Minuto de fin (0-59)

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

input group "=== Visualización ==="
input bool InpShowPanel = true; // Mostrar panel informativo en el gráfico

//+------------------------------------------------------------------+
//| Variables globales                                               |
//+------------------------------------------------------------------+
CTrade          g_trade;
CPositionInfo   g_position;

int             g_fastHandle      = INVALID_HANDLE;
int             g_slowHandle      = INVALID_HANDLE;
ENUM_TIMEFRAMES g_timeframe       = PERIOD_CURRENT;
double          g_pip             = 0.0;

datetime        g_lastBarTime     = 0; // última vela evaluada
datetime        g_signalBarTime   = 0; // vela con una señal pendiente de ejecutar (0 = ninguna)
int             g_entryAttempts   = 0;
bool            g_spreadWarned    = false;
datetime        g_lastPanelUpdate = 0;

//+------------------------------------------------------------------+
//| Inicialización                                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   //--- Validación de parámetros
   if(InpFastPeriod < 1 || InpSlowPeriod < 1 || InpFastPeriod >= InpSlowPeriod)
      return InitError("el periodo de la EMA rápida debe ser menor que el de la EMA lenta");
   if(InpLots <= 0.0)
      return InitError("el tamaño del lote debe ser mayor que 0");
   if(InpStopLossPips <= 0.0 || InpTakeProfitPips <= 0.0)
      return InitError("el stop loss y el take profit deben ser mayores que 0");
   if(InpPipSize < 0.0 || InpMaxSpreadPips < 0.0 || InpSlippagePoints < 0 || InpMaxTradesPerDay < 0)
      return InitError("valor de pip, spread, deslizamiento y máximo diario no pueden ser negativos");
   if(!IsValidTime(InpStartHour, InpStartMinute) || !IsValidTime(InpEndHour, InpEndMinute))
      return InitError("horario de operación inválido (horas 0-23, minutos 0-59)");
   if(!IsValidTime(InpCloseHour, InpCloseMinute))
      return InitError("hora de cierre intradía inválida (horas 0-23, minutos 0-59)");
   if(InpCloseEndOfDay && CloseMinutes() == 0)
      return InitError("la hora de cierre intradía no puede ser 00:00 (usa, por ejemplo, 23:55)");

   g_timeframe = (InpTimeframe == PERIOD_CURRENT) ? (ENUM_TIMEFRAMES)_Period : InpTimeframe;

   //--- Tamaño del pip
   g_pip = (InpPipSize > 0.0) ? InpPipSize : AutoPipSize();
   if(g_pip <= 0.0)
      return InitError("no se pudo determinar el tamaño del pip; indícalo manualmente");

   //--- Lote válido para el símbolo
   const double lots = NormalizeLots(InpLots);
   if(lots <= 0.0)
      return InitError(StringFormat("el lote %.2f es menor que el mínimo del símbolo (%.2f)",
                                    InpLots, SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN)));
   if(MathAbs(lots - InpLots) > 1e-8)
      PrintFormat("Aviso: el lote %.2f se ajustará a %.2f según las reglas del símbolo", InpLots, lots);

   if(InpUseTimeFilter && InpCloseEndOfDay && StartMinutes() < EndMinutes() && EndMinutes() > CloseMinutes())
      PrintFormat("Aviso: el horario termina a las %s pero el cierre intradía es a las %s; "
                  "no se abrirán operaciones después del cierre",
                  FormatHM(InpEndHour, InpEndMinute), FormatHM(InpCloseHour, InpCloseMinute));

   //--- Indicadores
   g_fastHandle = iMA(_Symbol, g_timeframe, InpFastPeriod, 0, MODE_EMA, InpAppliedPrice);
   g_slowHandle = iMA(_Symbol, g_timeframe, InpSlowPeriod, 0, MODE_EMA, InpAppliedPrice);
   if(g_fastHandle == INVALID_HANDLE || g_slowHandle == INVALID_HANDLE)
   {
      PrintFormat("Error al crear las EMAs (código %d)", GetLastError());
      return INIT_FAILED;
   }

   //--- Configuración de ejecución
   g_trade.SetExpertMagicNumber(InpMagicNumber);
   g_trade.SetDeviationInPoints((ulong)InpSlippagePoints);
   g_trade.SetTypeFillingBySymbol(_Symbol);
   g_trade.LogLevel(LOG_LEVEL_ERRORS);

   //--- No operar un cruce antiguo: la primera evaluación será en la próxima vela
   g_lastBarTime   = iTime(_Symbol, g_timeframe, 0);
   g_signalBarTime = 0;

   PrintFormat("EMA Cross %d/%d iniciado en %s %s | Lote %.2f | SL %.1f pips | TP %.1f pips | 1 pip = %s",
               InpFastPeriod, InpSlowPeriod, _Symbol, TimeframeToString(g_timeframe),
               lots, InpStopLossPips, InpTakeProfitPips, DoubleToString(g_pip, _Digits));
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
   Comment("");
}

//+------------------------------------------------------------------+
//| Cada tick                                                        |
//+------------------------------------------------------------------+
void OnTick()
{
   const datetime now = TimeCurrent();

   //--- 1) Day trade: cerrar posiciones al llegar la hora de cierre
   if(InpCloseEndOfDay)
      CloseDayTradePositions(now);

   //--- 2) En cada vela nueva, buscar el cruce en las dos últimas velas cerradas
   const datetime barTime = iTime(_Symbol, g_timeframe, 0);
   if(barTime == 0)
      return;

   if(barTime != g_lastBarTime)
   {
      const int signal = CheckBullishCross();
      if(signal < 0)
         return; // datos del indicador aún no listos: reintentar en el siguiente tick

      g_lastBarTime = barTime;
      if(signal > 0)
      {
         g_signalBarTime = barTime;
         g_entryAttempts = 0;
         g_spreadWarned  = false;
         PrintFormat("Señal de compra: la EMA %d cruzó hacia arriba la EMA %d (vela cerrada %s)",
                     InpFastPeriod, InpSlowPeriod,
                     TimeToString(iTime(_Symbol, g_timeframe, 1), TIME_DATE | TIME_MINUTES));
      }
   }

   //--- 3) Ejecutar la señal pendiente, solo dentro de la vela en la que se generó
   if(g_signalBarTime != 0)
   {
      if(g_signalBarTime != barTime)
      {
         Print("Señal de compra caducada: no se pudo ejecutar dentro de su vela");
         g_signalBarTime = 0;
      }
      else
         TryEnterLong(now);
   }

   //--- 4) Panel informativo
   if(InpShowPanel)
      UpdatePanel(now);
}

//+------------------------------------------------------------------+
//| Señal: 1 = cruce alcista, 0 = sin cruce, -1 = datos no listos     |
//+------------------------------------------------------------------+
int CheckBullishCross()
{
   if(BarsCalculated(g_fastHandle) <= InpFastPeriod || BarsCalculated(g_slowHandle) <= InpSlowPeriod)
      return -1;

   //--- Orden cronológico: [0] = vela 2 (anterior), [1] = vela 1 (última cerrada)
   double fast[], slow[];
   if(CopyBuffer(g_fastHandle, 0, 1, 2, fast) != 2 || CopyBuffer(g_slowHandle, 0, 1, 2, slow) != 2)
      return -1;

   return (fast[0] <= slow[0] && fast[1] > slow[1]) ? 1 : 0;
}

//+------------------------------------------------------------------+
//| Intenta abrir la compra de la señal pendiente                     |
//+------------------------------------------------------------------+
void TryEnterLong(const datetime now)
{
   string reason;
   if(!IsEntryAllowed(now, reason))
   {
      PrintFormat("Señal de compra descartada: %s", reason);
      g_signalBarTime = 0;
      return;
   }

   //--- Con spread alto se espera (dentro de la misma vela) a que se normalice
   const double spreadPips = CurrentSpreadPips();
   if(InpMaxSpreadPips > 0.0 && spreadPips > InpMaxSpreadPips)
   {
      if(!g_spreadWarned)
      {
         PrintFormat("Spread demasiado alto (%.1f pips > %.1f). Se esperará dentro de la vela actual",
                     spreadPips, InpMaxSpreadPips);
         g_spreadWarned = true;
      }
      return;
   }

   if(OpenBuy())
   {
      g_signalBarTime = 0;
      return;
   }

   if(++g_entryAttempts >= MAX_ENTRY_ATTEMPTS)
   {
      PrintFormat("Señal de compra descartada tras %d intentos fallidos", MAX_ENTRY_ATTEMPTS);
      g_signalBarTime = 0;
   }
}

//+------------------------------------------------------------------+
//| Filtros de entrada: día, horario, cierre intradía, límites        |
//+------------------------------------------------------------------+
bool IsEntryAllowed(const datetime now, string &reason)
{
   if(!IsTradingDay(now))
   {
      reason = "día no habilitado para operar";
      return false;
   }
   if(!IsInTradingWindow(now))
   {
      reason = StringFormat("fuera del horario de operación (%s - %s)",
                            FormatHM(InpStartHour, InpStartMinute), FormatHM(InpEndHour, InpEndMinute));
      return false;
   }
   if(IsAfterDailyClose(now))
   {
      reason = StringFormat("ya pasó la hora de cierre intradía (%s)", FormatHM(InpCloseHour, InpCloseMinute));
      return false;
   }
   if(!IsTradingPermitted(reason))
      return false;
   if(InpOnePosition && CountOpenPositions() > 0)
   {
      reason = "ya hay una posición abierta";
      return false;
   }
   if(InpMaxTradesPerDay > 0 && CountTradesToday(now) >= InpMaxTradesPerDay)
   {
      reason = StringFormat("se alcanzó el máximo de %d operaciones por día", InpMaxTradesPerDay);
      return false;
   }
   return true;
}

//+------------------------------------------------------------------+
//| Comprueba que el terminal, la cuenta y el símbolo permiten operar |
//+------------------------------------------------------------------+
bool IsTradingPermitted(string &reason)
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
   const long mode = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_MODE);
   if(mode != SYMBOL_TRADE_MODE_FULL && mode != SYMBOL_TRADE_MODE_LONGONLY)
   {
      reason = "el símbolo no admite nuevas compras en este momento";
      return false;
   }
   return true;
}

//+------------------------------------------------------------------+
//| Abre la compra con SL y TP en pips                               |
//+------------------------------------------------------------------+
bool OpenBuy()
{
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick) || tick.ask <= 0.0)
   {
      Print("No se pudo obtener el precio actual");
      return false;
   }

   const double lots = NormalizeLots(InpLots);
   if(lots <= 0.0)
   {
      PrintFormat("Lote %.2f no válido para %s", InpLots, _Symbol);
      return false;
   }

   const double sl = NormalizePrice(tick.ask - InpStopLossPips * g_pip);
   const double tp = NormalizePrice(tick.ask + InpTakeProfitPips * g_pip);

   //--- Distancia mínima de stops exigida por el bróker (en compras se mide desde el Bid)
   const double minDistance = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   if(minDistance > 0.0 && (tick.bid - sl < minDistance || tp - tick.bid < minDistance))
   {
      PrintFormat("SL/TP demasiado cerca del precio: el bróker exige al menos %.1f pips", minDistance / g_pip);
      return false;
   }

   //--- Margen suficiente
   double margin = 0.0;
   if(OrderCalcMargin(ORDER_TYPE_BUY, _Symbol, lots, tick.ask, margin) &&
      margin > AccountInfoDouble(ACCOUNT_MARGIN_FREE))
   {
      PrintFormat("Margen insuficiente: se necesitan %.2f y hay %.2f libres",
                  margin, AccountInfoDouble(ACCOUNT_MARGIN_FREE));
      return false;
   }

   if(!g_trade.Buy(lots, _Symbol, tick.ask, sl, tp, InpTradeComment) ||
      !IsRetcodeSuccess(g_trade.ResultRetcode()))
   {
      PrintFormat("Error al abrir la compra. Código %u: %s",
                  g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription());
      return false;
   }

   PrintFormat("COMPRA abierta: %.2f lotes a %s | SL %s (-%.1f pips) | TP %s (+%.1f pips)",
               lots, DoubleToString(g_trade.ResultPrice(), _Digits),
               DoubleToString(sl, _Digits), InpStopLossPips,
               DoubleToString(tp, _Digits), InpTakeProfitPips);
   return true;
}

//+------------------------------------------------------------------+
//| Day trade: cierra al llegar la hora de cierre y también cualquier |
//| posición que venga de un día anterior (p. ej. mercado cerrado)    |
//+------------------------------------------------------------------+
void CloseDayTradePositions(const datetime now)
{
   const bool     closeTimeReached = IsAfterDailyClose(now);
   const datetime today            = DayStart(now);

   for(int i = PositionsTotal() - 1; i >= 0; --i)
   {
      if(!g_position.SelectByIndex(i))
         continue;
      if(g_position.Symbol() != _Symbol || (ulong)g_position.Magic() != InpMagicNumber)
         continue;
      if(!closeTimeReached && g_position.Time() >= today)
         continue;

      const ulong ticket = g_position.Ticket();
      if(g_trade.PositionClose(ticket) && IsRetcodeSuccess(g_trade.ResultRetcode()))
         PrintFormat("Day trade: posición #%I64u cerrada (cierre intradía %s)",
                     ticket, FormatHM(InpCloseHour, InpCloseMinute));
      else
         PrintFormat("Day trade: no se pudo cerrar la posición #%I64u. Código %u: %s",
                     ticket, g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription());
   }
}

//+------------------------------------------------------------------+
//| Posiciones abiertas por este EA en este símbolo                   |
//+------------------------------------------------------------------+
int CountOpenPositions()
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; --i)
      if(g_position.SelectByIndex(i) && g_position.Symbol() == _Symbol &&
         (ulong)g_position.Magic() == InpMagicNumber)
         ++count;
   return count;
}

//+------------------------------------------------------------------+
//| Operaciones abiertas hoy por este EA (según el historial)         |
//+------------------------------------------------------------------+
int CountTradesToday(const datetime now)
{
   if(!HistorySelect(DayStart(now), now + 60))
      return 0;

   int count = 0;
   const int total = HistoryDealsTotal();
   for(int i = 0; i < total; ++i)
   {
      const ulong deal = HistoryDealGetTicket(i);
      if(deal == 0)
         continue;
      if(HistoryDealGetString(deal, DEAL_SYMBOL) != _Symbol)
         continue;
      if((ulong)HistoryDealGetInteger(deal, DEAL_MAGIC) != InpMagicNumber)
         continue;
      if((ENUM_DEAL_ENTRY)HistoryDealGetInteger(deal, DEAL_ENTRY) != DEAL_ENTRY_IN)
         continue;
      ++count;
   }
   return count;
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

   string emaLine = "EMAs: calculando...";
   double fast[], slow[];
   if(CopyBuffer(g_fastHandle, 0, 1, 1, fast) == 1 && CopyBuffer(g_slowHandle, 0, 1, 1, slow) == 1)
      emaLine = StringFormat("EMA %d: %s | EMA %d: %s | EMA rápida %s",
                             InpFastPeriod, DoubleToString(fast[0], _Digits),
                             InpSlowPeriod, DoubleToString(slow[0], _Digits),
                             fast[0] > slow[0] ? "por ENCIMA" : "por DEBAJO");

   const string window = InpUseTimeFilter
                         ? StringFormat("%s - %s", FormatHM(InpStartHour, InpStartMinute), FormatHM(InpEndHour, InpEndMinute))
                         : "sin filtro";
   const string dayClose = InpCloseEndOfDay ? FormatHM(InpCloseHour, InpCloseMinute) : "desactivado";

   Comment(StringFormat("EMA Cross %d/%d - Day Trade\n"
                        "%s %s | Lote %.2f | SL %.1f pips | TP %.1f pips\n"
                        "%s\n"
                        "Hora servidor: %s | Día habilitado: %s | En horario: %s (%s)\n"
                        "Cierre intradía: %s\n"
                        "Posiciones abiertas: %d | Spread: %.1f pips",
                        InpFastPeriod, InpSlowPeriod,
                        _Symbol, TimeframeToString(g_timeframe), NormalizeLots(InpLots),
                        InpStopLossPips, InpTakeProfitPips,
                        emaLine,
                        TimeToString(now, TIME_MINUTES), IsTradingDay(now) ? "Sí" : "No",
                        IsInTradingWindow(now) ? "Sí" : "No", window,
                        dayClose,
                        CountOpenPositions(), CurrentSpreadPips()));
}

//+------------------------------------------------------------------+
//| Utilidades de tiempo                                             |
//+------------------------------------------------------------------+
bool IsValidTime(const int hour, const int minute)
{
   return hour >= 0 && hour <= 23 && minute >= 0 && minute <= 59;
}

int StartMinutes() { return InpStartHour * 60 + InpStartMinute; }
int EndMinutes()   { return InpEndHour * 60 + InpEndMinute; }
int CloseMinutes() { return InpCloseHour * 60 + InpCloseMinute; }

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

bool IsTradingDay(const datetime t)
{
   MqlDateTime dt;
   TimeToStruct(t, dt);
   switch(dt.day_of_week)
   {
      case 0: return InpTradeSunday;
      case 1: return InpTradeMonday;
      case 2: return InpTradeTuesday;
      case 3: return InpTradeWednesday;
      case 4: return InpTradeThursday;
      case 5: return InpTradeFriday;
      case 6: return InpTradeSaturday;
   }
   return false;
}

//--- Si inicio == fin se opera todo el día; si inicio > fin la ventana cruza la medianoche
bool IsInTradingWindow(const datetime t)
{
   if(!InpUseTimeFilter)
      return true;

   const int now   = MinutesOfDay(t);
   const int start = StartMinutes();
   const int end   = EndMinutes();
   if(start == end)
      return true;
   if(start < end)
      return now >= start && now < end;
   return now >= start || now < end;
}

bool IsAfterDailyClose(const datetime t)
{
   return InpCloseEndOfDay && MinutesOfDay(t) >= CloseMinutes();
}

string FormatHM(const int hour, const int minute)
{
   return StringFormat("%02d:%02d", hour, minute);
}

//+------------------------------------------------------------------+
//| Utilidades de precio y volumen                                   |
//+------------------------------------------------------------------+
//--- Pip estándar: 10 puntos en cotizaciones de 3 y 5 decimales, 1 punto en el resto
double AutoPipSize()
{
   const int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   return (digits == 3 || digits == 5) ? _Point * 10.0 : _Point;
}

double CurrentSpreadPips()
{
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick))
      return DBL_MAX;
   return (tick.ask - tick.bid) / g_pip;
}

double NormalizePrice(const double price)
{
   const double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tickSize > 0.0)
      return NormalizeDouble(MathRound(price / tickSize) * tickSize, _Digits);
   return NormalizeDouble(price, _Digits);
}

//--- Ajusta el lote al paso del símbolo; devuelve 0 si queda por debajo del mínimo
double NormalizeLots(const double lots)
{
   const double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   const double maxLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   const double step   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(step <= 0.0)
      return 0.0;

   double volume = MathFloor(lots / step + 1e-7) * step;
   if(volume < minLot)
      return 0.0;
   if(maxLot > 0.0 && volume > maxLot)
      volume = maxLot;

   const int volumeDigits = (int)MathMax(0.0, MathCeil(-MathLog10(step)));
   return NormalizeDouble(volume, volumeDigits);
}

bool IsRetcodeSuccess(const uint retcode)
{
   return retcode == TRADE_RETCODE_DONE ||
          retcode == TRADE_RETCODE_DONE_PARTIAL ||
          retcode == TRADE_RETCODE_PLACED;
}

string TimeframeToString(const ENUM_TIMEFRAMES tf)
{
   return StringSubstr(EnumToString(tf), 7); // "PERIOD_M15" -> "M15"
}

int InitError(const string message)
{
   PrintFormat("Parámetros incorrectos: %s", message);
   return INIT_PARAMETERS_INCORRECT;
}
//+------------------------------------------------------------------+
