//+------------------------------------------------------------------+
//|                                           EMA_Cross_DayTrade.mq5 |
//|       Asesor experto: cruce alcista EMA 40 / EMA 200 (compras)   |
//+------------------------------------------------------------------+
#property copyright   "Kathe"
#property version     "1.01"
#property description "Abre una compra cuando la EMA rápida (40) cruza hacia arriba la EMA lenta (200)."
#property description "Stop loss y take profit en pips, filtro de horario y de días, y cierre intradía (day trade)."
#property description "Las señales se evalúan sobre velas cerradas para no operar cruces que luego desaparecen."

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>

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

//--- Si inicio == fin se opera todo el día; si inicio > fin la ventana cruza la medianoche
bool IsInTradingWindow(const datetime t)
{
   if(!InpUseTimeFilter)
      return true;

   int current = MinutesOfDay(t);
   int start   = StartMinutes();
   int end     = EndMinutes();
   if(start == end)
      return true;
   if(start < end)
      return (current >= start && current < end);
   return (current >= start || current < end);
}

bool IsAfterDailyClose(const datetime t)
{
   if(!InpCloseEndOfDay)
      return false;
   return (MinutesOfDay(t) >= CloseMinutes());
}

//+------------------------------------------------------------------+
//| Utilidades de precio, volumen y texto                            |
//+------------------------------------------------------------------+
//--- Pip estándar: 10 puntos en cotizaciones de 3 y 5 decimales, 1 punto en el resto
double AutoPipSize()
{
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   if(digits == 3 || digits == 5)
      return _Point * 10.0;
   return _Point;
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

//--- Ajusta el lote al paso del símbolo; devuelve 0 si queda por debajo del mínimo
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

string TimeframeToString(const ENUM_TIMEFRAMES tf)
{
   return StringSubstr(EnumToString(tf), 7); // "PERIOD_M15" -> "M15"
}

string YesNo(const bool value)
{
   if(value)
      return "Sí";
   return "No";
}

int InitError(const string message)
{
   Print("Parámetros incorrectos: ", message);
   return INIT_PARAMETERS_INCORRECT;
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
//| Posiciones y operaciones de este EA                              |
//+------------------------------------------------------------------+
bool IsOwnPosition()
{
   return (g_position.Symbol() == _Symbol && (ulong)g_position.Magic() == InpMagicNumber);
}

int CountOpenPositions()
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(g_position.SelectByIndex(i) && IsOwnPosition())
         count++;
   }
   return count;
}

//--- Operaciones abiertas hoy por este EA (según el historial)
int CountTradesToday(const datetime now)
{
   if(!HistorySelect(DayStart(now), (datetime)(now + 60)))
      return 0;

   int count = 0;
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
      if(HistoryDealGetInteger(deal, DEAL_ENTRY) != DEAL_ENTRY_IN)
         continue;
      count++;
   }
   return count;
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
   long mode = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_MODE);
   if(mode != SYMBOL_TRADE_MODE_FULL && mode != SYMBOL_TRADE_MODE_LONGONLY)
   {
      reason = "el símbolo no admite nuevas compras en este momento";
      return false;
   }
   return true;
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
      reason = "fuera del horario de operación (" + FormatHM(InpStartHour, InpStartMinute) +
               " - " + FormatHM(InpEndHour, InpEndMinute) + ")";
      return false;
   }
   if(IsAfterDailyClose(now))
   {
      reason = "ya pasó la hora de cierre intradía (" + FormatHM(InpCloseHour, InpCloseMinute) + ")";
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
      reason = "se alcanzó el máximo de " + IntegerToString(InpMaxTradesPerDay) + " operaciones por día";
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

   double lots = NormalizeLots(InpLots);
   if(lots <= 0.0)
   {
      Print("Lote no válido para ", _Symbol, ": ", DoubleToString(InpLots, 2));
      return false;
   }

   double sl = NormalizePrice(tick.ask - InpStopLossPips * g_pip);
   double tp = NormalizePrice(tick.ask + InpTakeProfitPips * g_pip);

   //--- Distancia mínima de stops exigida por el bróker (en compras se mide desde el Bid)
   double minDistance = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   if(minDistance > 0.0 && (tick.bid - sl < minDistance || tp - tick.bid < minDistance))
   {
      Print("SL/TP demasiado cerca del precio: el bróker exige al menos ",
            DoubleToString(minDistance / g_pip, 1), " pips");
      return false;
   }

   //--- Margen suficiente
   double margin = 0.0;
   double freeMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   if(OrderCalcMargin(ORDER_TYPE_BUY, _Symbol, lots, tick.ask, margin) && margin > freeMargin)
   {
      Print("Margen insuficiente: se necesitan ", DoubleToString(margin, 2),
            " y hay ", DoubleToString(freeMargin, 2), " libres");
      return false;
   }

   bool sent = g_trade.Buy(lots, _Symbol, tick.ask, sl, tp, InpTradeComment);
   if(!sent || !IsRetcodeSuccess(g_trade.ResultRetcode()))
   {
      Print("Error al abrir la compra. Código ", g_trade.ResultRetcode(), ": ",
            g_trade.ResultRetcodeDescription());
      return false;
   }

   Print("COMPRA abierta: ", DoubleToString(lots, 2), " lotes a ",
         DoubleToString(g_trade.ResultPrice(), _Digits),
         " | SL ", DoubleToString(sl, _Digits), " (-", DoubleToString(InpStopLossPips, 1), " pips)",
         " | TP ", DoubleToString(tp, _Digits), " (+", DoubleToString(InpTakeProfitPips, 1), " pips)");
   return true;
}

