//+------------------------------------------------------------------+
//|                                                KatheQuant_v5.mq5 |
//|  Motor de ejecucion modular para XAUUSD (protocolo en             |
//|  MQL5/docs/PROTOCOLO_V5.md).                                      |
//|                                                                  |
//|  Secciones (en este orden):                                       |
//|   1. Parametros            7. Seleccion (filtros de entrada)      |
//|   2. Estado global         8. Riesgo y tamano                     |
//|   3. Utilidades / tiempo   9. Ejecucion                           |
//|   4. Diario CSV           10a. Modo senales (posicion virtual)    |
//|   5. Datos e indicadores  10b. Gestion de posiciones              |
//|   6. Regimen y senales    12. Orquestacion, panel, eventos        |
//|                                                                  |
//|  Ejecucion automatica SOLO en el probador o en una cuenta DEMO    |
//|  con InpAllowDemoTrading = true. En cuentas reales el EA solo     |
//|  emite senales para ejecucion manual. Sin martingala ni grid.     |
//+------------------------------------------------------------------+
#property copyright   "Kathe"
#property version     "5.00"
#property description "Motor modular: senales, regimen, seleccion, riesgo, ejecucion, gestion y diagnostico."
#property description "Opera solo en el probador o en una cuenta DEMO habilitada. En cuentas reales solo emite senales."
#property description "Sin martingala, sin grid y sin aumentos de riesgo para recuperar perdidas."

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>

#define KQ_VERSION        "5.00"
#define KQ_SEND_ATTEMPTS  3     // envios inmediatos ante recotizacion
#define KQ_MAX_RETRIES    5     // reintentos por senal ante errores temporales
#define KQ_MIN_SCORE_N    30    // operaciones minimas para que OnTester puntue

//+------------------------------------------------------------------+
//| 1. Parametros                                                    |
//+------------------------------------------------------------------+
enum ENUM_KQ_STRATEGY
{
   KQ_STRAT_NONE             = 0, // (elige una estrategia)
   KQ_STRAT_TREND_DONCHIAN   = 1, // H1 Tendencia: ruptura Donchian + trailing chandelier
   KQ_STRAT_SESSION_BREAKOUT = 2, // H2 Ruptura del rango asiatico (Londres)
   KQ_STRAT_SESSION_DRIFT    = 3, // H3 Estacionalidad horaria (ventana UTC fija)
   KQ_STRAT_MEANREV_RSI2     = 4, // H4 Reversion RSI(2)
   KQ_STRAT_REF_T0           = 5  // Referencia: EMA 40/200 + ADX (la v4 en real)
};

enum ENUM_KQ_REGIME
{
   KQ_REGIME_OFF        = 0, // Sin filtro de regimen
   KQ_REGIME_TREND_ONLY = 1, // Solo en tendencia (ER diario >= umbral)
   KQ_REGIME_RANGE_ONLY = 2  // Solo en rango (ER diario < umbral)
};

enum ENUM_KQ_SERVER_TZ
{
   KQ_TZ_NY_PLUS_7 = 0, // Servidor = hora de Nueva York + 7 h (HF Markets)
   KQ_TZ_FIXED     = 1  // Desfase fijo respecto a UTC
};

enum ENUM_KQ_DIRECTION
{
   KQ_DIR_BOTH       = 0, // Compras y ventas
   KQ_DIR_LONG_ONLY  = 1, // Solo compras
   KQ_DIR_SHORT_ONLY = 2  // Solo ventas
};

enum ENUM_KQ_DRIFT_SIDE
{
   KQ_DRIFT_LONG  = 0, // Compra durante la ventana
   KQ_DRIFT_SHORT = 1  // Venta durante la ventana
};

input group "=== Modo y estrategia ==="
input ENUM_KQ_STRATEGY InpStrategy         = KQ_STRAT_NONE; // Estrategia activa (obligatorio elegir)
input bool             InpAllowDemoTrading = false;         // Permitir ejecucion automatica en una cuenta DEMO
input bool             InpNotifySignals    = true;          // Alertas y notificaciones push de senales y salidas
input ulong            InpMagic            = 5020050;       // Numero magico
input string           InpComment          = "KQ5";         // Comentario de las ordenes

input group "=== Riesgo ==="
input double InpRiskPercent      = 1.0;   // Riesgo por operacion (% del balance, maximo 2)
input double InpCommissionPerLot = 0.0;   // Comision ida y vuelta por lote (divisa de la cuenta)
input double InpMaxMarginPercent = 30.0;  // Margen maximo por operacion (% del margen libre)
input double InpMaxDailyLossPct  = 3.0;   // Perdida diaria maxima del EA (% del balance inicial del dia, 0 = sin limite)
input bool   InpCloseOnDailyLoss = true;  // Cerrar las posiciones al alcanzar la perdida diaria
input double InpMaxDrawdownPct   = 15.0;  // Drawdown maximo de la cuenta desde su maximo (%, 0 = sin limite)
input bool   InpResetLocks       = false; // Reiniciar los bloqueos de riesgo al cargar (usar una vez)

input group "=== Ejecucion y dias ==="
input int               InpMaxSpreadPoints = 60;          // Spread maximo para entrar (puntos, 0 = sin limite)
input int               InpMaxEntryDelayMin = 90;         // Retraso maximo de la entrada desde la apertura de la vela (min)
input int               InpSlippagePoints  = 30;          // Desviacion maxima al ejecutar (puntos)
input ENUM_KQ_DIRECTION InpDirection       = KQ_DIR_BOTH; // Direcciones permitidas
input bool              InpTradeMonday     = true;        // Operar el lunes
input bool              InpTradeTuesday    = true;        // Operar el martes
input bool              InpTradeWednesday  = true;        // Operar el miercoles
input bool              InpTradeThursday   = true;        // Operar el jueves
input bool              InpTradeFriday     = true;        // Operar el viernes
input int               InpRolloverFromMin = 1425;        // Sin entradas desde este minuto del dia del servidor (23:45 = 1425)
input int               InpRolloverToMin   = 75;          // ... hasta este minuto (01:15 = 75; igual al anterior = sin franja)

input group "=== Hora del servidor ==="
input ENUM_KQ_SERVER_TZ InpServerTz        = KQ_TZ_NY_PLUS_7; // Regla de la hora del servidor
input double            InpServerGmtOffset = 2.0;             // Desfase fijo en horas (solo con desfase fijo)

input group "=== Filtro de regimen (comun a todas) ==="
input ENUM_KQ_REGIME InpRegime      = KQ_REGIME_OFF; // Filtro de regimen
input int            InpErPeriod    = 20;            // Dias del Efficiency Ratio
input double         InpErThreshold = 0.30;          // Umbral del ER (tendencia si >= umbral)
input double         InpVolPctMax   = 100.0;         // No entrar si el ATR diario supera este percentil de 250 dias (100 = sin filtro)
input int            InpAtrPeriod   = 14;            // Periodo del ATR (todas las estrategias)

input group "=== H1 Tendencia (Donchian) ==="
input ENUM_TIMEFRAMES InpTdTimeframe = PERIOD_D1; // Temporalidad
input int             InpTdChannel   = 55;        // Velas del canal de ruptura (N)
input double          InpTdSlAtr     = 2.0;       // Stop inicial = ATR x
input double          InpTdTrailAtr  = 3.0;       // Trailing chandelier = ATR x (0 = sin trailing)

input group "=== H2 Ruptura del rango asiatico ==="
input int    InpSbRangeStartUtc = 0;   // Inicio del rango (hora UTC)
input int    InpSbRangeEndUtc   = 7;   // Fin del rango e inicio de entradas (hora UTC)
input int    InpSbEntryEndUtc   = 12;  // Fin de la ventana de entrada (hora UTC)
input int    InpSbFlatUtc       = 20;  // Cierre forzado (hora UTC)
input double InpSbMaxRangeAtr   = 0.4; // Compresion: ancho del rango / ATR diario maximo (0 = sin filtro)
input double InpSbBufferFrac    = 0.1; // Margen de ruptura (fraccion del ancho)
input double InpSbTpMult        = 1.0; // Objetivo = ancho x (0 = sin objetivo)

input group "=== H3 Estacionalidad horaria ==="
input int                InpSdEntryUtc = 0;             // Hora UTC de entrada
input int                InpSdExitUtc  = 8;             // Hora UTC de salida
input ENUM_KQ_DRIFT_SIDE InpSdSide     = KQ_DRIFT_LONG; // Direccion
input double             InpSdSlAtr    = 3.0;           // Stop de proteccion = ATR(H1) x

input group "=== H4 Reversion RSI(2) ==="
input ENUM_TIMEFRAMES InpMrTimeframe = PERIOD_H1; // Temporalidad
input int             InpMrRsiPeriod = 2;         // Periodo del RSI
input double          InpMrBuyLevel  = 10.0;      // Comprar si el RSI baja de
input double          InpMrSellLevel = 90.0;      // Vender si el RSI sube de
input double          InpMrExitBuy   = 70.0;      // Cerrar compras si el RSI supera
input double          InpMrExitSell  = 30.0;      // Cerrar ventas si el RSI baja de
input int             InpMrEmaPeriod = 200;       // EMA de tendencia
input double          InpMrSlAtr     = 1.5;       // Stop = ATR x
input double          InpMrTpAtr     = 6.0;       // Objetivo = ATR x (0 = sin objetivo)

input group "=== Referencia T0 (EMA 40/200 + ADX) ==="
input ENUM_TIMEFRAMES InpT0Timeframe = PERIOD_H4; // Temporalidad
input int             InpT0Fast      = 40;        // EMA rapida
input int             InpT0Slow      = 200;       // EMA lenta
input double          InpT0AdxMin    = 20.0;      // ADX minimo para entrar
input double          InpT0SlAtr     = 1.5;       // Stop = ATR x
input double          InpT0TpAtr     = 3.0;       // Objetivo = ATR x

input group "=== Registro y panel ==="
input bool InpJournal     = true; // Diario CSV (carpeta comun: Common\Files)
input bool InpLogDiscards = true; // Registrar las senales descartadas
input bool InpShowPanel   = true; // Mostrar el panel en el grafico

//+------------------------------------------------------------------+
//| 2. Estado global                                                 |
//+------------------------------------------------------------------+
struct KQSignal
{
   int      dir;            // 1 compra, -1 venta, 0 nada
   datetime barTime;        // apertura de la vela cerrada que genera la senal
   double   stopDistance;   // distancia del SL (si stopPrice = 0)
   double   stopPrice;      // SL absoluto (si > 0)
   double   targetDistance; // distancia del TP (0 = sin TP)
   double   atr;            // ATR de referencia
   datetime dayKey;         // dia UTC (estrategias de una operacion al dia)
   bool     entryOk;        // false = la senal cierra la contraria pero no abre
   string   blockReason;    // motivo si entryOk = false
   string   reason;         // descripcion
};

CTrade        g_trade;
CPositionInfo g_pos;

string          g_sym          = "";
double          g_point        = 0.0;
int             g_digits       = 0;
bool            g_auto         = false; // ejecucion automatica permitida
string          g_modeText     = "";
bool            g_isNetting    = false;
string          g_gv           = "";    // prefijo de variables globales (cuenta + simbolo + magico): bloqueos
string          g_gvs          = "";    // prefijo del estado de la estrategia (anade estrategia + temporalidad)
ENUM_TIMEFRAMES g_signalTf     = PERIOD_H1;
double          g_token        = 0.0;   // identificador de esta instancia
bool            g_lockOwned    = false;

int g_hAtrSig   = INVALID_HANDLE;
int g_hAtrD1    = INVALID_HANDLE;
int g_hAtrH1    = INVALID_HANDLE;
int g_hEmaFast  = INVALID_HANDLE;
int g_hEmaSlow  = INVALID_HANDLE;
int g_hAdx      = INVALID_HANDLE;
int g_hRsi      = INVALID_HANDLE;
int g_hEmaTrend = INVALID_HANDLE;

KQSignal g_pending;
bool     g_hasPending  = false;
datetime g_pendingBar  = 0;
int      g_attempts    = 0;
bool     g_waitWarned  = false;
datetime g_retryAfter  = 0;
datetime g_lastBarSeen = 0;

datetime g_dayKey          = 0;
double   g_dayStartBalance = 0.0;
bool     g_dayLocked       = false;
bool     g_ddLocked        = false;
double   g_ddNow           = 0.0;
double   g_dayResult       = 0.0;

int      g_vDir      = 0;   // posicion virtual del modo senales
double   g_vEntry    = 0.0;
double   g_vSl       = 0.0;
double   g_vTp       = 0.0;
double   g_vLots     = 0.0;
double   g_vRiskDist = 0.0;
datetime g_vTime     = 0;

string   g_lastSignal   = "ninguna todavia";
string   g_lastDecision = "-";
string   g_lastBlock    = "-";
datetime g_lastPanel    = 0;
datetime g_lastDayCalc  = 0;
datetime g_lastFlush    = 0;
datetime g_lastRiskRefresh = 0;
bool     g_journalOn    = true;
int      g_closeDir     = 0;   // cierre pendiente: 1 compras, -1 ventas, 2 todas, 0 ninguno
string   g_closeWhy     = "";
datetime g_closeRetry   = 0;
datetime g_exitRetryAfter = 0; // espera entre reintentos de salidas fallidas
double   g_lastRequested  = 0.0; // precio pedido en el ultimo envio de entrada
bool     g_notifyWarned = false;
bool     g_connWarned   = false;

long     g_statPos[];   // probador: identificador de posicion
double   g_statRisk[];  // probador: dinero en riesgo al abrir

//+------------------------------------------------------------------+
//| 3. Utilidades de texto, tiempo y variables globales              |
//+------------------------------------------------------------------+
string DirName(const int dir)
{
   if(dir > 0)
      return "COMPRA";
   if(dir < 0)
      return "VENTA";
   return "-";
}

string YesNo(const bool value)
{
   if(value)
      return "Si";
   return "No";
}

string TfName(const ENUM_TIMEFRAMES tf)
{
   return StringSubstr(EnumToString(tf), 7);
}

string Pr(const double price)
{
   return DoubleToString(price, g_digits);
}

