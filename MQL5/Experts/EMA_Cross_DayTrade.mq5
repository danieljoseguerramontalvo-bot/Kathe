//+------------------------------------------------------------------+
//|                                           EMA_Cross_DayTrade.mq5 |
//|     Robot tendencial EMA 40 / EMA 200: compras y ventas (oro)    |
//+------------------------------------------------------------------+
#property copyright   "Kathe"
#property version     "2.10"
#property description "Robot tendencial con EMA 40 / EMA 200: compra y vende. Pensado para el oro (XAUUSD)."
#property description "Entra en los cruces de las medias y, si se activa, en los retrocesos a favor de la tendencia."
#property description "SL/TP en pips o por ATR, filtro ADX, horario, días, cierre intradía, límite de pérdida diaria y breakeven."

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>

//--- Intentos de entrada por señal antes de descartarla (recotizaciones, precio cambiado, etc.)
#define MAX_ENTRY_ATTEMPTS 3

//+------------------------------------------------------------------+
//| Tipos de los parámetros                                          |
//+------------------------------------------------------------------+
enum ENUM_EA_ENTRY_MODE
{
   EA_ENTRY_CROSS_ONLY     = 0, // Solo cruce EMA 40 / EMA 200 (pocas operaciones)
   EA_ENTRY_CROSS_PULLBACK = 1  // Cruce + retrocesos a favor de la tendencia (más operaciones)
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

//+------------------------------------------------------------------+
//| Parámetros de entrada                                            |
//+------------------------------------------------------------------+
input group "=== Estrategia ==="
input ENUM_TIMEFRAMES    InpTimeframe       = PERIOD_CURRENT;          // Marco temporal de las EMAs
input int                InpFastPeriod      = 40;                      // Periodo EMA rápida
input int                InpSlowPeriod      = 200;                     // Periodo EMA lenta
input ENUM_APPLIED_PRICE InpAppliedPrice    = PRICE_CLOSE;             // Precio aplicado a las EMAs
input ENUM_EA_ENTRY_MODE InpEntryMode       = EA_ENTRY_CROSS_PULLBACK; // Tipo de entrada
input ENUM_EA_DIRECTION  InpDirection       = EA_DIR_BOTH;             // Dirección de las operaciones
input bool               InpCloseOnOpposite = true;                    // Cerrar la posición contraria cuando cambia la señal

input group "=== Gestión de la operación ==="
input double InpLots            = 0.5;         // Tamaño del lote (si el riesgo % es 0)
input double InpRiskPercent     = 0.0;         // Riesgo por operación en % del balance (0 = lote fijo)
input double InpStopLossPips    = 20.0;        // Stop Loss (pips)
input double InpTakeProfitPips  = 40.0;        // Take Profit (pips)
input ENUM_EA_STOP_MODE InpStopMode = EA_STOPS_PIPS; // Tipo de Stop Loss / Take Profit
input int    InpAtrPeriod       = 14;          // Periodo del ATR (modo ATR)
input double InpAtrSlMultiplier = 1.5;         // Stop Loss = ATR x este valor (modo ATR)
input double InpAtrTpMultiplier = 3.0;         // Take Profit = ATR x este valor (modo ATR)
input double InpPipSize         = 0.0;         // Valor de 1 pip en precio (0 = automático; oro = 0.1)
input double InpMaxSpreadPips   = 8.0;         // Spread máximo para entrar (pips, 0 = sin límite)
input int    InpSlippagePoints  = 30;          // Deslizamiento máximo (puntos)
input bool   InpOnePosition     = true;        // Solo una posición abierta a la vez
input int    InpMaxTradesPerDay = 10;          // Máximo de operaciones por día (0 = sin límite)
input ulong  InpMagicNumber     = 4020040;     // Número mágico
input string InpTradeComment    = "EMA40x200"; // Comentario de las órdenes

input group "=== Filtro de fuerza de tendencia (ADX) ==="
input int    InpAdxPeriod = 14;  // Periodo del ADX
input double InpAdxMin    = 0.0; // ADX mínimo para entrar (0 = sin filtro; típico 20-25)

input group "=== Protección ==="
input double InpMaxDailyLossPercent = 5.0; // Pérdida máxima diaria en % del balance (0 = sin límite)
input double InpBreakEvenPips       = 0.0; // Mover el SL a la entrada tras X pips de ganancia (0 = desactivado)
input double InpBreakEvenLockPips   = 2.0; // Pips de ganancia que se aseguran al mover a breakeven

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
int             g_atrHandle       = INVALID_HANDLE; // solo en modo ATR
int             g_adxHandle       = INVALID_HANDLE; // solo con filtro ADX
ENUM_TIMEFRAMES g_timeframe       = PERIOD_CURRENT;
double          g_pip             = 0.0;
bool            g_warmingUp       = false; // la EMA lenta aún no tiene historial suficiente

datetime        g_lastBarTime     = 0;  // última vela evaluada
datetime        g_signalBarTime   = 0;  // vela con una señal pendiente de ejecutar (0 = ninguna)
int             g_signalDir       = 0;  // 1 = compra, -1 = venta
string          g_signalKind      = ""; // descripción de la señal pendiente
int             g_entryAttempts   = 0;
bool            g_spreadWarned    = false;
string          g_lastSignalText  = "ninguna todavía";

datetime        g_lastPanelUpdate = 0;
datetime        g_lastLossCheck   = 0;
datetime        g_lossLimitDay    = 0;  // día en que se alcanzó el límite de pérdida

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
      return "Solo cruces";
   return "Cruces + retrocesos";
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

int InitError(const string message)
{
   Print("Parámetros incorrectos: ", message);
   return INIT_PARAMETERS_INCORRECT;
}

//+------------------------------------------------------------------+
//| Utilidades de precio y volumen                                   |
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

//--- Distancias de SL y TP en precio: pips fijos o ATR de la última vela cerrada
bool GetStopDistances(double &slDistance, double &tpDistance)
{
   slDistance = InpStopLossPips * g_pip;
   tpDistance = InpTakeProfitPips * g_pip;
   if(InpStopMode != EA_STOPS_ATR)
      return true;

   double atr[];
   if(CopyBuffer(g_atrHandle, 0, 1, 1, atr) != 1 || atr[0] <= 0.0)
      return false;
   slDistance = atr[0] * InpAtrSlMultiplier;
   tpDistance = atr[0] * InpAtrTpMultiplier;
   return true;
}

//--- Fuerza de la tendencia (ADX) en la última vela cerrada; -1 si no hay datos
double CurrentAdx()
{
   if(g_adxHandle == INVALID_HANDLE)
      return -1.0;
   double adx[];
   if(CopyBuffer(g_adxHandle, 0, 1, 1, adx) != 1)
      return -1.0;
   return adx[0];
}

//--- Lote fijo o calculado para arriesgar un % del balance si se toca el SL
double CalculateLots(const double slDistance)
{
   if(InpRiskPercent <= 0.0)
      return NormalizeLots(InpLots);

   double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   if(tickSize <= 0.0 || tickValue <= 0.0)
      return 0.0;

   double riskMoney  = AccountInfoDouble(ACCOUNT_BALANCE) * InpRiskPercent / 100.0;
   double lossPerLot = (slDistance / tickSize) * tickValue;
   if(lossPerLot <= 0.0)
      return 0.0;
   return NormalizeLots(riskMoney / lossPerLot);
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
         Print("Posición #", ticket, " cerrada: ", why);
      else
         Print("No se pudo cerrar la posición #", ticket, " (", why, "). Código ",
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
         Print("Day trade: posición #", ticket, " cerrada (cierre intradía ",
               FormatHM(InpCloseHour, InpCloseMinute), ")");
      else
         Print("Day trade: no se pudo cerrar la posición #", ticket, ". Código ",
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

//+------------------------------------------------------------------+
//| Protección: límite de pérdida diaria y breakeven                  |
//+------------------------------------------------------------------+
bool IsLossLimitReached(const datetime now)
{
   return (InpMaxDailyLossPercent > 0.0 && g_lossLimitDay == DayStart(now));
}

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
      Print("Límite de pérdida diaria alcanzado (", DoubleToString(dayResult, 2), " / máximo -",
            DoubleToString(maxLoss, 2), "). Se cierran las posiciones y no se opera más hoy");
      ClosePositions(0, "límite de pérdida diaria");
   }
}

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

      double openPrice = g_position.PriceOpen();
      double currentSl = g_position.StopLoss();
      double newSl     = 0.0;
      bool   move      = false;

      if(SelectedPositionDir() > 0)
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

      if(!move)
         continue;

      ulong  ticket = g_position.Ticket();
      double tp     = g_position.TakeProfit();
      if(g_trade.PositionModify(ticket, newSl, tp) && IsRetcodeSuccess(g_trade.ResultRetcode()))
         Print("Breakeven: SL de la posición #", ticket, " movido a ", DoubleToString(newSl, _Digits));
      else
         Print("Breakeven: no se pudo mover el SL de la posición #", ticket, ". Código ",
               g_trade.ResultRetcode(), ": ", g_trade.ResultRetcodeDescription());
   }
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

bool IsEntryAllowed(const datetime now, const int dir, string &reason)
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
   if(IsLossLimitReached(now))
   {
      reason = "se alcanzó el límite de pérdida diaria";
      return false;
   }
   if(InpAdxMin > 0.0)
   {
      double adx = CurrentAdx();
      if(adx < InpAdxMin)
      {
         reason = "tendencia débil (ADX " + DoubleToString(adx, 1) + " < " + DoubleToString(InpAdxMin, 1) + ")";
         return false;
      }
   }
   if(!IsTradingPermitted(dir, reason))
      return false;
   if(InpOnePosition && CountOpenPositions(0) > 0)
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
   return true;
}