//+------------------------------------------------------------------+
//| Day trade: cierra al llegar la hora de cierre y también cualquier |
//| posición que venga de un día anterior (p. ej. mercado cerrado)    |
//+------------------------------------------------------------------+
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
         Print("Day trade: posición #", ticket, " cerrada (cierre intradía ",
               FormatHM(InpCloseHour, InpCloseMinute), ")");
      else
         Print("Day trade: no se pudo cerrar la posición #", ticket, ". Código ",
               g_trade.ResultRetcode(), ": ", g_trade.ResultRetcodeDescription());
   }
}

//+------------------------------------------------------------------+
//| Señal: 1 = cruce alcista, 0 = sin cruce, -1 = datos no listos     |
//+------------------------------------------------------------------+
int CheckBullishCross()
{
   if(BarsCalculated(g_fastHandle) <= InpFastPeriod || BarsCalculated(g_slowHandle) <= InpSlowPeriod)
      return -1;

   //--- Orden cronológico: [0] = vela 2 (anterior), [1] = vela 1 (última cerrada)
   double fast[];
   double slow[];
   if(CopyBuffer(g_fastHandle, 0, 1, 2, fast) != 2)
      return -1;
   if(CopyBuffer(g_slowHandle, 0, 1, 2, slow) != 2)
      return -1;

   if(fast[0] <= slow[0] && fast[1] > slow[1])
      return 1;
   return 0;
}