string StrategyName()
{
   if(InpStrategy == KQ_STRAT_TREND_DONCHIAN)
      return "H1 Tendencia Donchian(" + IntegerToString(InpTdChannel) + ") " + TfName(InpTdTimeframe);
   if(InpStrategy == KQ_STRAT_SESSION_BREAKOUT)
      return "H2 Ruptura rango " + IntegerToString(InpSbRangeStartUtc) + "-" + IntegerToString(InpSbRangeEndUtc) + " UTC";
   if(InpStrategy == KQ_STRAT_SESSION_DRIFT)
   {
      string side = "compra";
      if(InpSdSide == KQ_DRIFT_SHORT)
         side = "venta";
      return "H3 Estacionalidad " + IntegerToString(InpSdEntryUtc) + "-" + IntegerToString(InpSdExitUtc) + " UTC (" + side + ")";
   }
   if(InpStrategy == KQ_STRAT_MEANREV_RSI2)
      return "H4 Reversion RSI(" + IntegerToString(InpMrRsiPeriod) + ") " + TfName(InpMrTimeframe);
   if(InpStrategy == KQ_STRAT_REF_T0)
      return "Ref T0 EMA " + IntegerToString(InpT0Fast) + "/" + IntegerToString(InpT0Slow) + " " + TfName(InpT0Timeframe);
   return "ninguna";
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

datetime MakeDate(const int year, const int mon, const int day, const int hour)
{
   MqlDateTime dt;
   dt.year        = year;
   dt.mon         = mon;
   dt.day         = day;
   dt.hour        = hour;
   dt.min         = 0;
   dt.sec         = 0;
   dt.day_of_week = 0;
   dt.day_of_year = 0;
   return StructToTime(dt);
}

int DayOfWeekOf(const int year, const int mon, const int day)
{
   MqlDateTime dt;
   TimeToStruct(MakeDate(year, mon, day, 0), dt);
   return dt.day_of_week;
}

//--- Horario de verano de EE. UU.: del segundo domingo de marzo al primer domingo de noviembre (02:00 local)
bool IsUsDst(const datetime nyLocal)
{
   MqlDateTime dt;
   TimeToStruct(nyLocal, dt);
   int      firstSunMar  = 1 + (7 - DayOfWeekOf(dt.year, 3, 1)) % 7;
   int      firstSunNov  = 1 + (7 - DayOfWeekOf(dt.year, 11, 1)) % 7;
   datetime dstStart     = MakeDate(dt.year, 3, firstSunMar + 7, 2);
   datetime dstEnd       = MakeDate(dt.year, 11, firstSunNov, 2);
   return (nyLocal >= dstStart && nyLocal < dstEnd);
}

datetime ServerToUtc(const datetime server)
{
   if(InpServerTz == KQ_TZ_FIXED)
      return (datetime)(server - (long)MathRound(InpServerGmtOffset * 3600.0));
   datetime ny = (datetime)(server - 7 * 3600);
   if(IsUsDst(ny))
      return (datetime)(ny + 4 * 3600);
   return (datetime)(ny + 5 * 3600);
}

datetime UtcToServer(const datetime utc)
{
   if(InpServerTz == KQ_TZ_FIXED)
      return (datetime)(utc + (long)MathRound(InpServerGmtOffset * 3600.0));
   datetime ny = (datetime)(utc - 4 * 3600);
   if(!IsUsDst(ny))
      ny = (datetime)(utc - 5 * 3600);
   return (datetime)(ny + 7 * 3600);
}

int UtcHourOf(const datetime server)
{
   MqlDateTime dt;
   TimeToStruct(ServerToUtc(server), dt);
   return dt.hour;
}

bool IsTradingDay(const datetime server)
{
   MqlDateTime dt;
   TimeToStruct(server, dt);
   if(dt.day_of_week == 1) return InpTradeMonday;
   if(dt.day_of_week == 2) return InpTradeTuesday;
   if(dt.day_of_week == 3) return InpTradeWednesday;
   if(dt.day_of_week == 4) return InpTradeThursday;
   if(dt.day_of_week == 5) return InpTradeFriday;
   return false;
}

//--- Franja del rollover diario (spread ancho): puede cruzar la medianoche
bool InRolloverWindow(const datetime server)
{
   if(InpRolloverFromMin == InpRolloverToMin)
      return false;
   MqlDateTime dt;
   TimeToStruct(server, dt);
   int minute = dt.hour * 60 + dt.min;
   if(InpRolloverFromMin < InpRolloverToMin)
      return (minute >= InpRolloverFromMin && minute < InpRolloverToMin);
   return (minute >= InpRolloverFromMin || minute < InpRolloverToMin);
}

string GvName(const string key)
{
   return g_gv + key;
}

double GvGet(const string key, const double fallback)
{
   string name = GvName(key);
   if(GlobalVariableCheck(name))
      return GlobalVariableGet(name);
   return fallback;
}

//--- MT5 solo guarda las variables globales al cerrar el terminal: se fuerza el guardado del estado critico
void FlushState()
{
   if(!MQLInfoInteger(MQL_TESTER))
      GlobalVariablesFlush();
}

void GvSet(const string key, const double value)
{
   GlobalVariableSet(GvName(key), value);
   if(key != "peak")
      FlushState();
}

void GvDel(const string key)
{
   string name = GvName(key);
   if(GlobalVariableCheck(name))
      GlobalVariableDel(name);
}

//--- Estado de la estrategia (ultima vela, dias usados, posicion virtual): separado por estrategia y temporalidad
double SsGet(const string key, const double fallback)
{
   string name = g_gvs + key;
   if(GlobalVariableCheck(name))
      return GlobalVariableGet(name);
   return fallback;
}

void SsSet(const string key, const double value)
{
   GlobalVariableSet(g_gvs + key, value);
   FlushState();
}

//--- Riesgo inicial por posicion (para el multiplo R de cada salida)
string RiskGvName(const long positionId)
{
   return "KQ5R_" + IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN)) + "_" + IntegerToString(positionId);
}

//+------------------------------------------------------------------+
//| 4. Diario CSV (carpeta comun) y notificaciones                    |
//+------------------------------------------------------------------+
string JournalFile(const string kind)
{
   string prefix = "KQ5_";
   if(MQLInfoInteger(MQL_TESTER))
      prefix = "KQ5T_";
   return prefix + IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN)) + "_" + g_sym + "_" +
          IntegerToString((long)InpMagic) + "_" + kind + ".csv";
}

void JournalAppend(const string kind, const string header, const string line)
{
   if(!InpJournal || !g_journalOn)
      return;
   string name   = JournalFile(kind);
   bool   exists = FileIsExist(name, FILE_COMMON);
   int    handle = FileOpen(name, FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_COMMON);
   if(handle == INVALID_HANDLE)
   {
      Print("[ERROR] No se pudo abrir el diario ", name, ". Codigo ", GetLastError());
      return;
   }
   FileSeek(handle, 0, SEEK_END);
   if(!exists)
      FileWriteString(handle, header + "\r\n");
   FileWriteString(handle, line + "\r\n");
   FileClose(handle);
}

string ModeTag()
{
   if(g_auto)
      return "AUTO";
   return "SENALES";
}

void JournalSignal(const KQSignal &sig, const string decision, const string detail, const double expectedPrice,
                   const double sl, const double tp, const double lots, const double riskMoney)
{
   datetime now    = TimeCurrent();
   string   header = "time_server;time_utc;mode;strategy;signal_bar;dir;decision;detail;expected_price;sl;tp;lots;risk_money;spread_points;reason";
   string   line   = TimeToString(now, TIME_DATE | TIME_SECONDS) + ";" +
                     TimeToString(ServerToUtc(now), TIME_DATE | TIME_SECONDS) + ";" +
                     ModeTag() + ";" + IntegerToString((int)InpStrategy) + ";" +
                     TimeToString(sig.barTime, TIME_DATE | TIME_MINUTES) + ";" +
                     IntegerToString(sig.dir) + ";" + decision + ";" + detail + ";" +
                     Pr(expectedPrice) + ";" + Pr(sl) + ";" + Pr(tp) + ";" +
                     DoubleToString(lots, 2) + ";" + DoubleToString(riskMoney, 2) + ";" +
                     IntegerToString((int)SymbolInfoInteger(g_sym, SYMBOL_SPREAD)) + ";" + sig.reason;
   JournalAppend("senales", header, line);
}

void JournalTrade(const string eventName, const long ticket, const long positionId, const int dir, const double lots,
                  const double requested, const double executed, const double sl, const double tp,
                  const double profit, const double rMultiple, const string reason, const uint retcode,
                  const double commission = 0.0, const double swap = 0.0)
{
   datetime now      = TimeCurrent();
   double   slipPts  = 0.0;
   if(requested > 0.0 && executed > 0.0 && g_point > 0.0)
      slipPts = (executed - requested) / g_point * dir; // positivo = en contra al comprar
   string header = "time_server;time_utc;mode;event;ticket;position_id;dir;lots;requested_price;executed_price;slippage_points;spread_points;sl;tp;net_profit;commission;swap;r_multiple;reason;retcode";
   string line   = TimeToString(now, TIME_DATE | TIME_SECONDS) + ";" +
                   TimeToString(ServerToUtc(now), TIME_DATE | TIME_SECONDS) + ";" +
                   ModeTag() + ";" + eventName + ";" + IntegerToString(ticket) + ";" + IntegerToString(positionId) + ";" +
                   IntegerToString(dir) + ";" + DoubleToString(lots, 2) + ";" + Pr(requested) + ";" + Pr(executed) + ";" +
                   DoubleToString(slipPts, 1) + ";" + IntegerToString((int)SymbolInfoInteger(g_sym, SYMBOL_SPREAD)) + ";" +
                   Pr(sl) + ";" + Pr(tp) + ";" + DoubleToString(profit, 2) + ";" + DoubleToString(commission, 2) + ";" +
                   DoubleToString(swap, 2) + ";" + DoubleToString(rMultiple, 3) + ";" +
                   reason + ";" + IntegerToString((long)retcode);
   JournalAppend("operaciones", header, line);
}

void Notify(const string text)
{
   Print(text);
   if(!InpNotifySignals || MQLInfoInteger(MQL_TESTER))
      return;
   Alert(text);
   if(!SendNotification(text) && !g_notifyWarned)
   {
      Print("[AVISO] No se pudo enviar la notificacion push (configura el MetaQuotes ID en Herramientas > Opciones > Notificaciones)");
      g_notifyWarned = true;
   }
}

//+------------------------------------------------------------------+
//| 5. Precios, volumen y datos                                      |
//+------------------------------------------------------------------+
double NormalizePrice(const double price)
{
   double tickSize = SymbolInfoDouble(g_sym, SYMBOL_TRADE_TICK_SIZE);
   if(tickSize > 0.0)
      return NormalizeDouble(MathRound(price / tickSize) * tickSize, g_digits);
   return NormalizeDouble(price, g_digits);
}

double MinStopDistance()
{
   return (double)SymbolInfoInteger(g_sym, SYMBOL_TRADE_STOPS_LEVEL) * g_point;
}

double FreezeDistance()
{
   return (double)SymbolInfoInteger(g_sym, SYMBOL_TRADE_FREEZE_LEVEL) * g_point;
}