//+------------------------------------------------------------------+
//| Abre la operación (1 = compra, -1 = venta) con SL y TP en pips   |
//+------------------------------------------------------------------+
bool OpenPosition(const int dir)
{
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick) || tick.ask <= 0.0 || tick.bid <= 0.0)
   {
      Print("No se pudo obtener el precio actual");
      return false;
   }

   double slDistance = 0.0;
   double tpDistance = 0.0;
   if(!GetStopDistances(slDistance, tpDistance))
   {
      Print("No se pudo calcular el ATR para el Stop Loss y el Take Profit");
      return false;
   }

   double lots = CalculateLots(slDistance);
   if(lots <= 0.0)
   {
      Print("El lote calculado no es válido o es menor que el mínimo del símbolo (",
            DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN), 2), ")");
      return false;
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
      Print("SL/TP demasiado cerca del precio: el SL (", DoubleToString(slDistance, _Digits),
            ") queda dentro del spread o de la distancia mínima del bróker. Aumente el SL o revise el valor del pip");
      return false;
   }

   //--- Margen suficiente
   ENUM_ORDER_TYPE orderType = ORDER_TYPE_BUY;
   if(dir < 0)
      orderType = ORDER_TYPE_SELL;
   double margin     = 0.0;
   double freeMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   if(OrderCalcMargin(orderType, _Symbol, lots, price, margin) && margin > freeMargin)
   {
      Print("Margen insuficiente: se necesitan ", DoubleToString(margin, 2),
            " y hay ", DoubleToString(freeMargin, 2), " libres");
      return false;
   }

   bool sent = false;
   if(dir > 0)
      sent = g_trade.Buy(lots, _Symbol, price, sl, tp, InpTradeComment);
   else
      sent = g_trade.Sell(lots, _Symbol, price, sl, tp, InpTradeComment);

   if(!sent || !IsRetcodeSuccess(g_trade.ResultRetcode()))
   {
      Print("Error al abrir la ", DirName(dir), ". Código ", g_trade.ResultRetcode(), ": ",
            g_trade.ResultRetcodeDescription());
      return false;
   }

   Print(DirName(dir), " abierta: ", DoubleToString(lots, 2), " lotes a ",
         DoubleToString(g_trade.ResultPrice(), _Digits),
         " | SL ", DoubleToString(sl, _Digits), " | TP ", DoubleToString(tp, _Digits),
         " | Motivo: ", g_signalKind);
   return true;
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

   //--- 1) Cruce de las medias: cambio de tendencia
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