//+------------------------------------------------------------------+
//| Intenta abrir la compra de la señal pendiente                     |
//+------------------------------------------------------------------+
void TryEnterLong(const datetime now)
{
   string reason = "";
   if(!IsEntryAllowed(now, reason))
   {
      Print("Señal de compra descartada: ", reason);
      g_signalBarTime = 0;
      return;
   }

   //--- Con spread alto se espera (dentro de la misma vela) a que se normalice
   double spreadPips = CurrentSpreadPips();
   if(InpMaxSpreadPips > 0.0 && spreadPips > InpMaxSpreadPips)
   {
      if(!g_spreadWarned)
      {
         Print("Spread demasiado alto (", DoubleToString(spreadPips, 1), " pips > ",
               DoubleToString(InpMaxSpreadPips, 1), "). Se esperará dentro de la vela actual");
         g_spreadWarned = true;
      }
      return;
   }

   if(OpenBuy())
   {
      g_signalBarTime = 0;
      return;
   }

   g_entryAttempts++;
   if(g_entryAttempts >= MAX_ENTRY_ATTEMPTS)
   {
      Print("Señal de compra descartada tras ", MAX_ENTRY_ATTEMPTS, " intentos fallidos");
      g_signalBarTime = 0;
   }
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
   double fast[];
   double slow[];
   if(CopyBuffer(g_fastHandle, 0, 1, 1, fast) == 1 && CopyBuffer(g_slowHandle, 0, 1, 1, slow) == 1)
   {
      string position = "por DEBAJO";
      if(fast[0] > slow[0])
         position = "por ENCIMA";
      emaLine = "EMA " + IntegerToString(InpFastPeriod) + ": " + DoubleToString(fast[0], _Digits) +
                " | EMA " + IntegerToString(InpSlowPeriod) + ": " + DoubleToString(slow[0], _Digits) +
                " | EMA rápida " + position;
   }

   string window = "sin filtro";
   if(InpUseTimeFilter)
      window = FormatHM(InpStartHour, InpStartMinute) + " - " + FormatHM(InpEndHour, InpEndMinute);

   string dayClose = "desactivado";
   if(InpCloseEndOfDay)
      dayClose = FormatHM(InpCloseHour, InpCloseMinute);

   string text = "EMA Cross " + IntegerToString(InpFastPeriod) + "/" + IntegerToString(InpSlowPeriod) +
                 " - Day Trade\n";
   text += _Symbol + " " + TimeframeToString(g_timeframe) +
           " | Lote " + DoubleToString(NormalizeLots(InpLots), 2) +
           " | SL " + DoubleToString(InpStopLossPips, 1) + " pips" +
           " | TP " + DoubleToString(InpTakeProfitPips, 1) + " pips\n";
   text += emaLine + "\n";
   text += "Hora servidor: " + TimeToString(now, TIME_MINUTES) +
           " | Día habilitado: " + YesNo(IsTradingDay(now)) +
           " | En horario: " + YesNo(IsInTradingWindow(now)) + " (" + window + ")\n";
   text += "Cierre intradía: " + dayClose + "\n";
   text += "Posiciones abiertas: " + IntegerToString(CountOpenPositions()) +
           " | Spread: " + DoubleToString(CurrentSpreadPips(), 1) + " pips";
   Comment(text);
}

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

   g_timeframe = InpTimeframe;
   if(g_timeframe == PERIOD_CURRENT)
      g_timeframe = (ENUM_TIMEFRAMES)Period();

   //--- Tamaño del pip
   g_pip = InpPipSize;
   if(g_pip <= 0.0)
      g_pip = AutoPipSize();
   if(g_pip <= 0.0)
      return InitError("no se pudo determinar el tamaño del pip; indícalo manualmente");

   //--- Lote válido para el símbolo
   double lots = NormalizeLots(InpLots);
   if(lots <= 0.0)
      return InitError("el lote " + DoubleToString(InpLots, 2) + " es menor que el mínimo del símbolo (" +
                       DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN), 2) + ")");
   if(MathAbs(lots - InpLots) > 0.00000001)
      Print("Aviso: el lote ", DoubleToString(InpLots, 2), " se ajustará a ", DoubleToString(lots, 2),
            " según las reglas del símbolo");

   if(InpUseTimeFilter && InpCloseEndOfDay && StartMinutes() < EndMinutes() && EndMinutes() > CloseMinutes())
      Print("Aviso: el horario termina a las ", FormatHM(InpEndHour, InpEndMinute),
            " pero el cierre intradía es a las ", FormatHM(InpCloseHour, InpCloseMinute),
            "; no se abrirán operaciones después del cierre");

   //--- Indicadores
   g_fastHandle = iMA(_Symbol, g_timeframe, InpFastPeriod, 0, MODE_EMA, InpAppliedPrice);
   g_slowHandle = iMA(_Symbol, g_timeframe, InpSlowPeriod, 0, MODE_EMA, InpAppliedPrice);
   if(g_fastHandle == INVALID_HANDLE || g_slowHandle == INVALID_HANDLE)
   {
      Print("Error al crear las EMAs. Código ", GetLastError());
      return INIT_FAILED;
   }

   //--- Configuración de ejecución
   g_trade.SetExpertMagicNumber(InpMagicNumber);
   g_trade.SetDeviationInPoints((ulong)InpSlippagePoints);
   ConfigureFilling();

   //--- No operar un cruce antiguo: la primera evaluación será en la próxima vela
   g_lastBarTime   = iTime(_Symbol, g_timeframe, 0);
   g_signalBarTime = 0;

   Print("EMA Cross ", InpFastPeriod, "/", InpSlowPeriod, " iniciado en ", _Symbol, " ",
         TimeframeToString(g_timeframe), " | Lote ", DoubleToString(lots, 2),
         " | SL ", DoubleToString(InpStopLossPips, 1), " pips | TP ", DoubleToString(InpTakeProfitPips, 1),
         " pips | 1 pip = ", DoubleToString(g_pip, _Digits));
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
   datetime now = TimeCurrent();

   //--- 1) Day trade: cerrar posiciones al llegar la hora de cierre
   if(InpCloseEndOfDay)
      CloseDayTradePositions(now);

   //--- 2) En cada vela nueva, buscar el cruce en las dos últimas velas cerradas
   datetime barTime = iTime(_Symbol, g_timeframe, 0);
   if(barTime == 0)
      return;

   if(barTime != g_lastBarTime)
   {
      int signal = CheckBullishCross();
      if(signal < 0)
         return; // datos del indicador aún no listos: reintentar en el siguiente tick

      g_lastBarTime = barTime;
      if(signal > 0)
      {
         g_signalBarTime = barTime;
         g_entryAttempts = 0;
         g_spreadWarned  = false;
         Print("Señal de compra: la EMA ", InpFastPeriod, " cruzó hacia arriba la EMA ", InpSlowPeriod,
               " (vela cerrada ", TimeToString(iTime(_Symbol, g_timeframe, 1), TIME_DATE | TIME_MINUTES), ")");
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