//--- Redondea el volumen hacia abajo al paso del simbolo; 0 si queda por debajo del minimo
double NormalizeLots(const double lots)
{
   double minLot = SymbolInfoDouble(g_sym, SYMBOL_VOLUME_MIN);
   double maxLot = SymbolInfoDouble(g_sym, SYMBOL_VOLUME_MAX);
   double step   = SymbolInfoDouble(g_sym, SYMBOL_VOLUME_STEP);
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

//--- ¿Sesion de trading abierta ahora? (sin datos de sesiones = abierta: decide el servidor)
bool IsTradeSessionOpen(const datetime t)
{
   MqlDateTime dt;
   TimeToStruct(t, dt);
   long     secondsOfDay = dt.hour * 3600 + dt.min * 60 + dt.sec;
   datetime from         = 0;
   datetime to           = 0;
   bool     anySession   = false;
   for(uint i = 0; i < 10; i++)
   {
      if(!SymbolInfoSessionTrade(g_sym, (ENUM_DAY_OF_WEEK)dt.day_of_week, i, from, to))
         break;
      anySession = true;
      long start = (long)from;
      long end   = (long)to;
      if(end <= start)
         end = 86400;
      if(secondsOfDay >= start && secondsOfDay < end)
         return true;
   }
   return !anySession;
}

//--- Lee un valor de un indicador en una vela cerrada
bool ReadBuffer(const int handle, const int buffer, const int shift, double &value)
{
   if(handle == INVALID_HANDLE)
      return false;
   double tmp[];
   if(CopyBuffer(handle, buffer, shift, 1, tmp) != 1)
      return false;
   if(tmp[0] == EMPTY_VALUE || !MathIsValidNumber(tmp[0]))
      return false;
   value = tmp[0];
   return true;
}

bool IndicatorReady(const int handle, const int minBars)
{
   if(handle == INVALID_HANDLE)
      return false;
   return (BarsCalculated(handle) >= minBars);
}

bool SeriesReady(const ENUM_TIMEFRAMES tf, const int minBars)
{
   return (Bars(g_sym, tf) >= minBars);
}

//+------------------------------------------------------------------+
//| 6. Regimen y generacion de senales                               |
//+------------------------------------------------------------------+
//--- Efficiency Ratio de Kaufman con cierres diarios CERRADOS
bool EfficiencyRatioD1(double &er)
{
   int    n = InpErPeriod;
   double c[];
   if(CopyClose(g_sym, PERIOD_D1, 1, n + 1, c) != n + 1)
      return false;
   double path = 0.0;
   for(int i = 1; i <= n; i++)
      path += MathAbs(c[i] - c[i - 1]);
   if(path <= 0.0)
      return false;
   er = MathAbs(c[n] - c[0]) / path;
   return true;
}

//--- Percentil del ATR diario actual (vela cerrada) dentro de los ultimos 250 dias
bool AtrPercentileD1(double &pct)
{
   int    lookback = 250;
   double a[];
   if(!IndicatorReady(g_hAtrD1, lookback + InpAtrPeriod))
      return false;
   if(CopyBuffer(g_hAtrD1, 0, 1, lookback, a) != lookback)
      return false;
   double last  = a[lookback - 1];
   int    below = 0;
   for(int i = 0; i < lookback; i++)
   {
      if(a[i] <= last)
         below++;
   }
   pct = 100.0 * below / lookback;
   return true;
}

void ResetSignal(KQSignal &s)
{
   s.dir            = 0;
   s.barTime        = 0;
   s.stopDistance   = 0.0;
   s.stopPrice      = 0.0;
   s.targetDistance = 0.0;
   s.atr            = 0.0;
   s.dayKey         = 0;
   s.entryOk        = true;
   s.blockReason    = "";
   s.reason         = "";
}

void CopySignal(KQSignal &dst, const KQSignal &src)
{
   dst.dir            = src.dir;
   dst.barTime        = src.barTime;
   dst.stopDistance   = src.stopDistance;
   dst.stopPrice      = src.stopPrice;
   dst.targetDistance = src.targetDistance;
   dst.atr            = src.atr;
   dst.dayKey         = src.dayKey;
   dst.entryOk        = src.entryOk;
   dst.blockReason    = src.blockReason;
   dst.reason         = src.reason;
}

//--- Devuelven 1 si la evaluacion se hizo (con o sin senal) y 0 si faltan datos

//--- H1: ruptura del canal Donchian de las N velas anteriores a la cerrada
int EvalTrendDonchian(KQSignal &sig)
{
   int n = InpTdChannel;
   if(!SeriesReady(g_signalTf, n + InpAtrPeriod + 5) || !IndicatorReady(g_hAtrSig, InpAtrPeriod + 2))
      return 0;
   double highs[];
   double lows[];
   double closes[];
   if(CopyHigh(g_sym, g_signalTf, 2, n, highs) != n)
      return 0;
   if(CopyLow(g_sym, g_signalTf, 2, n, lows) != n)
      return 0;
   if(CopyClose(g_sym, g_signalTf, 1, 1, closes) != 1)
      return 0;
   double atr = 0.0;
   if(!ReadBuffer(g_hAtrSig, 0, 1, atr) || atr <= 0.0)
      return 0;
   double upper = highs[ArrayMaximum(highs)];
   double lower = lows[ArrayMinimum(lows)];
   sig.barTime = iTime(g_sym, g_signalTf, 1);
   sig.atr     = atr;
   if(closes[0] > upper)
   {
      sig.dir          = 1;
      sig.stopDistance = InpTdSlAtr * atr;
      sig.reason       = "cierre " + Pr(closes[0]) + " sobre el maximo de " + IntegerToString(n) + " velas (" + Pr(upper) + ")";
   }
   else if(closes[0] < lower)
   {
      sig.dir          = -1;
      sig.stopDistance = InpTdSlAtr * atr;
      sig.reason       = "cierre " + Pr(closes[0]) + " bajo el minimo de " + IntegerToString(n) + " velas (" + Pr(lower) + ")";
   }
   return 1;
}

//--- H2: ruptura del rango UTC [inicio, fin) con el cierre de una vela M5 dentro de la ventana de entrada
int EvalSessionBreakout(KQSignal &sig)
{
   datetime barOpen = iTime(g_sym, PERIOD_M5, 1);
   if(barOpen == 0)
      return 0;
   datetime closeUtc = ServerToUtc((datetime)(barOpen + PeriodSeconds(PERIOD_M5)));
   MqlDateTime u;
   TimeToStruct(closeUtc, u);
   int minuteOfDay = u.hour * 60 + u.min;
   if(minuteOfDay <= InpSbRangeEndUtc * 60 || minuteOfDay > InpSbEntryEndUtc * 60)
      return 1;
   if(u.day_of_week == 0 || u.day_of_week == 6)
      return 1;

   datetime utcDay = DayStart(closeUtc);
   if(SsGet("sb_day", 0.0) == (double)utcDay || SsGet("sb_skip", 0.0) == (double)utcDay)
      return 1;

   datetime fromServer = UtcToServer((datetime)(utcDay + InpSbRangeStartUtc * 3600));
   datetime toServer   = UtcToServer((datetime)(utcDay + InpSbRangeEndUtc * 3600)) - 60;
   MqlRates rates[];
   int      n        = CopyRates(g_sym, PERIOD_M1, fromServer, toServer, rates);
   int      expected = (InpSbRangeEndUtc - InpSbRangeStartUtc) * 60;
   if(n < 0)
      return 0;
   if(n < expected / 2)
   {
      if(SeriesInfoInteger(g_sym, PERIOD_M1, SERIES_SYNCHRONIZED) == 0)
         return 0;
      SsSet("sb_skip", (double)utcDay);
      if(InpLogDiscards)
         Print("[DESCARTE] Ruptura: datos insuficientes del rango (", n, " de ", expected, " velas M1)");
      return 1;
   }
   double hi = rates[0].high;
   double lo = rates[0].low;
   for(int i = 1; i < n; i++)
   {
      if(rates[i].high > hi)
         hi = rates[i].high;
      if(rates[i].low < lo)
         lo = rates[i].low;
   }
   double width = hi - lo;
   double atrD1 = 0.0;
   if(width <= 0.0 || !ReadBuffer(g_hAtrD1, 0, 1, atrD1) || atrD1 <= 0.0)
      return 0;
   if(InpSbMaxRangeAtr > 0.0 && width / atrD1 > InpSbMaxRangeAtr)
   {
      SsSet("sb_skip", (double)utcDay);
      if(InpLogDiscards)
         Print("[DESCARTE] Ruptura: rango sin compresion (ancho/ATR = ", DoubleToString(width / atrD1, 2),
               " > ", DoubleToString(InpSbMaxRangeAtr, 2), ")");
      return 1;
   }
   double close  = iClose(g_sym, PERIOD_M5, 1);
   double buffer = InpSbBufferFrac * width;
   sig.barTime   = barOpen;
   sig.atr       = atrD1;
   sig.dayKey    = utcDay;
   if(close > hi + buffer)
   {
      sig.dir            = 1;
      sig.stopPrice      = lo;
      sig.targetDistance = InpSbTpMult * width;
      sig.reason         = "cierre M5 " + Pr(close) + " sobre el rango " + Pr(lo) + "-" + Pr(hi);
   }
   else if(close < lo - buffer)
   {
      sig.dir            = -1;
      sig.stopPrice      = hi;
      sig.targetDistance = InpSbTpMult * width;
      sig.reason         = "cierre M5 " + Pr(close) + " bajo el rango " + Pr(lo) + "-" + Pr(hi);
   }
   return 1;
}

//--- H3: entrada al abrir la vela H1 de la hora UTC indicada
int EvalSessionDrift(KQSignal &sig)
{
   datetime barOpen = iTime(g_sym, PERIOD_H1, 0);
   if(barOpen == 0)
      return 0;
   datetime utc = ServerToUtc(barOpen);
   MqlDateTime u;
   TimeToStruct(utc, u);
   if(u.hour != InpSdEntryUtc || u.day_of_week == 0 || u.day_of_week == 6)
      return 1;
   datetime utcDay = DayStart(utc);
   if(SsGet("sd_day", 0.0) == (double)utcDay)
      return 1;
   double atr = 0.0;
   if(!IndicatorReady(g_hAtrH1, InpAtrPeriod + 2) || !ReadBuffer(g_hAtrH1, 0, 1, atr) || atr <= 0.0)
      return 0;
   sig.dir = 1;
   if(InpSdSide == KQ_DRIFT_SHORT)
      sig.dir = -1;
   sig.barTime      = iTime(g_sym, PERIOD_H1, 1);
   sig.stopDistance = InpSdSlAtr * atr;
   sig.atr          = atr;
   sig.dayKey       = utcDay;
   sig.reason       = "ventana " + IntegerToString(InpSdEntryUtc) + ":00-" + IntegerToString(InpSdExitUtc) + ":00 UTC";
   return 1;
}

//--- H4: RSI extremo a favor de la EMA de tendencia
int EvalMeanRevRsi2(KQSignal &sig)
{
   if(!SeriesReady(g_signalTf, InpMrEmaPeriod * 3))
      return 0;
   if(!IndicatorReady(g_hEmaTrend, InpMrEmaPeriod + 2) || !IndicatorReady(g_hRsi, InpMrRsiPeriod + 2) ||
      !IndicatorReady(g_hAtrSig, InpAtrPeriod + 2))
      return 0;
   double ema = 0.0;
   double rsi = 0.0;
   double atr = 0.0;
   if(!ReadBuffer(g_hEmaTrend, 0, 1, ema) || !ReadBuffer(g_hRsi, 0, 1, rsi) || !ReadBuffer(g_hAtrSig, 0, 1, atr) || atr <= 0.0)
      return 0;
   double close = iClose(g_sym, g_signalTf, 1);
   sig.barTime  = iTime(g_sym, g_signalTf, 1);
   sig.atr      = atr;
   string rsiText = "RSI(" + IntegerToString(InpMrRsiPeriod) + ") = " + DoubleToString(rsi, 1);
   if(close > ema && rsi < InpMrBuyLevel)
   {
      sig.dir            = 1;
      sig.stopDistance   = InpMrSlAtr * atr;
      sig.targetDistance = InpMrTpAtr * atr;
      sig.reason         = rsiText + " sobreventa con el precio sobre la EMA " + IntegerToString(InpMrEmaPeriod);
   }
   else if(close < ema && rsi > InpMrSellLevel)
   {
      sig.dir            = -1;
      sig.stopDistance   = InpMrSlAtr * atr;
      sig.targetDistance = InpMrTpAtr * atr;
      sig.reason         = rsiText + " sobrecompra con el precio bajo la EMA " + IntegerToString(InpMrEmaPeriod);
   }
   return 1;
}

//--- Referencia T0 (misma logica que la v4): cruce o retroceso a la EMA rapida; el ADX filtra la entrada
int EvalRefT0(KQSignal &sig)
{
   if(!SeriesReady(g_signalTf, InpT0Slow * 3))
      return 0;
   if(!IndicatorReady(g_hEmaFast, InpT0Fast + 2) || !IndicatorReady(g_hEmaSlow, InpT0Slow + 2) ||
      !IndicatorReady(g_hAtrSig, InpAtrPeriod + 2) || !IndicatorReady(g_hAdx, 28))
      return 0;
   double fast[];
   double slow[];
   double closes[];
   if(CopyBuffer(g_hEmaFast, 0, 1, 2, fast) != 2 || CopyBuffer(g_hEmaSlow, 0, 1, 2, slow) != 2)
      return 0;
   if(CopyClose(g_sym, g_signalTf, 1, 2, closes) != 2)
      return 0;
   double atr = 0.0;
   double adx = 0.0;
   if(!ReadBuffer(g_hAtrSig, 0, 1, atr) || atr <= 0.0 || !ReadBuffer(g_hAdx, 0, 1, adx))
      return 0;
   sig.barTime = iTime(g_sym, g_signalTf, 1);
   sig.atr     = atr;
   // [0] = vela 2, [1] = vela 1 (ultima cerrada)
   if(fast[0] <= slow[0] && fast[1] > slow[1])
   {
      sig.dir    = 1;
      sig.reason = "cruce alcista EMA " + IntegerToString(InpT0Fast) + "/" + IntegerToString(InpT0Slow);
   }
   else if(fast[0] >= slow[0] && fast[1] < slow[1])
   {
      sig.dir    = -1;
      sig.reason = "cruce bajista EMA " + IntegerToString(InpT0Fast) + "/" + IntegerToString(InpT0Slow);
   }
   else if(fast[1] > slow[1] && closes[0] <= fast[0] && closes[1] > fast[1])
   {
      sig.dir    = 1;
      sig.reason = "retroceso alcista a la EMA " + IntegerToString(InpT0Fast);
   }
   else if(fast[1] < slow[1] && closes[0] >= fast[0] && closes[1] < fast[1])
   {
      sig.dir    = -1;
      sig.reason = "retroceso bajista a la EMA " + IntegerToString(InpT0Fast);
   }
   if(sig.dir == 0)
      return 1;
   sig.stopDistance   = InpT0SlAtr * atr;
   sig.targetDistance = InpT0TpAtr * atr;
   if(adx < InpT0AdxMin)
   {
      sig.entryOk     = false;
      sig.blockReason = "tendencia debil (ADX " + DoubleToString(adx, 1) + " < " + DoubleToString(InpT0AdxMin, 1) + ")";
   }
   return 1;
}

int EvaluateStrategy(KQSignal &sig)
{
   ResetSignal(sig);
   if(InpStrategy == KQ_STRAT_TREND_DONCHIAN)
      return EvalTrendDonchian(sig);
   if(InpStrategy == KQ_STRAT_SESSION_BREAKOUT)
      return EvalSessionBreakout(sig);
   if(InpStrategy == KQ_STRAT_SESSION_DRIFT)
      return EvalSessionDrift(sig);
   if(InpStrategy == KQ_STRAT_MEANREV_RSI2)
      return EvalMeanRevRsi2(sig);
   if(InpStrategy == KQ_STRAT_REF_T0)
      return EvalRefT0(sig);
   return 0;
}

//+------------------------------------------------------------------+
//| 7. Posiciones propias y seleccion de operaciones                 |
//+------------------------------------------------------------------+
bool IsOwnPosition()
{
   return (g_pos.Symbol() == g_sym && (ulong)g_pos.Magic() == InpMagic);
}

int SelectedDir()
{
   if(g_pos.PositionType() == POSITION_TYPE_BUY)
      return 1;
   return -1;
}

//--- dirFilter: 0 = todas, 1 = compras, -1 = ventas
int CountOwnPositions(const int dirFilter)
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(!g_pos.SelectByIndex(i) || !IsOwnPosition())
         continue;
      if(dirFilter == 0 || SelectedDir() == dirFilter)
         count++;
   }
   return count;
}

//--- Direccion de la exposicion actual: posiciones reales (modo auto) o virtual (modo senales)
int CurrentExposureDir()
{
   if(!g_auto)
      return g_vDir;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(g_pos.SelectByIndex(i) && IsOwnPosition())
         return SelectedDir();
   }
   return 0;
}

bool IsDirectionAllowed(const int dir)
{
   if(dir > 0)
      return (InpDirection != KQ_DIR_SHORT_ONLY);
   if(dir < 0)
      return (InpDirection != KQ_DIR_LONG_ONLY);
   return false;
}

bool IsTradingPermitted(const int dir, string &reason)
{
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
   {
      reason = "Algo Trading desactivado en el terminal";
      return false;
   }
   if(!MQLInfoInteger(MQL_TRADE_ALLOWED))
   {
      reason = "el EA no tiene permiso para operar (Comun > Permitir Algo Trading)";
      return false;
   }
   if(!AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) || !AccountInfoInteger(ACCOUNT_TRADE_EXPERT))
   {
      reason = "la cuenta no permite operar con asesores";
      return false;
   }
   long mode = SymbolInfoInteger(g_sym, SYMBOL_TRADE_MODE);
   if(mode == SYMBOL_TRADE_MODE_FULL)
      return true;
   if(dir > 0 && mode == SYMBOL_TRADE_MODE_LONGONLY)
      return true;
   if(dir < 0 && mode == SYMBOL_TRADE_MODE_SHORTONLY)
      return true;
   reason = "el simbolo no admite nuevas operaciones en esa direccion";
   return false;
}