//+------------------------------------------------------------------+
//| Intenta abrir la operación de la señal pendiente                 |
//+------------------------------------------------------------------+
void TryEnter(const datetime now)
{
   string reason = "";
   if(!IsEntryAllowed(now, g_signalDir, reason))
   {
      Print("Señal de ", DirName(g_signalDir), " descartada: ", reason);
      ClearSignal();
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

   if(OpenPosition(g_signalDir))
   {
      ClearSignal();
      return;
   }

   g_entryAttempts++;
   if(g_entryAttempts >= MAX_ENTRY_ATTEMPTS)
   {
      Print("Señal de ", DirName(g_signalDir), " descartada tras ", MAX_ENTRY_ATTEMPTS, " intentos fallidos");
      ClearSignal();
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

   string trendLine = "Tendencia: calculando...";
   if(g_warmingUp)
      trendLine = "Tendencia: calentando indicadores (faltan velas de historial)";
   else
   {
      double fast[];
      double slow[];
      if(CopyBuffer(g_fastHandle, 0, 1, 1, fast) == 1 && CopyBuffer(g_slowHandle, 0, 1, 1, slow) == 1)
      {
         string trend = "BAJISTA (busca ventas)";
         if(fast[0] > slow[0])
            trend = "ALCISTA (busca compras)";
         trendLine = "Tendencia: " + trend +
                     " | EMA " + IntegerToString(InpFastPeriod) + ": " + DoubleToString(fast[0], _Digits) +
                     " | EMA " + IntegerToString(InpSlowPeriod) + ": " + DoubleToString(slow[0], _Digits);
      }
   }

   string window = "sin filtro";
   if(InpUseTimeFilter)
      window = FormatHM(InpStartHour, InpStartMinute) + " - " + FormatHM(InpEndHour, InpEndMinute);

   string dayClose = "desactivado";
   if(InpCloseEndOfDay)
      dayClose = FormatHM(InpCloseHour, InpCloseMinute);

   double slDistance = 0.0;
   double tpDistance = 0.0;
   bool   stopsReady = GetStopDistances(slDistance, tpDistance);

   string stopsText = "SL " + DoubleToString(InpStopLossPips, 1) + " pips (" + DoubleToString(slDistance, _Digits) + ")" +
                      " | TP " + DoubleToString(InpTakeProfitPips, 1) + " pips (" + DoubleToString(tpDistance, _Digits) + ")";
   if(InpStopMode == EA_STOPS_ATR)
   {
      stopsText = "SL ATR x" + DoubleToString(InpAtrSlMultiplier, 1) + " | TP ATR x" + DoubleToString(InpAtrTpMultiplier, 1);
      if(stopsReady)
         stopsText += " (ahora " + DoubleToString(slDistance, _Digits) + " / " + DoubleToString(tpDistance, _Digits) + ")";
   }

   string lotText = "Lote " + DoubleToString(CalculateLots(slDistance), 2);
   if(InpRiskPercent > 0.0)
   {
      lotText = "Riesgo " + DoubleToString(InpRiskPercent, 1) + "%";
      if(stopsReady)
         lotText += " (lote " + DoubleToString(CalculateLots(slDistance), 2) + ")";
   }

   string adxText = "sin filtro ADX";
   if(InpAdxMin > 0.0)
      adxText = "ADX " + DoubleToString(CurrentAdx(), 1) + " (mínimo " + DoubleToString(InpAdxMin, 1) + ")";

   int    trades       = 0;
   double closedProfit = 0.0;
   GetTodayStats(now, trades, closedProfit);
   double dayResult = closedProfit + OpenProfit();

   string text = "Robot tendencial EMA " + IntegerToString(InpFastPeriod) + "/" + IntegerToString(InpSlowPeriod) +
                 " - Day Trade\n";
   text += _Symbol + " " + TimeframeToString(g_timeframe) + " | " + lotText + " | " + stopsText +
           " | 1 pip = " + DoubleToString(g_pip, _Digits) + "\n";
   text += trendLine + "\n";
   text += "Entradas: " + EntryModeName() + " | " + DirectionName() + " | " + adxText + "\n";
   text += "Hora servidor: " + TimeToString(now, TIME_MINUTES) +
           " | Hora PC: " + TimeToString(TimeLocal(), TIME_MINUTES) +
           " | Día habilitado: " + YesNo(IsTradingDay(now)) +
           " | En horario: " + YesNo(IsInTradingWindow(now)) + " (" + window + ")" +
           " | Cierre: " + dayClose + "\n";
   text += "Posiciones: " + IntegerToString(CountOpenPositions(1)) + " compras / " +
           IntegerToString(CountOpenPositions(-1)) + " ventas" +
           " | Operaciones hoy: " + IntegerToString(trades) +
           " | Resultado hoy: " + DoubleToString(dayResult, 2) +
           " | Spread: " + DoubleToString(CurrentSpreadPips(), 1) + " pips\n";
   text += "Última señal: " + g_lastSignalText;
   if(IsLossLimitReached(now))
      text += "\n*** LÍMITE DE PÉRDIDA DIARIA ALCANZADO: sin operar hasta mañana ***";
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
   if(InpLots <= 0.0 && InpRiskPercent <= 0.0)
      return InitError("indique un tamaño de lote mayor que 0 o un riesgo en %");
   if(InpRiskPercent < 0.0 || InpRiskPercent > 100.0)
      return InitError("el riesgo por operación debe estar entre 0 y 100 %");
   if(InpStopLossPips <= 0.0 || InpTakeProfitPips <= 0.0)
      return InitError("el stop loss y el take profit deben ser mayores que 0");
   if(InpPipSize < 0.0 || InpMaxSpreadPips < 0.0 || InpSlippagePoints < 0 || InpMaxTradesPerDay < 0)
      return InitError("valor de pip, spread, deslizamiento y máximo diario no pueden ser negativos");
   if(InpMaxDailyLossPercent < 0.0 || InpBreakEvenPips < 0.0 || InpBreakEvenLockPips < 0.0)
      return InitError("la pérdida diaria y el breakeven no pueden ser negativos");
   if(InpStopMode == EA_STOPS_ATR && (InpAtrPeriod < 1 || InpAtrSlMultiplier <= 0.0 || InpAtrTpMultiplier <= 0.0))
      return InitError("en modo ATR, el periodo y los multiplicadores deben ser mayores que 0");
   if(InpAdxPeriod < 1 || InpAdxMin < 0.0 || InpAdxMin > 100.0)
      return InitError("el periodo del ADX debe ser mayor que 0 y el ADX mínimo estar entre 0 y 100");
   if(InpBreakEvenPips > 0.0 && InpBreakEvenLockPips >= InpBreakEvenPips)
      return InitError("los pips asegurados deben ser menores que los pips para activar el breakeven");
   if(!IsValidTime(InpStartHour, InpStartMinute) || !IsValidTime(InpEndHour, InpEndMinute))
      return InitError("horario de operación inválido (horas 0-23, minutos 0-59)");
   if(!IsValidTime(InpCloseHour, InpCloseMinute))
      return InitError("hora de cierre intradía inválida (horas 0-23, minutos 0-59)");
   if(InpCloseEndOfDay && CloseMinutes() == 0)
      return InitError("la hora de cierre intradía no puede ser 00:00 (use, por ejemplo, 23:55)");

   g_timeframe = InpTimeframe;
   if(g_timeframe == PERIOD_CURRENT)
      g_timeframe = (ENUM_TIMEFRAMES)Period();

   //--- Tamaño del pip
   g_pip = InpPipSize;
   if(g_pip <= 0.0)
      g_pip = AutoPipSize();
   if(g_pip <= 0.0)
      return InitError("no se pudo determinar el tamaño del pip; indíquelo manualmente");

   //--- Lote fijo válido para el símbolo (con riesgo % se comprueba en cada operación)
   if(InpRiskPercent <= 0.0)
   {
      double lots = NormalizeLots(InpLots);
      if(lots <= 0.0)
         return InitError("el lote " + DoubleToString(InpLots, 2) + " es menor que el mínimo del símbolo (" +
                          DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN), 2) + ")");
      if(MathAbs(lots - InpLots) > 0.00000001)
         Print("Aviso: el lote ", DoubleToString(InpLots, 2), " se ajustará a ", DoubleToString(lots, 2),
               " según las reglas del símbolo");
   }

   //--- Avisos de configuración
   double spreadNow = CurrentSpreadPips();
   if(InpStopMode == EA_STOPS_PIPS && spreadNow > 0.0 && InpStopLossPips <= spreadNow * 2.0)
      Print("Aviso: el SL (", DoubleToString(InpStopLossPips, 1), " pips) es muy pequeño frente al spread actual (",
            DoubleToString(spreadNow, 1), " pips). Muchas operaciones se cerrarán por el ruido del precio");
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
   if(InpStopMode == EA_STOPS_ATR)
   {
      g_atrHandle = iATR(_Symbol, g_timeframe, InpAtrPeriod);
      if(g_atrHandle == INVALID_HANDLE)
      {
         Print("Error al crear el ATR. Código ", GetLastError());
         return INIT_FAILED;
      }
   }
   if(InpAdxMin > 0.0)
   {
      g_adxHandle = iADX(_Symbol, g_timeframe, InpAdxPeriod);
      if(g_adxHandle == INVALID_HANDLE)
      {
         Print("Error al crear el ADX. Código ", GetLastError());
         return INIT_FAILED;
      }
   }

   //--- Configuración de ejecución
   g_trade.SetExpertMagicNumber(InpMagicNumber);
   g_trade.SetDeviationInPoints((ulong)InpSlippagePoints);
   ConfigureFilling();

   //--- No operar una señal antigua: la primera evaluación será en la próxima vela
   g_lastBarTime = iTime(_Symbol, g_timeframe, 0);
   ClearSignal();

   string stopsText = "SL " + DoubleToString(InpStopLossPips, 1) + " pips (" + DoubleToString(InpStopLossPips * g_pip, _Digits) + ")" +
                      " | TP " + DoubleToString(InpTakeProfitPips, 1) + " pips (" + DoubleToString(InpTakeProfitPips * g_pip, _Digits) + ")";
   if(InpStopMode == EA_STOPS_ATR)
      stopsText = "SL ATR(" + IntegerToString(InpAtrPeriod) + ") x" + DoubleToString(InpAtrSlMultiplier, 1) +
                  " | TP ATR x" + DoubleToString(InpAtrTpMultiplier, 1);
   string lotText = "Lote " + DoubleToString(NormalizeLots(InpLots), 2);
   if(InpRiskPercent > 0.0)
      lotText = "Riesgo " + DoubleToString(InpRiskPercent, 1) + "% por operación";
   string adxText = "sin filtro ADX";
   if(InpAdxMin > 0.0)
      adxText = "ADX mínimo " + DoubleToString(InpAdxMin, 1);

   Print("Robot tendencial iniciado en ", _Symbol, " ", TimeframeToString(g_timeframe),
         " | 1 pip = ", DoubleToString(g_pip, _Digits), " | ", stopsText, " | ", lotText,
         " | ", EntryModeName(), " | ", DirectionName(), " | ", adxText);
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
   Comment("");
}