//--- Regimen comun: 1 = permitido, 0 = esperar datos, -1 = bloqueado
int RegimeCheck(string &reason)
{
   if(InpRegime != KQ_REGIME_OFF)
   {
      double er = 0.0;
      if(!EfficiencyRatioD1(er))
      {
         reason = "Efficiency Ratio diario no disponible";
         return 0;
      }
      if(InpRegime == KQ_REGIME_TREND_ONLY && er < InpErThreshold)
      {
         reason = "regimen de rango (ER " + DoubleToString(er, 2) + " < " + DoubleToString(InpErThreshold, 2) + ")";
         return -1;
      }
      if(InpRegime == KQ_REGIME_RANGE_ONLY && er >= InpErThreshold)
      {
         reason = "regimen de tendencia (ER " + DoubleToString(er, 2) + " >= " + DoubleToString(InpErThreshold, 2) + ")";
         return -1;
      }
   }
   if(InpVolPctMax < 100.0)
   {
      double pct = 0.0;
      if(!AtrPercentileD1(pct))
      {
         reason = "percentil del ATR diario no disponible";
         return 0;
      }
      if(pct > InpVolPctMax)
      {
         reason = "volatilidad alta (percentil " + DoubleToString(pct, 0) + " > " + DoubleToString(InpVolPctMax, 0) + ")";
         return -1;
      }
   }
   return 1;
}

//--- Filtros de entrada: 1 = entrar, 0 = esperar dentro de la vela, -1 = descartar
int EntryGate(const int dir, const datetime now, string &reason)
{
   if(!g_lockOwned)
   {
      reason = "sin bloqueo de instancia";
      return -1;
   }
   if(SsGet("last_entry_bar", 0.0) == (double)g_pendingBar)
   {
      reason = "ya se abrio una operacion en esta vela";
      return -1;
   }
   if(!IsTradingDay(now))
   {
      reason = "dia no habilitado";
      return -1;
   }
   if(InRolloverWindow(now))
   {
      reason = "franja del rollover diario (spread ancho)";
      return 0;
   }
   if(g_ddLocked)
   {
      reason = "bloqueado por drawdown";
      return -1;
   }
   if(g_dayLocked)
   {
      reason = "bloqueado por perdida diaria";
      return -1;
   }
   if(!IsDirectionAllowed(dir))
   {
      reason = "direccion desactivada";
      return -1;
   }
   if(g_auto)
   {
      if(!TerminalInfoInteger(TERMINAL_CONNECTED))
      {
         reason = "terminal desconectado";
         return 0;
      }
      if(!IsTradingPermitted(dir, reason))
         return -1;
      if(g_closeDir != 0)
      {
         reason = "cerrando la posicion anterior";
         return 0;
      }
      if(CountOwnPositions(0) > 0)
      {
         reason = "ya hay una posicion abierta";
         return -1;
      }
      if(g_isNetting && PositionSelect(g_sym) && (ulong)PositionGetInteger(POSITION_MAGIC) != InpMagic)
      {
         reason = "netting: hay una posicion ajena en " + g_sym;
         return -1;
      }
   }
   else if(g_vDir != 0)
   {
      reason = "ya hay una posicion (virtual) abierta";
      return -1;
   }
   int regime = RegimeCheck(reason);
   if(regime <= 0)
      return regime;
   if(!IsTradeSessionOpen(now))
   {
      reason = "mercado cerrado (fuera de la sesion de trading)";
      return 0;
   }
   long spread = SymbolInfoInteger(g_sym, SYMBOL_SPREAD);
   if(InpMaxSpreadPoints > 0 && spread > InpMaxSpreadPoints)
   {
      reason = "spread alto (" + IntegerToString(spread) + " > " + IntegerToString(InpMaxSpreadPoints) + " puntos)";
      return 0;
   }
   return 1;
}

//+------------------------------------------------------------------+
//| 8. Riesgo: tamano de la posicion y limites                       |
//+------------------------------------------------------------------+
double RiskMoneyTarget()
{
   return AccountInfoDouble(ACCOUNT_BALANCE) * InpRiskPercent / 100.0;
}

//--- Perdida de 1 lote de la entrada al SL (divisa de la cuenta, con comision); -1 si no se puede calcular
double LossPerLotAtStop(const int dir, const double entry, const double sl)
{
   ENUM_ORDER_TYPE type = ORDER_TYPE_BUY;
   if(dir < 0)
      type = ORDER_TYPE_SELL;
   double profit = 0.0;
   if(!OrderCalcProfit(type, g_sym, 1.0, entry, sl, profit))
      return -1.0;
   if(profit >= 0.0)
      return -1.0;
   return -profit + InpCommissionPerLot;
}

//--- Lote por riesgo. Nunca redondea hacia arriba: si el minimo arriesga de mas, devuelve 0
double CalculateLots(const int dir, const double entry, const double sl, double &riskOfTrade, string &reason)
{
   riskOfTrade = 0.0;
   double lossPerLot = LossPerLotAtStop(dir, entry, sl);
   if(lossPerLot <= 0.0)
   {
      reason = "no se pudo calcular la perdida al stop (OrderCalcProfit)";
      return 0.0;
   }
   double riskMoney = RiskMoneyTarget();
   double lots      = NormalizeLots(riskMoney / lossPerLot);
   if(lots <= 0.0)
   {
      double minLot = SymbolInfoDouble(g_sym, SYMBOL_VOLUME_MIN);
      reason = "el lote minimo (" + DoubleToString(minLot, 2) + ") perderia " + DoubleToString(lossPerLot * minLot, 2) +
               " " + AccountInfoString(ACCOUNT_CURRENCY) + " en el stop, mas que el riesgo permitido (" +
               DoubleToString(riskMoney, 2) + ")";
      return 0.0;
   }
   riskOfTrade = lossPerLot * lots;
   return lots;
}

bool MarginAllows(const int dir, const double lots, const double price, string &reason)
{
   ENUM_ORDER_TYPE type = ORDER_TYPE_BUY;
   if(dir < 0)
      type = ORDER_TYPE_SELL;
   double margin = 0.0;
   if(!OrderCalcMargin(type, g_sym, lots, price, margin))
   {
      reason = "no se pudo calcular el margen";
      return false;
   }
   double allowed = AccountInfoDouble(ACCOUNT_MARGIN_FREE) * InpMaxMarginPercent / 100.0;
   if(margin > allowed)
   {
      reason = "margen " + DoubleToString(margin, 2) + " > permitido " + DoubleToString(allowed, 2);
      return false;
   }
   return true;
}

//--- Resultado cerrado de hoy de este EA (historial) + flotante
double TodayResult(const datetime now)
{
   double result = 0.0;
   if(HistorySelect(DayStart(now), (datetime)(now + 60)))
   {
      int total = HistoryDealsTotal();
      for(int i = 0; i < total; i++)
      {
         ulong deal = HistoryDealGetTicket(i);
         if(deal == 0)
            continue;
         if(HistoryDealGetString(deal, DEAL_SYMBOL) != g_sym || (ulong)HistoryDealGetInteger(deal, DEAL_MAGIC) != InpMagic)
            continue;
         result += HistoryDealGetDouble(deal, DEAL_PROFIT) + HistoryDealGetDouble(deal, DEAL_SWAP) +
                   HistoryDealGetDouble(deal, DEAL_COMMISSION);
      }
   }
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(g_pos.SelectByIndex(i) && IsOwnPosition())
         result += g_pos.Profit() + g_pos.Swap();
   }
   return result;
}

//+------------------------------------------------------------------+
//| 9. Ejecucion                                                     |
//+------------------------------------------------------------------+
void ConfigureFilling()
{
   long filling = SymbolInfoInteger(g_sym, SYMBOL_FILLING_MODE);
   if((filling & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK)
      g_trade.SetTypeFilling(ORDER_FILLING_FOK);
   else if((filling & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC)
      g_trade.SetTypeFilling(ORDER_FILLING_IOC);
   else
      g_trade.SetTypeFilling(ORDER_FILLING_RETURN);
}

//--- Segunda comprobacion independiente de g_auto: nunca se envian ordenes en cuentas reales
bool OrdersAllowedNow()
{
   if(!g_auto)
      return false;
   if(MQLInfoInteger(MQL_TESTER))
      return true;
   return (AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_DEMO && InpAllowDemoTrading);
}

//--- 1 = exito, 2 = reintentar ya (precio cambiado), 0 = reintentar mas tarde, -1 = descartar
int ClassifyRetcode(const uint rc)
{
   if(rc == TRADE_RETCODE_DONE || rc == TRADE_RETCODE_DONE_PARTIAL || rc == TRADE_RETCODE_PLACED)
      return 1;
   if(rc == TRADE_RETCODE_REQUOTE || rc == TRADE_RETCODE_PRICE_CHANGED || rc == TRADE_RETCODE_PRICE_OFF ||
      rc == TRADE_RETCODE_INVALID_PRICE)
      return 2;
   if(rc == 0 || rc == TRADE_RETCODE_TIMEOUT || rc == TRADE_RETCODE_CONNECTION || rc == TRADE_RETCODE_TOO_MANY_REQUESTS ||
      rc == TRADE_RETCODE_MARKET_CLOSED || rc == TRADE_RETCODE_REJECT || rc == TRADE_RETCODE_ERROR ||
      rc == TRADE_RETCODE_LOCKED || rc == TRADE_RETCODE_CANCEL)
      return 0;
   return -1;
}

//--- Orden a mercado con reintentos inmediatos ante recotizaciones
int SendMarket(const int dir, const double lots, const double sl, const double tp, double &requested, double &executed,
               ulong &order, uint &retcode, string &reason)
{
   if(!OrdersAllowedNow())
   {
      reason = "[SEGURIDAD] orden bloqueada: cuenta sin ejecucion automatica";
      return -1;
   }
   for(int k = 0; k < KQ_SEND_ATTEMPTS; k++)
   {
      MqlTick tick;
      if(!SymbolInfoTick(g_sym, tick) || tick.ask <= 0.0 || tick.bid <= 0.0)
      {
         reason = "sin precio actual";
         return 0;
      }
      requested = tick.bid;
      if(dir > 0)
         requested = tick.ask;
      bool sent = false;
      g_lastRequested = requested;
      if(dir > 0)
         sent = g_trade.Buy(lots, g_sym, requested, sl, tp, InpComment);
      else
         sent = g_trade.Sell(lots, g_sym, requested, sl, tp, InpComment);
      retcode  = g_trade.ResultRetcode();
      int kind = ClassifyRetcode(retcode);
      if(sent && kind == 1)
      {
         executed = g_trade.ResultPrice(); // 0 si el servidor no lo devuelve: el precio real se registra con el deal
         order    = g_trade.ResultOrder();
         return 1;
      }
      reason = "codigo " + IntegerToString((long)retcode) + ": " + g_trade.ResultRetcodeDescription();
      if(kind == 2)
         continue;
      return kind;
   }
   return 0;
}

bool ClosePositionTicket(const ulong ticket, const string why)
{
   if(!OrdersAllowedNow())
   {
      Print("[SEGURIDAD] Cierre bloqueado: cuenta sin ejecucion automatica");
      return false;
   }
   for(int k = 0; k < KQ_SEND_ATTEMPTS; k++)
   {
      if(g_trade.PositionClose(ticket) && ClassifyRetcode(g_trade.ResultRetcode()) == 1)
      {
         Print("[SALIDA] Posicion #", ticket, " cerrada: ", why);
         return true;
      }
      if(ClassifyRetcode(g_trade.ResultRetcode()) != 2)
         break;
   }
   Print("[ERROR] No se pudo cerrar la posicion #", ticket, " (", why, "). Codigo ", g_trade.ResultRetcode(), ": ",
         g_trade.ResultRetcodeDescription());
   return false;
}

//--- dirFilter: 0 = todas, 1 = compras, -1 = ventas
void CloseOwn(const int dirFilter, const string why)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(!g_pos.SelectByIndex(i) || !IsOwnPosition())
         continue;
      if(dirFilter != 0 && SelectedDir() != dirFilter)
         continue;
      ClosePositionTicket(g_pos.Ticket(), why);
   }
}

void CloseAllOwn(const string why)
{
   if(g_auto)
      CloseOwn(0, why);
}

//--- dir: 1 compras, -1 ventas, 2 todas
int OwnCountForClose(const int dir)
{
   if(dir == 2)
      return CountOwnPositions(0);
   return CountOwnPositions(dir);
}

void RequestClose(const int dir, const string why, const datetime now)
{
   if(!g_auto || OwnCountForClose(dir) == 0)
      return;
   g_closeDir   = dir;
   g_closeWhy   = why;
   g_closeRetry = now;
}

void ProcessCloseRequest(const datetime now)
{
   if(g_closeDir == 0 || now < g_closeRetry)
      return;
   int filter = g_closeDir;
   if(filter == 2)
      filter = 0;
   CloseOwn(filter, g_closeWhy);
   if(OwnCountForClose(g_closeDir) == 0)
   {
      g_closeDir = 0;
      g_closeWhy = "";
      return;
   }
   g_closeRetry = (datetime)(now + 10);
   JournalTrade("ERROR", 0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "cierre pendiente reintentado: " + g_closeWhy,
                g_trade.ResultRetcode());
}

bool ModifyStops(const ulong ticket, const int dir, const double newSl, const double tp, const string why)
{
   if(!OrdersAllowedNow())
      return false;
   MqlTick tick;
   if(!SymbolInfoTick(g_sym, tick))
      return false;
   if(!g_pos.SelectByTicket(ticket))
      return false;
   if(!OutsideFreezeLevel(dir, g_pos.StopLoss(), g_pos.TakeProfit(), tick))
      return false;
   if(g_trade.PositionModify(ticket, newSl, tp) && ClassifyRetcode(g_trade.ResultRetcode()) == 1)
   {
      Print("[GESTION] Posicion #", ticket, ": SL movido a ", Pr(newSl), " (", why, ")");
      JournalTrade("MODIFY", (long)ticket, (long)ticket, dir, g_pos.Volume(), 0.0, 0.0, newSl, tp, 0.0, 0.0, why,
                   g_trade.ResultRetcode());
      return true;
   }
   Print("[ERROR] No se pudo modificar la posicion #", ticket, ". Codigo ", g_trade.ResultRetcode(), ": ",
         g_trade.ResultRetcodeDescription());
   return false;
}

void StoreRisk(const long positionId, const double riskMoney)
{
   GlobalVariableSet(RiskGvName(positionId), riskMoney);
   int n = ArraySize(g_statPos);
   ArrayResize(g_statPos, n + 1);
   ArrayResize(g_statRisk, n + 1);
   g_statPos[n]  = positionId;
   g_statRisk[n] = riskMoney;
}

double LookupRisk(const long positionId)
{
   for(int i = ArraySize(g_statPos) - 1; i >= 0; i--)
   {
      if(g_statPos[i] == positionId)
         return g_statRisk[i];
   }
   string name = RiskGvName(positionId);
   if(GlobalVariableCheck(name))
      return GlobalVariableGet(name);
   return 0.0;
}

//--- Limites de perdida diaria y de drawdown (con estado persistente por cuenta, simbolo y magico)
void RiskUpdate(const datetime now)
{
   datetime day = DayStart(now);
   if(day != g_dayKey)
   {
      g_dayKey      = day;
      g_dayResult   = 0.0;
      g_lastDayCalc = 0;
      if(GvGet("day_key", 0.0) == (double)day)
         g_dayStartBalance = GvGet("day_bal", AccountInfoDouble(ACCOUNT_BALANCE));
      else
      {
         g_dayStartBalance = AccountInfoDouble(ACCOUNT_BALANCE);
         GvSet("day_key", (double)day);
         GvSet("day_bal", g_dayStartBalance);
      }
      g_dayLocked = (GvGet("day_lock", 0.0) == (double)day);
   }

   if(g_auto && (now - g_lastDayCalc >= 10 || now < g_lastDayCalc))
   {
      g_dayResult   = TodayResult(now);
      g_lastDayCalc = now;
   }
   if(InpMaxDailyLossPct > 0.0 && !g_dayLocked && g_dayStartBalance > 0.0 &&
      g_dayResult <= -g_dayStartBalance * InpMaxDailyLossPct / 100.0)
   {
      g_dayLocked = true;
      GvSet("day_lock", (double)day);
      Notify("[RIESGO] KQ5 " + g_sym + ": perdida diaria " + DoubleToString(g_dayResult, 2) +
             " alcanza el limite. Sin nuevas entradas hasta manana");
      if(InpCloseOnDailyLoss)
         CloseAllOwn("limite de perdida diaria");
   }

   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double peak   = GvGet("peak", equity);
   if(equity > peak)
   {
      peak = equity;
      GvSet("peak", peak);
   }
   g_ddNow = 0.0;
   if(peak > 0.0)
      g_ddNow = (peak - equity) / peak * 100.0;
   if(InpMaxDrawdownPct > 0.0 && !g_ddLocked && g_ddNow >= InpMaxDrawdownPct)
   {
      g_ddLocked = true;
      GvSet("dd_lock", 1.0);
      Notify("[RIESGO] KQ5 " + g_sym + ": drawdown " + DoubleToString(g_ddNow, 2) + "% >= " +
             DoubleToString(InpMaxDrawdownPct, 2) + "%. Se cierran las posiciones y se bloquean nuevas entradas");
      CloseAllOwn("limite de drawdown");
   }
}

//+------------------------------------------------------------------+
//| 10a. Modo senales: posicion virtual para ejecucion manual         |
//+------------------------------------------------------------------+
void DrawLine(const string name, const double price, const color clr)
{
   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, OBJ_HLINE, 0, 0, price);
   else
      ObjectMove(0, name, 0, 0, price);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_DASH);
}

void ClearVirtualLines()
{
   ObjectDelete(0, "KQ5_V_ENTRY");
   ObjectDelete(0, "KQ5_V_SL");
   ObjectDelete(0, "KQ5_V_TP");
}

void SaveVirtual()
{
   SsSet("v_dir", (double)g_vDir);
   SsSet("v_entry", g_vEntry);
   SsSet("v_sl", g_vSl);
   SsSet("v_tp", g_vTp);
   SsSet("v_lots", g_vLots);
   SsSet("v_risk", g_vRiskDist);
   SsSet("v_time", (double)g_vTime);
}

void LoadVirtual()
{
   g_vDir      = (int)SsGet("v_dir", 0.0);
   g_vEntry    = SsGet("v_entry", 0.0);
   g_vSl       = SsGet("v_sl", 0.0);
   g_vTp       = SsGet("v_tp", 0.0);
   g_vLots     = SsGet("v_lots", 0.0);
   g_vRiskDist = SsGet("v_risk", 0.0);
   g_vTime     = (datetime)SsGet("v_time", 0.0);
   if(g_vDir != 0)
   {
      DrawLine("KQ5_V_ENTRY", g_vEntry, clrDodgerBlue);
      DrawLine("KQ5_V_SL", g_vSl, clrRed);
      if(g_vTp > 0.0)
         DrawLine("KQ5_V_TP", g_vTp, clrLime);
      Print("[INICIO] Posicion virtual recuperada: ", DirName(g_vDir), " ", DoubleToString(g_vLots, 2), " a ", Pr(g_vEntry),
            " | SL ", Pr(g_vSl), " | TP ", Pr(g_vTp));
   }
}

void CloseVirtual(const string why, const double price)
{
   if(g_vDir == 0)
      return;
   double r = 0.0;
   if(g_vRiskDist > 0.0)
      r = (price - g_vEntry) * g_vDir / g_vRiskDist;
   Notify("KQ5 " + g_sym + ": CERRAR la " + DirName(g_vDir) + " de " + DoubleToString(g_vLots, 2) + " lotes (" + why +
          ") precio ~" + Pr(price) + " | resultado " + DoubleToString(r, 2) + " R");
   JournalTrade("VIRTUAL_EXIT", 0, 0, g_vDir, g_vLots, 0.0, price, g_vSl, g_vTp, 0.0, r, why, 0);
   g_vDir = 0;
   SaveVirtual();
   ClearVirtualLines();
}

//--- Cada tick: SL y TP de la posicion virtual
void ManageVirtual(const datetime now)
{
   if(g_vDir == 0)
      return;
   MqlTick tick;
   if(!SymbolInfoTick(g_sym, tick))
      return;
   if(g_vDir > 0)
   {
      if(tick.bid <= g_vSl)
         CloseVirtual("stop loss", tick.bid);
      else if(g_vTp > 0.0 && tick.bid >= g_vTp)
         CloseVirtual("take profit", tick.bid);
   }
   else
   {
      if(tick.ask >= g_vSl)
         CloseVirtual("stop loss", tick.ask);
      else if(g_vTp > 0.0 && tick.ask <= g_vTp)
         CloseVirtual("take profit", tick.ask);
   }
}

//+------------------------------------------------------------------+
//| 10b. Gestion de posiciones (modo automatico)                     |
//+------------------------------------------------------------------+
//--- Toda posicion del EA debe tener SL: si falta se pone (ATR x 2 de la temporalidad de senal) o se cierra
void EnsureStops()
{
   if(TimeCurrent() < g_exitRetryAfter)
      return;
   MqlTick tick;
   if(!SymbolInfoTick(g_sym, tick))
      return;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(!g_pos.SelectByIndex(i) || !IsOwnPosition() || g_pos.StopLoss() > 0.0)
         continue;
      ulong  ticket = g_pos.Ticket();
      int    dir    = SelectedDir();
      double atr    = 0.0;
      bool   fixed  = false;
      if(ReadBuffer(g_hAtrSig, 0, 1, atr) && atr > 0.0)
      {
         double sl    = NormalizePrice(g_pos.PriceOpen() - 2.0 * atr);
         bool   valid = (tick.bid - sl > MinStopDistance());
         if(dir < 0)
         {
            sl    = NormalizePrice(g_pos.PriceOpen() + 2.0 * atr);
            valid = (sl - tick.ask > MinStopDistance());
         }
         if(valid)
            fixed = ModifyStops(ticket, dir, sl, g_pos.TakeProfit(), "posicion sin SL");
      }
      if(!fixed)
      {
         Print("[RIESGO] La posicion #", ticket, " no tiene SL y no se pudo proteger: se cierra");
         if(!ClosePositionTicket(ticket, "sin SL"))
            g_exitRetryAfter = (datetime)(TimeCurrent() + 10);
      }
   }
}

//--- Maximo (compras) o minimo (ventas) de las velas CERRADAS desde la entrada
bool ExtremeSinceEntry(const datetime entryTime, const int dir, double &extreme)
{
   int shiftEntry = iBarShift(g_sym, g_signalTf, entryTime, false);
   if(shiftEntry < 1)
      return false;
   double values[];
   if(dir > 0)
   {
      if(CopyHigh(g_sym, g_signalTf, 1, shiftEntry, values) != shiftEntry)
         return false;
      extreme = values[ArrayMaximum(values)];
   }
   else
   {
      if(CopyLow(g_sym, g_signalTf, 1, shiftEntry, values) != shiftEntry)
         return false;
      extreme = values[ArrayMinimum(values)];
   }
   return true;
}

//--- H1: trailing chandelier (solo se estrecha)
void UpdateChandelier()
{
   if(InpTdTrailAtr <= 0.0)
      return;
   double atr = 0.0;
   if(!ReadBuffer(g_hAtrSig, 0, 1, atr) || atr <= 0.0)
      return;
   MqlTick tick;
   if(!SymbolInfoTick(g_sym, tick))
      return;
   double minDistance = MinStopDistance();

   if(!g_auto)
   {
      if(g_vDir == 0)
         return;
      double extreme = 0.0;
      if(!ExtremeSinceEntry(g_vTime, g_vDir, extreme))
         return;
      double candidate = NormalizePrice(extreme - g_vDir * InpTdTrailAtr * atr);
      if((g_vDir > 0 && candidate > g_vSl) || (g_vDir < 0 && candidate < g_vSl))
      {
         g_vSl = candidate;
         SsSet("v_sl", g_vSl);
         ObjectMove(0, "KQ5_V_SL", 0, 0, g_vSl);
         Notify("KQ5 " + g_sym + ": MOVER el SL de la " + DirName(g_vDir) + " a " + Pr(g_vSl) + " (trailing)");
      }
      return;
   }

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(!g_pos.SelectByIndex(i) || !IsOwnPosition())
         continue;
      int    dir       = SelectedDir();
      double extreme   = 0.0;
      if(!ExtremeSinceEntry(g_pos.Time(), dir, extreme))
         continue;
      double currentSl = g_pos.StopLoss();
      double candidate = NormalizePrice(extreme - dir * InpTdTrailAtr * atr);
      bool   better    = false;
      if(dir > 0)
         better = (candidate > currentSl + g_point * 0.5 && tick.bid - candidate > minDistance);
      else
         better = ((currentSl == 0.0 || candidate < currentSl - g_point * 0.5) && candidate - tick.ask > minDistance);
      if(better)
         ModifyStops(g_pos.Ticket(), dir, candidate, g_pos.TakeProfit(), "trailing chandelier");
   }
}

//--- H4: salida por RSI al cierre de la vela
void RsiExit()
{
   double rsi = 0.0;
   if(!ReadBuffer(g_hRsi, 0, 1, rsi))
      return;
   string text = "RSI " + DoubleToString(rsi, 1);
   if(!g_auto)
   {
      MqlTick tick;
      if(!SymbolInfoTick(g_sym, tick))
         return;
      if(g_vDir > 0 && rsi > InpMrExitBuy)
         CloseVirtual("salida por " + text, tick.bid);
      else if(g_vDir < 0 && rsi < InpMrExitSell)
         CloseVirtual("salida por " + text, tick.ask);
      return;
   }
   datetime now = TimeCurrent();
   if(rsi > InpMrExitBuy && CountOwnPositions(1) > 0)
      RequestClose(1, "salida por " + text, now);
   else if(rsi < InpMrExitSell && CountOwnPositions(-1) > 0)
      RequestClose(-1, "salida por " + text, now);
   ProcessCloseRequest(now);
}

//--- H3: hora UTC de salida correspondiente a una entrada (la primera posterior a la entrada)
datetime DriftExitUtc(const datetime entryServer)
{
   datetime entryUtc = ServerToUtc(entryServer);
   datetime exitUtc  = (datetime)(DayStart(entryUtc) + InpSdExitUtc * 3600);
   if(exitUtc <= entryUtc)
      exitUtc = (datetime)(exitUtc + 86400);
   return exitUtc;
}

//--- H3: salida por reloj en cada tick (y de seguridad si la posicion supera 24 h)
void DriftExitTick(const datetime now)
{
   if(now < g_exitRetryAfter)
      return;
   datetime utcNow = ServerToUtc(now);
   if(!g_auto)
   {
      if(g_vDir == 0)
         return;
      if(utcNow >= DriftExitUtc(g_vTime) || now - g_vTime > 86400)
      {
         MqlTick tick;
         if(!SymbolInfoTick(g_sym, tick))
            return;
         double price = tick.bid;
         if(g_vDir < 0)
            price = tick.ask;
         CloseVirtual("fin de la ventana horaria", price);
      }
      return;
   }
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(!g_pos.SelectByIndex(i) || !IsOwnPosition())
         continue;
      if(utcNow >= DriftExitUtc(g_pos.Time()) || now - g_pos.Time() > 86400)
      {
         if(!ClosePositionTicket(g_pos.Ticket(), "fin de la ventana horaria"))
            g_exitRetryAfter = (datetime)(now + 10);
      }
   }
}

//--- H2: cierre forzado a la hora UTC indicada o si la posicion es de un dia UTC anterior
void BreakoutFlat(const datetime now)
{
   if(now < g_exitRetryAfter)
      return;
   datetime utcNow = ServerToUtc(now);
   MqlDateTime u;
   TimeToStruct(utcNow, u);
   bool lateHour = (u.hour >= InpSbFlatUtc);
   if(!g_auto)
   {
      if(g_vDir == 0)
         return;
      if(lateHour || DayStart(ServerToUtc(g_vTime)) != DayStart(utcNow))
      {
         MqlTick tick;
         if(!SymbolInfoTick(g_sym, tick))
            return;
         double price = tick.bid;
         if(g_vDir < 0)
            price = tick.ask;
         CloseVirtual("cierre forzado de la sesion", price);
      }
      return;
   }
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(!g_pos.SelectByIndex(i) || !IsOwnPosition())
         continue;
      if(lateHour || DayStart(ServerToUtc(g_pos.Time())) != DayStart(utcNow))
      {
         if(!ClosePositionTicket(g_pos.Ticket(), "cierre forzado de la sesion"))
            g_exitRetryAfter = (datetime)(now + 10);
      }
   }
}

//--- Salidas que dependen del cierre de una vela de la temporalidad de senal
void ManageBarExits(const datetime now)
{
   if(InpStrategy == KQ_STRAT_TREND_DONCHIAN)
      UpdateChandelier();
   else if(InpStrategy == KQ_STRAT_MEANREV_RSI2)
      RsiExit();
   // H3 (estacionalidad) sale por reloj en cada tick: DriftExitTick
}