//+------------------------------------------------------------------+
//| Cada tick                                                        |
//+------------------------------------------------------------------+
void OnTick()
{
   datetime now = TimeCurrent();

   //--- 1) Protección: cierre intradía, pérdida diaria y breakeven
   if(InpCloseEndOfDay)
      CloseDayTradePositions(now);
   CheckDailyLoss(now);
   ManageBreakEven();

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
      if(signal != 0)
      {
         g_lastSignalText = DirName(signal) + " - " + kind + " (" + TimeToString(barTime, TIME_DATE | TIME_MINUTES) + ")";
         Print("Señal de ", DirName(signal), ": ", kind,
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
            g_spreadWarned  = false;
         }
         else
            Print("Señal de ", DirName(signal), " ignorada: esa dirección está desactivada en los parámetros");
      }
   }

   //--- 3) Ejecutar la señal pendiente, solo dentro de la vela en la que se generó
   if(g_signalBarTime != 0)
   {
      if(g_signalBarTime != barTime)
      {
         Print("Señal de ", DirName(g_signalDir), " caducada: no se pudo ejecutar dentro de su vela");
         ClearSignal();
      }
      else
         TryEnter(now);
   }

   //--- 4) Panel informativo
   if(InpShowPanel)
      UpdatePanel(now);
}
//+------------------------------------------------------------------+