//+------------------------------------------------------------------+
//| 12. Orquestacion: senal -> seleccion -> riesgo -> ejecucion       |
//+------------------------------------------------------------------+
void ClearPending()
{
   g_hasPending = false;
   g_pendingBar = 0;
   g_attempts   = 0;
   g_waitWarned = false;
   g_retryAfter = 0;
}

void DiscardPending(const string reason)
{
   g_lastDecision = "descartada: " + reason;
   g_lastBlock    = reason;
   if(InpLogDiscards)
      Print("[DESCARTE] Senal de ", DirName(g_pending.dir), ": ", reason);
   JournalSignal(g_pending, "DISCARD", reason, 0.0, 0.0, 0.0, 0.0, 0.0);
   ClearPending();
}

//--- Precios de SL y TP de la senal a partir del precio de entrada
bool BuildStops(const KQSignal &sig, const double entry, double &sl, double &tp, string &reason)
{
   sl = sig.stopPrice;
   if(sl <= 0.0)
      sl = entry - sig.dir * sig.stopDistance;
   sl = NormalizePrice(sl);
   tp = 0.0;
   if(sig.targetDistance > 0.0)
      tp = NormalizePrice(entry + sig.dir * sig.targetDistance);
   if(sig.dir > 0 && sl >= entry)
   {
      reason = "el SL (" + Pr(sl) + ") no queda por debajo de la entrada";
      return false;
   }
   if(sig.dir < 0 && sl <= entry)
   {
      reason = "el SL (" + Pr(sl) + ") no queda por encima de la entrada";
      return false;
   }
   return true;
}

void ExecutePendingAuto(const datetime now)
{
   MqlTick tick;
   if(!SymbolInfoTick(g_sym, tick) || tick.ask <= 0.0 || tick.bid <= 0.0)
      return;
   int    dir    = g_pending.dir;
   double entry  = tick.bid;
   if(dir > 0)
      entry = tick.ask;
   double sl     = 0.0;
   double tp     = 0.0;
   string reason = "";
   if(!BuildStops(g_pending, entry, sl, tp, reason))
   {
      DiscardPending(reason);
      return;
   }
   double minDistance = MinStopDistance();
   bool   stopsOk     = true;
   if(dir > 0)
      stopsOk = (tick.bid - sl > minDistance && (tp == 0.0 || tp - tick.bid > minDistance));
   else
      stopsOk = (sl - tick.ask > minDistance && (tp == 0.0 || tick.ask - tp > minDistance));
   if(!stopsOk)
   {
      DiscardPending("SL/TP dentro de la distancia minima del broker");
      return;
   }
   double riskMoney = 0.0;
   double lots      = CalculateLots(dir, entry, sl, riskMoney, reason);
   if(lots <= 0.0)
   {
      DiscardPending(reason);
      return;
   }
   if(!MarginAllows(dir, lots, entry, reason))
   {
      DiscardPending(reason);
      return;
   }

   double requested = 0.0;
   double executed  = 0.0;
   ulong  order     = 0;
   uint   retcode   = 0;
   int    result    = SendMarket(dir, lots, sl, tp, requested, executed, order, retcode, reason);
   if(result == 1)
   {
      SsSet("last_entry_bar", (double)g_pendingBar);
      if(InpStrategy == KQ_STRAT_SESSION_BREAKOUT)
         SsSet("sb_day", (double)g_pending.dayKey);
      if(InpStrategy == KQ_STRAT_SESSION_DRIFT)
         SsSet("sd_day", (double)g_pending.dayKey);
      StoreRisk((long)order, riskMoney);
      g_lastDecision = "ejecutada: " + DirName(dir) + " " + DoubleToString(lots, 2) + " a " + Pr(executed);
      Print("[ENTRADA] ", DirName(dir), " ", DoubleToString(lots, 2), " lotes a ", Pr(executed), " (pedido ", Pr(requested),
            ") | SL ", Pr(sl), " | TP ", Pr(tp), " | riesgo ", DoubleToString(riskMoney, 2), " ",
            AccountInfoString(ACCOUNT_CURRENCY), " | ", g_pending.reason);
      JournalSignal(g_pending, "EXECUTED", "", requested, sl, tp, lots, riskMoney);
      JournalTrade("ENTRY", (long)order, (long)order, dir, lots, requested, executed, sl, tp, 0.0, 0.0, g_pending.reason, retcode);
      ClearPending();
      return;
   }
   if(result < 0)
   {
      JournalTrade("REJECTED", 0, 0, dir, lots, requested, 0.0, sl, tp, 0.0, 0.0, reason, retcode);
      DiscardPending(reason);
      return;
   }
   // Error temporal: mercado cerrado no gasta intentos; el resto si
   if(retcode == TRADE_RETCODE_MARKET_CLOSED)
   {
      g_retryAfter = (datetime)(now + 60);
      if(!g_waitWarned)
      {
         Print("[ESPERA] Mercado cerrado segun el servidor; se reintentara dentro de la vela");
         g_waitWarned = true;
      }
      return;
   }
   g_attempts++;
   g_retryAfter = (datetime)(now + 5);
   Print("[ERROR] Intento ", g_attempts, " de ", KQ_MAX_RETRIES, " fallido: ", reason);
   JournalTrade("ERROR", 0, 0, dir, lots, requested, 0.0, sl, tp, 0.0, 0.0, reason, retcode);
   if(g_attempts >= KQ_MAX_RETRIES)
      DiscardPending("tras " + IntegerToString(KQ_MAX_RETRIES) + " intentos: " + reason);
}

void ExecutePendingSignalOnly()
{
   MqlTick tick;
   if(!SymbolInfoTick(g_sym, tick) || tick.ask <= 0.0 || tick.bid <= 0.0)
      return;
   int    dir    = g_pending.dir;
   double entry  = tick.bid;
   if(dir > 0)
      entry = tick.ask;
   double sl     = 0.0;
   double tp     = 0.0;
   string reason = "";
   if(!BuildStops(g_pending, entry, sl, tp, reason))
   {
      DiscardPending(reason);
      return;
   }
   double riskMoney = 0.0;
   double lots      = CalculateLots(dir, entry, sl, riskMoney, reason);
   if(lots <= 0.0)
   {
      DiscardPending(reason);
      return;
   }
   g_vDir      = dir;
   g_vEntry    = entry;
   g_vSl       = sl;
   g_vTp       = tp;
   g_vLots     = lots;
   g_vRiskDist = MathAbs(entry - sl);
   g_vTime     = TimeCurrent();
   SaveVirtual();
   SsSet("last_entry_bar", (double)g_pendingBar);
   if(InpStrategy == KQ_STRAT_SESSION_BREAKOUT)
      SsSet("sb_day", (double)g_pending.dayKey);
   if(InpStrategy == KQ_STRAT_SESSION_DRIFT)
      SsSet("sd_day", (double)g_pending.dayKey);
   DrawLine("KQ5_V_ENTRY", entry, clrDodgerBlue);
   DrawLine("KQ5_V_SL", sl, clrRed);
   if(tp > 0.0)
      DrawLine("KQ5_V_TP", tp, clrLime);
   string tpText = "sin TP";
   if(tp > 0.0)
      tpText = "TP " + Pr(tp);
   Notify("KQ5 " + g_sym + ": SENAL " + DirName(dir) + " " + DoubleToString(lots, 2) + " lotes a ~" + Pr(entry) +
          " | SL " + Pr(sl) + " | " + tpText + " | riesgo " + DoubleToString(riskMoney, 2) + " " +
          AccountInfoString(ACCOUNT_CURRENCY) + " | " + g_pending.reason);
   g_lastDecision = "senal emitida (ejecucion manual)";
   JournalSignal(g_pending, "SIGNAL_ONLY", "", entry, sl, tp, lots, riskMoney);
   JournalTrade("VIRTUAL_ENTRY", 0, 0, dir, lots, entry, entry, sl, tp, 0.0, 0.0, g_pending.reason, 0);
   ClearPending();
}

void TryExecutePending(const datetime now)
{
   if(!g_hasPending)
      return;
   if(iTime(g_sym, g_signalTf, 0) != g_pendingBar)
   {
      DiscardPending("caducada: no se pudo ejecutar dentro de su vela");
      return;
   }
   if(now > g_pendingBar + (long)InpMaxEntryDelayMin * 60)
   {
      DiscardPending("demasiado tarde: mas de " + IntegerToString(InpMaxEntryDelayMin) + " min desde la apertura de la vela");
      return;
   }
   if(now < g_retryAfter)
      return;
   // Tras un error temporal el primer envio pudo ejecutarse igualmente: no se duplica
   if(g_auto && g_attempts > 0)
   {
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         if(g_pos.SelectByIndex(i) && IsOwnPosition() && g_pos.Time() >= g_pendingBar)
         {
            SsSet("last_entry_bar", (double)g_pendingBar);
            g_lastDecision = "ejecutada en un intento anterior (confirmada por la posicion abierta)";
            ClearPending();
            return;
         }
      }
   }
   string reason = "";
   int    gate   = EntryGate(g_pending.dir, now, reason);
   if(gate < 0)
   {
      DiscardPending(reason);
      return;
   }
   if(gate == 0)
   {
      g_lastBlock = reason;
      if(!g_waitWarned)
      {
         Print("[ESPERA] Senal de ", DirName(g_pending.dir), ": ", reason, ". Se espera dentro de la vela");
         g_waitWarned = true;
      }
      return;
   }
   if(g_auto)
      ExecutePendingAuto(now);
   else
      ExecutePendingSignalOnly();
}

//--- Nueva vela de la temporalidad de senal: salidas de vela, senal, cierre de la contraria y cola
void OnNewSignalBar(const datetime barTime, const datetime now)
{
   // Una senal pendiente de una vela anterior caduca (y queda registrada) antes de evaluar la nueva
   if(g_hasPending && g_pendingBar != barTime)
      DiscardPending("caducada: no se pudo ejecutar dentro de su vela");
   KQSignal sig;
   int ready = EvaluateStrategy(sig);
   if(ready == 0)
      return; // faltan datos: se reintenta en el siguiente tick
   g_lastBarSeen = barTime;
   SsSet("last_bar", (double)barTime);

   ManageBarExits(now);
   if(sig.dir == 0)
      return;

   g_lastSignal = DirName(sig.dir) + " - " + sig.reason + " (" + TimeToString(sig.barTime, TIME_DATE | TIME_MINUTES) + ")";
   Print("[SENAL] ", DirName(sig.dir), ": ", sig.reason);

   // La senal contraria cierra la exposicion abierta en la otra direccion
   int exposure = CurrentExposureDir();
   if(exposure == -sig.dir)
   {
      if(g_auto)
      {
         RequestClose(-sig.dir, "senal contraria", now);
         ProcessCloseRequest(now);
      }
      else
      {
         MqlTick tick;
         if(SymbolInfoTick(g_sym, tick))
         {
            double price = tick.bid;
            if(g_vDir < 0)
               price = tick.ask;
            CloseVirtual("senal contraria", price);
         }
      }
   }

   CopySignal(g_pending, sig);
   g_hasPending = true;
   g_pendingBar = barTime;
   g_attempts   = 0;
   g_waitWarned = false;
   g_retryAfter = 0;
   JournalSignal(sig, "SIGNAL", "", 0.0, 0.0, 0.0, 0.0, 0.0);
   // H2: un solo intento por dia UTC, contado cuando se emite la senal (igual que el motor Python)
   if(InpStrategy == KQ_STRAT_SESSION_BREAKOUT && sig.entryOk && IsDirectionAllowed(sig.dir))
      SsSet("sb_day", (double)sig.dayKey);
   if(!sig.entryOk)
      DiscardPending(sig.blockReason);
}

//+------------------------------------------------------------------+
//| Bloqueo de instancia (evita dos copias con el mismo magico)       |
//+------------------------------------------------------------------+
bool AcquireInstanceLock()
{
   if(MQLInfoInteger(MQL_TESTER))
   {
      g_lockOwned = true;
      return true;
   }
   string owner = GvName("inst");
   string beat  = GvName("inst_beat");
   if(!GlobalVariableCheck(owner))
      GlobalVariableTemp(owner); // valor 0; desaparece al cerrar el terminal
   double current = GlobalVariableGet(owner);
   bool   alive   = (current != 0.0 && current != g_token && GlobalVariableCheck(beat) &&
                     (double)TimeLocal() - GlobalVariableGet(beat) < 60.0);
   if(alive)
      return false;
   if(!GlobalVariableSetOnCondition(owner, g_token, current)) // comparacion y escritura atomicas
      return false;
   GlobalVariableSet(beat, (double)TimeLocal());
   g_lockOwned = true;
   return true;
}

void HeartbeatInstanceLock()
{
   if(!g_lockOwned || MQLInfoInteger(MQL_TESTER))
      return;
   if(!GlobalVariableSetOnCondition(GvName("inst"), g_token, g_token))
   {
      g_lockOwned = false;
      Print("[ERROR] Se perdio el bloqueo de instancia (hay otra copia con el mismo magico). El EA se detiene");
      ExpertRemove();
      return;
   }
   GlobalVariableSet(GvName("inst_beat"), (double)TimeLocal());
}

void ReleaseInstanceLock()
{
   if(!g_lockOwned || MQLInfoInteger(MQL_TESTER))
      return;
   if(GlobalVariableCheck(GvName("inst")) && GlobalVariableGet(GvName("inst")) == g_token)
   {
      GlobalVariableDel(GvName("inst"));
      GlobalVariableDel(GvName("inst_beat"));
   }
   g_lockOwned = false;
}

//+------------------------------------------------------------------+
//| Panel                                                            |
//+------------------------------------------------------------------+
void UpdatePanel(const datetime now)
{
   if(!InpShowPanel || now == g_lastPanel)
      return;
   g_lastPanel = now;
   if(MQLInfoInteger(MQL_TESTER) && !MQLInfoInteger(MQL_VISUAL_MODE))
      return;

   string regimeText = "ER n/d";
   double er         = 0.0;
   if(EfficiencyRatioD1(er))
   {
      regimeText = "ER " + DoubleToString(er, 2);
      if(er >= InpErThreshold)
         regimeText += " (tendencia)";
      else
         regimeText += " (rango)";
   }
   double pct = 0.0;
   if(AtrPercentileD1(pct))
      regimeText += " | ATR diario percentil " + DoubleToString(pct, 0);

   string position = "ninguna";
   if(g_auto)
   {
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         if(!g_pos.SelectByIndex(i) || !IsOwnPosition())
            continue;
         position = DirName(SelectedDir()) + " " + DoubleToString(g_pos.Volume(), 2) + " a " + Pr(g_pos.PriceOpen()) +
                    " | SL " + Pr(g_pos.StopLoss()) + " | TP " + Pr(g_pos.TakeProfit()) +
                    " | " + DoubleToString(g_pos.Profit() + g_pos.Swap(), 2);
         break;
      }
   }
   else if(g_vDir != 0)
      position = "VIRTUAL " + DirName(g_vDir) + " " + DoubleToString(g_vLots, 2) + " a " + Pr(g_vEntry) + " | SL " + Pr(g_vSl) +
                 " | TP " + Pr(g_vTp);

   string blocks = "ninguno";
   if(g_ddLocked)
      blocks = "DRAWDOWN (reiniciar con 'Reiniciar los bloqueos' = true)";
   else if(g_dayLocked)
      blocks = "PERDIDA DIARIA (hasta manana)";

   string text = "KatheQuant v" + KQ_VERSION + " | " + StrategyName() + " | " + g_sym + " senal " + TfName(g_signalTf) + "\n";
   text += "MODO: " + g_modeText + "\n";
   text += "Riesgo " + DoubleToString(InpRiskPercent, 2) + "% por operacion | perdida diaria max " +
           DoubleToString(InpMaxDailyLossPct, 1) + "% | DD max " + DoubleToString(InpMaxDrawdownPct, 1) +
           "% (ahora " + DoubleToString(g_ddNow, 2) + "%)\n";
   text += "Hoy (EA): " + DoubleToString(g_dayResult, 2) + " " + AccountInfoString(ACCOUNT_CURRENCY) + " | Bloqueos: " + blocks + "\n";
   text += "Regimen: " + regimeText + " | Spread " + IntegerToString((int)SymbolInfoInteger(g_sym, SYMBOL_SPREAD)) +
           " pts | Sesion abierta: " + YesNo(IsTradeSessionOpen(now)) + "\n";
   text += "Hora servidor " + TimeToString(now, TIME_MINUTES) + " | UTC " + TimeToString(ServerToUtc(now), TIME_MINUTES) + "\n";
   text += "Posicion: " + position + "\n";
   text += "Ultima senal: " + g_lastSignal + "\n";
   text += "Decision: " + g_lastDecision + " | Ultimo motivo de espera/descarte: " + g_lastBlock;
   Comment(text);
}

//+------------------------------------------------------------------+
//| Registro de salidas (modo automatico)                            |
//+------------------------------------------------------------------+
string DealReasonName(const long reason)
{
   if(reason == DEAL_REASON_SL)
      return "stop loss";
   if(reason == DEAL_REASON_TP)
      return "take profit";
   if(reason == DEAL_REASON_SO)
      return "stop out";
   if(reason == DEAL_REASON_EXPERT)
      return "EA";
   return "manual/otro";
}

double PositionNet(const long positionId, double &commission, double &swap)
{
   double profit = 0.0;
   commission = 0.0;
   swap       = 0.0;
   if(!HistorySelectByPosition(positionId))
      return 0.0;
   int total = HistoryDealsTotal();
   for(int i = 0; i < total; i++)
   {
      ulong deal = HistoryDealGetTicket(i);
      if(deal == 0)
         continue;
      profit     += HistoryDealGetDouble(deal, DEAL_PROFIT);
      swap       += HistoryDealGetDouble(deal, DEAL_SWAP);
      commission += HistoryDealGetDouble(deal, DEAL_COMMISSION);
   }
   return profit + swap + commission;
}

void OnTradeTransaction(const MqlTradeTransaction &trans, const MqlTradeRequest &request, const MqlTradeResult &result)
{
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD || trans.deal == 0)
      return;
   ulong deal = trans.deal;
   if(!HistoryDealSelect(deal))
      return;
   if(HistoryDealGetString(deal, DEAL_SYMBOL) != g_sym || (ulong)HistoryDealGetInteger(deal, DEAL_MAGIC) != InpMagic)
      return;
   long entry = HistoryDealGetInteger(deal, DEAL_ENTRY);
   if(entry == DEAL_ENTRY_IN)
   {
      int inDir = 1;
      if(HistoryDealGetInteger(deal, DEAL_TYPE) == DEAL_TYPE_SELL)
         inDir = -1;
      JournalTrade("FILL", (long)deal, HistoryDealGetInteger(deal, DEAL_POSITION_ID), inDir, HistoryDealGetDouble(deal, DEAL_VOLUME),
                   g_lastRequested, HistoryDealGetDouble(deal, DEAL_PRICE), HistoryDealGetDouble(deal, DEAL_SL),
                   HistoryDealGetDouble(deal, DEAL_TP), 0.0, 0.0, "ejecucion de la entrada", 0,
                   HistoryDealGetDouble(deal, DEAL_COMMISSION), 0.0);
      return;
   }
   if(entry != DEAL_ENTRY_OUT && entry != DEAL_ENTRY_OUT_BY && entry != DEAL_ENTRY_INOUT)
      return;
   long   positionId = HistoryDealGetInteger(deal, DEAL_POSITION_ID);
   long   reason     = HistoryDealGetInteger(deal, DEAL_REASON);
   double price      = HistoryDealGetDouble(deal, DEAL_PRICE);
   double volume     = HistoryDealGetDouble(deal, DEAL_VOLUME);
   double dealSl     = HistoryDealGetDouble(deal, DEAL_SL);
   double dealTp     = HistoryDealGetDouble(deal, DEAL_TP);
   double expected   = 0.0; // precio esperado de la salida: el nivel de SL o TP que la disparo
   if(reason == DEAL_REASON_SL)
      expected = dealSl;
   else if(reason == DEAL_REASON_TP)
      expected = dealTp;
   int    dir        = 1;
   if(HistoryDealGetInteger(deal, DEAL_TYPE) == DEAL_TYPE_BUY)
      dir = -1; // una compra cierra una venta
   double commission = 0.0;
   double swap       = 0.0;
   double net  = PositionNet(positionId, commission, swap);
   double risk = LookupRisk(positionId);
   double r    = 0.0;
   if(risk > 0.0)
      r = net / risk;
   Print("[SALIDA] Posicion #", positionId, " ", DealReasonName(reason), " a ", Pr(price), " | neto ", DoubleToString(net, 2),
         " | ", DoubleToString(r, 2), " R");
   // Deslizamiento de la salida: a favor de la posicion cerrada es positivo si se ejecuta peor que el nivel
   JournalTrade("EXIT", (long)deal, positionId, -dir, volume, expected, price, dealSl, dealTp, net, r, DealReasonName(reason), 0,
                commission, swap);
   if(!MQLInfoInteger(MQL_TESTER) && !PositionSelectByTicket((ulong)positionId))
   {
      string name = RiskGvName(positionId);
      if(GlobalVariableCheck(name))
         GlobalVariableDel(name);
   }
}

//+------------------------------------------------------------------+
//| Informe al final de la prueba (Diario del probador)              |
//+------------------------------------------------------------------+
double OnTester()
{
   if(!HistorySelect(0, (datetime)(TimeCurrent() + 86400)))
      return 0.0;
   long     ids[];
   double   nets[];
   double   vols[];
   int      dirs[];
   datetime exits[];
   int total = HistoryDealsTotal();
   for(int i = 0; i < total; i++)
   {
      ulong deal = HistoryDealGetTicket(i);
      if(deal == 0)
         continue;
      if(HistoryDealGetString(deal, DEAL_SYMBOL) != g_sym || (ulong)HistoryDealGetInteger(deal, DEAL_MAGIC) != InpMagic)
         continue;
      long id   = HistoryDealGetInteger(deal, DEAL_POSITION_ID);
      int  slot = -1;
      for(int j = ArraySize(ids) - 1; j >= 0; j--)
      {
         if(ids[j] == id)
         {
            slot = j;
            break;
         }
      }
      if(slot < 0)
      {
         slot = ArraySize(ids);
         ArrayResize(ids, slot + 1);
         ArrayResize(nets, slot + 1);
         ArrayResize(vols, slot + 1);
         ArrayResize(dirs, slot + 1);
         ArrayResize(exits, slot + 1);
         ids[slot]   = id;
         nets[slot]  = 0.0;
         vols[slot]  = 0.0;
         dirs[slot]  = 0;
         exits[slot] = 0;
      }
      nets[slot] += HistoryDealGetDouble(deal, DEAL_PROFIT) + HistoryDealGetDouble(deal, DEAL_SWAP) +
                    HistoryDealGetDouble(deal, DEAL_COMMISSION);
      long entry = HistoryDealGetInteger(deal, DEAL_ENTRY);
      if(entry == DEAL_ENTRY_IN)
      {
         vols[slot] += HistoryDealGetDouble(deal, DEAL_VOLUME);
         dirs[slot]  = 1;
         if(HistoryDealGetInteger(deal, DEAL_TYPE) == DEAL_TYPE_SELL)
            dirs[slot] = -1;
      }
      else
         exits[slot] = (datetime)HistoryDealGetInteger(deal, DEAL_TIME);
   }

   // Estadistica por operacion cerrada, en dinero y en R
   double tickValue = SymbolInfoDouble(g_sym, SYMBOL_TRADE_TICK_VALUE);
   double tickSize  = SymbolInfoDouble(g_sym, SYMBOL_TRADE_TICK_SIZE);
   double moneyPerPricePerLot = 0.0;
   if(tickSize > 0.0)
      moneyPerPricePerLot = tickValue / tickSize;

   int    n = 0, nR = 0, wins = 0, streak = 0, maxStreak = 0, nLong = 0, nShort = 0;
   double grossWin = 0.0, grossLoss = 0.0, sum = 0.0, sumR = 0.0, sumR2 = 0.0, best5 = 0.0, totalVol = 0.0;
   double sumLong = 0.0, sumShort = 0.0;
   double sorted[];
   int    years[];
   double yearSum[];
   int    yearCount[];
   for(int j = 0; j < ArraySize(ids); j++)
   {
      if(exits[j] == 0)
         continue;
      n++;
      sum += nets[j];
      if(nets[j] > 0.0)
      {
         wins++;
         grossWin += nets[j];
         streak = 0;
      }
      else if(nets[j] < 0.0)
      {
         grossLoss -= nets[j];
         streak++;
         if(streak > maxStreak)
            maxStreak = streak;
      }
      if(dirs[j] > 0)
      {
         nLong++;
         sumLong += nets[j];
      }
      else
      {
         nShort++;
         sumShort += nets[j];
      }
      totalVol += vols[j];
      double risk = LookupRisk(ids[j]);
      if(risk > 0.0)
      {
         double r = nets[j] / risk;
         nR++;
         sumR  += r;
         sumR2 += r * r;
      }
      int k = ArraySize(sorted);
      ArrayResize(sorted, k + 1);
      sorted[k] = nets[j];

      MqlDateTime dt;
      TimeToStruct(exits[j], dt);
      int ySlot = -1;
      for(int y = 0; y < ArraySize(years); y++)
      {
         if(years[y] == dt.year)
         {
            ySlot = y;
            break;
         }
      }
      if(ySlot < 0)
      {
         ySlot = ArraySize(years);
         ArrayResize(years, ySlot + 1);
         ArrayResize(yearSum, ySlot + 1);
         ArrayResize(yearCount, ySlot + 1);
         years[ySlot]     = dt.year;
         yearSum[ySlot]   = 0.0;
         yearCount[ySlot] = 0;
      }
      yearSum[ySlot] += nets[j];
      yearCount[ySlot]++;
   }
   if(n == 0)
   {
      Print("[RESULTADO] ", StrategyName(), ": sin operaciones cerradas");
      return 0.0;
   }
   ArraySort(sorted);
   for(int j = ArraySize(sorted) - 1; j >= 0 && j >= ArraySize(sorted) - 5; j--)
   {
      if(sorted[j] > 0.0)
         best5 += sorted[j];
   }
   double pf = 0.0;
   if(grossLoss > 0.0)
      pf = grossWin / grossLoss;
   double meanR = 0.0, sdR = 0.0, tR = 0.0;
   if(nR > 1)
   {
      meanR = sumR / nR;
      double variance = (sumR2 - nR * meanR * meanR) / (nR - 1);
      if(variance > 0.0)
         sdR = MathSqrt(variance);
      if(sdR > 0.0)
         tR = meanR / (sdR / MathSqrt((double)nR));
   }

   Print("[RESULTADO] ", StrategyName(), " | operaciones ", n, " | acierto ", DoubleToString(100.0 * wins / n, 1),
         "% | neto ", DoubleToString(sum, 2), " | PF ", DoubleToString(pf, 2), " | esperanza ", DoubleToString(sum / n, 2),
         " | DD equidad ", DoubleToString(TesterStatistics(STAT_EQUITY_DDREL_PERCENT), 2), "%");
   Print("[RESULTADO] En R: n = ", nR, " | media ", DoubleToString(meanR, 3), " R | desviacion ", DoubleToString(sdR, 3),
         " | t = ", DoubleToString(tR, 2), " | racha perdedora maxima ", maxStreak);
   double costUnit  = moneyPerPricePerLot * totalVol; // dinero por 1.00 de precio de coste extra en todas las operaciones
   double breakEven = 0.0;
   if(costUnit > 0.0)
      breakEven = sum / costUnit;
   Print("[RESULTADO] Compras ", nLong, " (", DoubleToString(sumLong, 2), ") | ventas ", nShort, " (", DoubleToString(sumShort, 2),
         ") | neto con coste extra de 0.10 / 0.20 / 0.40 por onza: ", DoubleToString(sum - 0.10 * costUnit, 2), " / ",
         DoubleToString(sum - 0.20 * costUnit, 2), " / ", DoubleToString(sum - 0.40 * costUnit, 2),
         " | coste de equilibrio ", DoubleToString(breakEven, 3), " por onza y operacion");
   string yearsText = "[RESULTADO] Por ano:";
   for(int y = 0; y < ArraySize(years); y++)
      yearsText += " " + IntegerToString(years[y]) + ": " + DoubleToString(yearSum[y], 2) + " (" + IntegerToString(yearCount[y]) + " op.)";
   Print(yearsText);
   if(sum > 0.0)
      Print("[RESULTADO] Las 5 mejores operaciones = ", DoubleToString(100.0 * best5 / sum, 1), "% del beneficio neto");

   if(nR < KQ_MIN_SCORE_N)
      return 0.0;
   return tR;
}

//+------------------------------------------------------------------+
//| Inicializacion                                                   |
//+------------------------------------------------------------------+
int InitError(const string message)
{
   Print("[ERROR] Parametros incorrectos: ", message);
   if(!MQLInfoInteger(MQL_TESTER))
      Alert("KatheQuant v5: ", message);
   return INIT_PARAMETERS_INCORRECT;
}

bool ValidHour(const int hour)
{
   return (hour >= 0 && hour <= 23);
}

int OnInit()
{
   g_sym    = _Symbol;
   g_point  = SymbolInfoDouble(g_sym, SYMBOL_POINT);
   g_digits = (int)SymbolInfoInteger(g_sym, SYMBOL_DIGITS);

   //--- Validacion
   if(InpStrategy == KQ_STRAT_NONE)
      return InitError("elige una estrategia en 'Estrategia activa' (o carga un archivo .set)");
   if(InpRiskPercent <= 0.0 || InpRiskPercent > 2.0)
      return InitError("el riesgo por operacion debe estar entre 0 y 2 %");
   if(InpMaxEntryDelayMin < 5)
      return InitError("el retraso maximo de entrada debe ser de al menos 5 minutos");
   if(InpMaxMarginPercent <= 0.0 || InpMaxMarginPercent > 100.0 || InpMaxDailyLossPct < 0.0 ||
      InpMaxDrawdownPct < 0.0 || InpMaxDrawdownPct > 100.0 || InpCommissionPerLot < 0.0)
      return InitError("limites de margen, perdida diaria, drawdown o comision fuera de rango");
   if(InpRolloverFromMin < 0 || InpRolloverFromMin > 1439 || InpRolloverToMin < 0 || InpRolloverToMin > 1439)
      return InitError("la franja del rollover debe estar entre 0 y 1439 minutos");
   if(InpAtrPeriod < 1 || InpErPeriod < 2 || InpErThreshold <= 0.0 || InpErThreshold >= 1.0 || InpVolPctMax <= 0.0)
      return InitError("parametros de ATR o de regimen fuera de rango");
   if(InpStrategy == KQ_STRAT_TREND_DONCHIAN && (InpTdChannel < 2 || InpTdSlAtr <= 0.0 || InpTdTrailAtr < 0.0))
      return InitError("tendencia: canal >= 2 y stop > 0");
   if(InpStrategy == KQ_STRAT_SESSION_BREAKOUT)
   {
      if(!ValidHour(InpSbRangeStartUtc) || !ValidHour(InpSbRangeEndUtc) || !ValidHour(InpSbEntryEndUtc) || !ValidHour(InpSbFlatUtc) ||
         InpSbRangeStartUtc >= InpSbRangeEndUtc || InpSbRangeEndUtc >= InpSbEntryEndUtc || InpSbEntryEndUtc > InpSbFlatUtc)
         return InitError("ruptura: se requiere inicio < fin del rango < fin de entradas <= cierre (horas UTC 0-23)");
      if(InpSbBufferFrac < 0.0 || InpSbTpMult < 0.0 || InpSbMaxRangeAtr < 0.0)
         return InitError("ruptura: margen, objetivo y compresion no pueden ser negativos");
   }
   if(InpStrategy == KQ_STRAT_SESSION_DRIFT && (!ValidHour(InpSdEntryUtc) || !ValidHour(InpSdExitUtc) ||
      InpSdEntryUtc == InpSdExitUtc || InpSdSlAtr <= 0.0))
      return InitError("estacionalidad: horas UTC 0-23 distintas y stop > 0");
   if(InpStrategy == KQ_STRAT_MEANREV_RSI2 && (InpMrRsiPeriod < 1 || InpMrBuyLevel >= InpMrSellLevel || InpMrSlAtr <= 0.0 ||
      InpMrTpAtr < 0.0 || InpMrEmaPeriod < 2))
      return InitError("reversion: niveles o stops incorrectos");
   if(InpStrategy == KQ_STRAT_REF_T0 && (InpT0Fast < 1 || InpT0Fast >= InpT0Slow || InpT0SlAtr <= 0.0 || InpT0TpAtr <= 0.0))
      return InitError("referencia T0: EMA rapida < lenta y stops > 0");

   //--- Temporalidad de senal
   g_signalTf = PERIOD_H1;
   if(InpStrategy == KQ_STRAT_TREND_DONCHIAN)
      g_signalTf = InpTdTimeframe;
   else if(InpStrategy == KQ_STRAT_SESSION_BREAKOUT)
      g_signalTf = PERIOD_M5;
   else if(InpStrategy == KQ_STRAT_SESSION_DRIFT)
      g_signalTf = PERIOD_H1;
   else if(InpStrategy == KQ_STRAT_MEANREV_RSI2)
      g_signalTf = InpMrTimeframe;
   else if(InpStrategy == KQ_STRAT_REF_T0)
      g_signalTf = InpT0Timeframe;
   if(g_signalTf == PERIOD_CURRENT)
      g_signalTf = (ENUM_TIMEFRAMES)Period();

   //--- Modo: automatico solo en el probador o en DEMO habilitada; real = solo senales
   long tradeMode = AccountInfoInteger(ACCOUNT_TRADE_MODE);
   if(MQLInfoInteger(MQL_TESTER))
   {
      g_auto     = true;
      g_modeText = "AUTOMATICO (probador)";
   }
   else if(tradeMode == ACCOUNT_TRADE_MODE_DEMO && InpAllowDemoTrading)
   {
      g_auto     = true;
      g_modeText = "AUTOMATICO en cuenta DEMO (habilitado)";
   }
   else
   {
      g_auto = false;
      if(tradeMode == ACCOUNT_TRADE_MODE_DEMO)
         g_modeText = "SOLO SENALES (DEMO sin habilitar: activa 'Permitir ejecucion automatica en una cuenta DEMO')";
      else
         g_modeText = "SOLO SENALES (cuenta REAL: el EA no envia ordenes; ejecucion manual)";
   }

   //--- En DEMO automatica los limites de riesgo son obligatorios
   if(g_auto && !MQLInfoInteger(MQL_TESTER) && (InpMaxDrawdownPct <= 0.0 || InpMaxDailyLossPct <= 0.0))
      return InitError("en DEMO automatica el drawdown maximo y la perdida diaria son obligatorios (usa KQ5_DEMO_plantilla.set)");

   g_isNetting = (AccountInfoInteger(ACCOUNT_MARGIN_MODE) != ACCOUNT_MARGIN_MODE_RETAIL_HEDGING);
   g_gv        = "KQ5_" + IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN)) + "_" + g_sym + "_" + IntegerToString((long)InpMagic) + "_";
   g_gvs       = g_gv + IntegerToString((int)InpStrategy) + "_" + TfName(g_signalTf) + "_";
   g_token     = (double)(ChartID() % 1000000000) + 1.0; // unico por grafico dentro del terminal

   //--- Probador: cada prueba empieza sin estado heredado; el diario se reescribe (y se desactiva al optimizar)
   g_journalOn = InpJournal;
   if(MQLInfoInteger(MQL_TESTER))
   {
      GlobalVariablesDeleteAll(g_gv);
      GlobalVariablesDeleteAll("KQ5R_" + IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN)) + "_");
      if(MQLInfoInteger(MQL_OPTIMIZATION))
         g_journalOn = false;
      else
      {
         FileDelete(JournalFile("senales"), FILE_COMMON);
         FileDelete(JournalFile("operaciones"), FILE_COMMON);
      }
   }

   if(!AcquireInstanceLock())
      return InitError("ya hay otra instancia con el mismo numero magico en " + g_sym + ". Quitala o cambia el magico");

   //--- Indicadores
   g_hAtrD1  = iATR(g_sym, PERIOD_D1, InpAtrPeriod);
   g_hAtrH1  = iATR(g_sym, PERIOD_H1, InpAtrPeriod);
   g_hAtrSig = iATR(g_sym, g_signalTf, InpAtrPeriod);
   if(g_hAtrD1 == INVALID_HANDLE || g_hAtrH1 == INVALID_HANDLE || g_hAtrSig == INVALID_HANDLE)
   {
      Print("[ERROR] No se pudo crear el ATR. Codigo ", GetLastError());
      return INIT_FAILED;
   }
   if(InpStrategy == KQ_STRAT_MEANREV_RSI2)
   {
      g_hRsi      = iRSI(g_sym, g_signalTf, InpMrRsiPeriod, PRICE_CLOSE);
      g_hEmaTrend = iMA(g_sym, g_signalTf, InpMrEmaPeriod, 0, MODE_EMA, PRICE_CLOSE);
      if(g_hRsi == INVALID_HANDLE || g_hEmaTrend == INVALID_HANDLE)
      {
         Print("[ERROR] No se pudieron crear el RSI o la EMA. Codigo ", GetLastError());
         return INIT_FAILED;
      }
   }
   if(InpStrategy == KQ_STRAT_REF_T0)
   {
      g_hEmaFast = iMA(g_sym, g_signalTf, InpT0Fast, 0, MODE_EMA, PRICE_CLOSE);
      g_hEmaSlow = iMA(g_sym, g_signalTf, InpT0Slow, 0, MODE_EMA, PRICE_CLOSE);
      g_hAdx     = iADX(g_sym, g_signalTf, 14);
      if(g_hEmaFast == INVALID_HANDLE || g_hEmaSlow == INVALID_HANDLE || g_hAdx == INVALID_HANDLE)
      {
         Print("[ERROR] No se pudieron crear las EMAs o el ADX. Codigo ", GetLastError());
         return INIT_FAILED;
      }
   }

   //--- Ejecucion
   g_trade.SetExpertMagicNumber(InpMagic);
   g_trade.SetDeviationInPoints((ulong)InpSlippagePoints);
   ConfigureFilling();

   //--- Estado persistente: bloqueos, ultima vela procesada y posicion virtual
   //--- El reinicio de bloqueos se aplica una sola vez por activacion (no en cada recarga del EA)
   bool doReset = InpResetLocks && (MQLInfoInteger(MQL_TESTER) || GvGet("reset_used", 0.0) == 0.0);
   if(doReset)
   {
      GvDel("dd_lock");
      GvDel("day_lock");
      GvSet("peak", AccountInfoDouble(ACCOUNT_EQUITY));
      if(!MQLInfoInteger(MQL_TESTER))
         GvSet("reset_used", 1.0);
      Print("[RIESGO] Bloqueos reiniciados. Nuevo maximo de equidad: ", DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2),
            ". Vuelve a poner 'Reiniciar los bloqueos' = false");
   }
   if(!InpResetLocks)
      GvDel("reset_used");
   g_ddLocked    = (GvGet("dd_lock", 0.0) > 0.0);
   g_lastBarSeen = (datetime)SsGet("last_bar", 0.0);
   ClearPending();
   if(!g_auto)
      LoadVirtual();
   if(g_ddLocked)
      Print("[RIESGO] El EA esta bloqueado por drawdown. Para reanudar, cargalo con 'Reiniciar los bloqueos' = true");

   EventSetTimer(5);

   string accountType = "hedging";
   if(g_isNetting)
      accountType = "netting (una sola posicion)";
   Print("[INICIO] KatheQuant v", KQ_VERSION, " | ", StrategyName(), " | ", g_sym, " | senal ", TfName(g_signalTf), " | ", g_modeText);
   Print("[INICIO] Cuenta ", accountType, " en ", AccountInfoString(ACCOUNT_CURRENCY), " | riesgo ", DoubleToString(InpRiskPercent, 2),
         "% | perdida diaria max ", DoubleToString(InpMaxDailyLossPct, 1), "% | DD max ", DoubleToString(InpMaxDrawdownPct, 1),
         "% | spread max ", InpMaxSpreadPoints, " pts | hora servidor ", TimeToString(TimeCurrent(), TIME_MINUTES),
         " = UTC ", TimeToString(ServerToUtc(TimeCurrent()), TIME_MINUTES));
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   ReleaseInstanceLock();
   if(g_hAtrSig != INVALID_HANDLE)
      IndicatorRelease(g_hAtrSig);
   if(g_hAtrD1 != INVALID_HANDLE)
      IndicatorRelease(g_hAtrD1);
   if(g_hAtrH1 != INVALID_HANDLE)
      IndicatorRelease(g_hAtrH1);
   if(g_hEmaFast != INVALID_HANDLE)
      IndicatorRelease(g_hEmaFast);
   if(g_hEmaSlow != INVALID_HANDLE)
      IndicatorRelease(g_hEmaSlow);
   if(g_hAdx != INVALID_HANDLE)
      IndicatorRelease(g_hAdx);
   if(g_hRsi != INVALID_HANDLE)
      IndicatorRelease(g_hRsi);
   if(g_hEmaTrend != INVALID_HANDLE)
      IndicatorRelease(g_hEmaTrend);
   Comment("");
}

void OnTimer()
{
   HeartbeatInstanceLock();
   datetime now = TimeCurrent();
   RiskUpdate(now);
   if(g_auto)
      ProcessCloseRequest(now);
   datetime local = TimeLocal();
   if(local - g_lastFlush >= 60)
   {
      FlushState();
      g_lastFlush = local;
   }
   //--- Las variables globales caducan a las 4 semanas sin acceso: se renuevan las del riesgo de las posiciones abiertas
   if(local - g_lastRiskRefresh >= 3600)
   {
      g_lastRiskRefresh = local;
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         if(!g_pos.SelectByIndex(i) || !IsOwnPosition())
            continue;
         string name = RiskGvName(g_pos.Identifier());
         if(GlobalVariableCheck(name))
            GlobalVariableSet(name, GlobalVariableGet(name));
      }
   }
   UpdatePanel(now);
}

void OnTick()
{
   datetime now = TimeCurrent();
   RiskUpdate(now);

   //--- 1) Gestion de lo abierto
   if(g_auto)
   {
      EnsureStops();
      ProcessCloseRequest(now);
   }
   else
      ManageVirtual(now);
   if(InpStrategy == KQ_STRAT_SESSION_BREAKOUT)
      BreakoutFlat(now);
   if(InpStrategy == KQ_STRAT_SESSION_DRIFT)
      DriftExitTick(now);

   //--- 2) Vela nueva de la temporalidad de senal
   datetime barTime = iTime(g_sym, g_signalTf, 0);
   if(barTime != 0 && barTime != g_lastBarSeen)
      OnNewSignalBar(barTime, now);

   //--- 3) Ejecucion de la senal pendiente (solo dentro de su vela)
   TryExecutePending(now);

   //--- 4) Panel
   UpdatePanel(now);
}
//+------------------------------------------------------------------+
