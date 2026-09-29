//+------------------------------------------------------------------+
//|                                           KQ_AuditoriaEntorno.mq5 |
//| Vuelca a archivos las especificaciones de la cuenta y de los      |
//| simbolos, las sesiones, la profundidad del historial, el spread   |
//| por hora y las comisiones cobradas. Solo lee: no opera.           |
//| Salida: MQL5\Files\KQ_auditoria_<cuenta>.txt,                     |
//|         MQL5\Files\KQ_<SIMBOLO>_spec.json,                        |
//|         MQL5\Files\KQ_<SIMBOLO>_spread_por_hora.csv               |
//+------------------------------------------------------------------+
#property copyright   "Kathe"
#property version     "1.00"
#property description "Auditoria del entorno de trading (solo lectura)."
#property script_show_inputs

input string InpSymbols     = "XAUUSD,XAUUSDc,XAUUSD247,XAUUSD247c"; // Simbolos (separados por comas)
input int    InpSpreadDays  = 60;   // Dias de velas M1 para el spread por hora
input int    InpTickDays    = 2;    // Dias de ticks para comparar el spread real
input int    InpDealsDays   = 365;  // Dias de historial de operaciones para las comisiones

int g_report = INVALID_HANDLE;

//+------------------------------------------------------------------+
//| Utilidades de salida                                             |
//+------------------------------------------------------------------+
void Out(const string text)
{
   Print(text);
   if(g_report != INVALID_HANDLE)
      FileWriteString(g_report, text + "\r\n");
}

string BoolText(const bool value)
{
   if(value)
      return "true";
   return "false";
}

string D(const double value, const int digits)
{
   return DoubleToString(value, digits);
}

string I(const long value)
{
   return IntegerToString(value);
}

string T(const datetime value)
{
   if(value <= 0)
      return "n/d";
   return TimeToString(value, TIME_DATE | TIME_MINUTES);
}

string JsonText(const string key, const string value)
{
   return "  \"" + key + "\": \"" + value + "\"";
}

string JsonNumber(const string key, const string value)
{
   return "  \"" + key + "\": " + value;
}

string TradeModeName(const long mode)
{
   if(mode == ACCOUNT_TRADE_MODE_DEMO)
      return "DEMO";
   if(mode == ACCOUNT_TRADE_MODE_CONTEST)
      return "CONTEST";
   return "REAL";
}

string MarginModeName(const long mode)
{
   if(mode == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING)
      return "HEDGING";
   if(mode == ACCOUNT_MARGIN_MODE_RETAIL_NETTING)
      return "NETTING";
   return "EXCHANGE";
}

string DayName(const int day)
{
   if(day == 0) return "domingo";
   if(day == 1) return "lunes";
   if(day == 2) return "martes";
   if(day == 3) return "miercoles";
   if(day == 4) return "jueves";
   if(day == 5) return "viernes";
   return "sabado";
}

string SecondsToHM(const long seconds)
{
   long h = seconds / 3600;
   long m = (seconds % 3600) / 60;
   return StringFormat("%02d:%02d", (int)h, (int)m);
}

//+------------------------------------------------------------------+
//| Cuenta, terminal y hora                                          |
//+------------------------------------------------------------------+
long ReportAccount()
{
   datetime serverTime = TimeTradeServer();
   datetime gmtTime    = TimeGMT();
   long     offset     = (long)(serverTime - gmtTime);
   // Redondeo a la media hora mas cercana
   offset = (long)(MathRound((double)offset / 1800.0) * 1800.0);

   Out("=== CUENTA ===");
   Out("login: " + I(AccountInfoInteger(ACCOUNT_LOGIN)));
   Out("servidor: " + AccountInfoString(ACCOUNT_SERVER));
   Out("empresa: " + AccountInfoString(ACCOUNT_COMPANY));
   Out("tipo: " + TradeModeName(AccountInfoInteger(ACCOUNT_TRADE_MODE)));
   Out("modo de margen: " + MarginModeName(AccountInfoInteger(ACCOUNT_MARGIN_MODE)));
   Out("divisa: " + AccountInfoString(ACCOUNT_CURRENCY));
   Out("apalancamiento: 1:" + I(AccountInfoInteger(ACCOUNT_LEVERAGE)));
   Out("balance: " + D(AccountInfoDouble(ACCOUNT_BALANCE), 2) + " | equidad: " + D(AccountInfoDouble(ACCOUNT_EQUITY), 2));
   Out("margin call: " + D(AccountInfoDouble(ACCOUNT_MARGIN_SO_CALL), 2) + " | stop out: " + D(AccountInfoDouble(ACCOUNT_MARGIN_SO_SO), 2) +
       " (modo " + I(AccountInfoInteger(ACCOUNT_MARGIN_SO_MODE)) + ": 0 = %, 1 = dinero)");
   Out("trading permitido: " + BoolText(AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) != 0) +
       " | asesores permitidos: " + BoolText(AccountInfoInteger(ACCOUNT_TRADE_EXPERT) != 0));
   Out("");
   Out("=== TERMINAL Y HORA ===");
   Out("build: " + I(TerminalInfoInteger(TERMINAL_BUILD)) + " | max. barras en grafico: " + I(TerminalInfoInteger(TERMINAL_MAXBARS)));
   Out("hora servidor: " + TimeToString(serverTime, TIME_DATE | TIME_SECONDS) +
       " | GMT: " + TimeToString(gmtTime, TIME_DATE | TIME_SECONDS) +
       " | local: " + TimeToString(TimeLocal(), TIME_DATE | TIME_SECONDS));
   Out("desfase servidor - GMT: " + I(offset) + " s (" + D((double)offset / 3600.0, 1) + " h)");
   Out("");
   return offset;
}

//+------------------------------------------------------------------+
//| Sesiones                                                         |
//+------------------------------------------------------------------+
void ReportSessions(const string symbol)
{
   Out("sesiones de trading (hora del servidor):");
   for(int day = 0; day < 7; day++)
   {
      string   line = "  " + DayName(day) + ":";
      datetime from = 0;
      datetime to   = 0;
      int      n    = 0;
      for(uint i = 0; i < 10; i++)
      {
         if(!SymbolInfoSessionTrade(symbol, (ENUM_DAY_OF_WEEK)day, i, from, to))
            break;
         line += " " + SecondsToHM((long)from) + "-" + SecondsToHM((long)to);
         n++;
      }
      if(n == 0)
         line += " cerrado";
      Out(line);
   }
}

//+------------------------------------------------------------------+
//| Profundidad del historial                                        |
//+------------------------------------------------------------------+
void ReportHistoryDepth(const string symbol, datetime &firstM1Server, datetime &firstM1Terminal)
{
   ENUM_TIMEFRAMES frames[] = {PERIOD_M1, PERIOD_M15, PERIOD_H1, PERIOD_H4, PERIOD_D1};
   string          names[]  = {"M1", "M15", "H1", "H4", "D1"};
   Out("historial (primera fecha en servidor / en terminal / barras disponibles):");
   for(int k = 0; k < ArraySize(frames); k++)
   {
      datetime serverFirst   = (datetime)SeriesInfoInteger(symbol, frames[k], SERIES_SERVER_FIRSTDATE);
      datetime terminalFirst = (datetime)SeriesInfoInteger(symbol, frames[k], SERIES_TERMINAL_FIRSTDATE);
      int      bars          = Bars(symbol, frames[k]);
      Out("  " + names[k] + ": " + T(serverFirst) + " / " + T(terminalFirst) + " / " + IntegerToString(bars));
      if(k == 0)
      {
         firstM1Server   = serverFirst;
         firstM1Terminal = terminalFirst;
      }
   }
}

//+------------------------------------------------------------------+
//| Spread por hora desde velas M1 y desde ticks                     |
//+------------------------------------------------------------------+
void SpreadByHour(const string symbol, double &avgM1[], double &p50M1[], double &p90M1[], double &avgTicks[])
{
   ArrayResize(avgM1, 24);
   ArrayResize(p50M1, 24);
   ArrayResize(p90M1, 24);
   ArrayResize(avgTicks, 24);
   ArrayInitialize(avgM1, 0.0);
   ArrayInitialize(p50M1, 0.0);
   ArrayInitialize(p90M1, 0.0);
   ArrayInitialize(avgTicks, 0.0);

   MqlRates rates[];
   datetime to   = TimeCurrent();
   datetime from = (datetime)(to - (long)InpSpreadDays * 86400);
   int      n    = CopyRates(symbol, PERIOD_M1, from, to, rates);
   if(n <= 0)
      Out("  (sin velas M1 para el spread; error " + IntegerToString(GetLastError()) + ")");

   for(int h = 0; h < 24 && n > 0; h++)
   {
      double values[];
      int    count = 0;
      ArrayResize(values, n);
      for(int i = 0; i < n; i++)
      {
         MqlDateTime dt;
         TimeToStruct(rates[i].time, dt);
         if(dt.hour != h)
            continue;
         values[count] = (double)rates[i].spread;
         count++;
      }
      if(count == 0)
         continue;
      ArrayResize(values, count);
      ArraySort(values);
      double sum = 0.0;
      for(int j = 0; j < count; j++)
         sum += values[j];
      avgM1[h] = sum / count;
      p50M1[h] = values[count / 2];
      p90M1[h] = values[(int)MathMin(count - 1, (int)MathFloor(count * 0.9))];
   }

   // Spread real de los ticks recientes (para ver que significa el campo spread de las velas)
   MqlTick ticks[];
   ulong   toMsc   = (ulong)TimeCurrent() * 1000;
   ulong   fromMsc = toMsc - (ulong)InpTickDays * 86400 * 1000;
   int     nt      = CopyTicksRange(symbol, ticks, COPY_TICKS_INFO, fromMsc, toMsc);
   double  point   = SymbolInfoDouble(symbol, SYMBOL_POINT);
   if(nt <= 0 || point <= 0.0)
   {
      Out("  (sin ticks recientes; error " + IntegerToString(GetLastError()) + ")");
      return;
   }
   double sums[];
   int    counts[];
   ArrayResize(sums, 24);
   ArrayResize(counts, 24);
   ArrayInitialize(sums, 0.0);
   ArrayInitialize(counts, 0);
   for(int i = 0; i < nt; i++)
   {
      if(ticks[i].bid <= 0.0 || ticks[i].ask <= 0.0)
         continue;
      MqlDateTime dt;
      TimeToStruct(ticks[i].time, dt);
      sums[dt.hour] += (ticks[i].ask - ticks[i].bid) / point;
      counts[dt.hour]++;
   }
   for(int h = 0; h < 24; h++)
   {
      if(counts[h] > 0)
         avgTicks[h] = sums[h] / counts[h];
   }
   Out("  ticks analizados: " + IntegerToString(nt));
}

//+------------------------------------------------------------------+
//| Comisiones, swaps y tarifas cobradas en el historial             |
//+------------------------------------------------------------------+
void ReportCosts(const string symbol, double &commissionPerLotSide)
{
   commissionPerLotSide = 0.0;
   datetime to   = TimeCurrent();
   datetime from = (datetime)(to - (long)InpDealsDays * 86400);
   if(!HistorySelect(from, to))
   {
      Out("  (no se pudo leer el historial de operaciones)");
      return;
   }
   int    deals      = 0;
   double volume     = 0.0;
   double commission = 0.0;
   double swap       = 0.0;
   double fee        = 0.0;
   int    total      = HistoryDealsTotal();
   for(int i = 0; i < total; i++)
   {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0)
         continue;
      if(HistoryDealGetString(ticket, DEAL_SYMBOL) != symbol)
         continue;
      long type = HistoryDealGetInteger(ticket, DEAL_TYPE);
      if(type != DEAL_TYPE_BUY && type != DEAL_TYPE_SELL)
         continue;
      deals++;
      volume     += HistoryDealGetDouble(ticket, DEAL_VOLUME);
      commission += HistoryDealGetDouble(ticket, DEAL_COMMISSION);
      swap       += HistoryDealGetDouble(ticket, DEAL_SWAP);
      fee        += HistoryDealGetDouble(ticket, DEAL_FEE);
   }
   if(volume > 0.0)
      commissionPerLotSide = commission / volume;
   Out("costes cobrados en " + IntegerToString(InpDealsDays) + " dias: deals " + IntegerToString(deals) +
       " | volumen " + D(volume, 2) + " lotes | comision " + D(commission, 2) +
       " | swap " + D(swap, 2) + " | tarifas " + D(fee, 2) +
       " | comision por lote y lado " + D(commissionPerLotSide, 4));
}

//+------------------------------------------------------------------+
//| Especificacion de un simbolo                                     |
//+------------------------------------------------------------------+
void AuditSymbol(const string symbol, const long gmtOffset)
{
   if(!SymbolSelect(symbol, true))
   {
      Out("=== " + symbol + ": no existe en esta cuenta ===");
      Out("");
      return;
   }
   Sleep(300);
   MqlTick tick;
   bool    hasTick = SymbolInfoTick(symbol, tick);

   int    digits       = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   double point        = SymbolInfoDouble(symbol, SYMBOL_POINT);
   double tickSize     = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE);
   double tickValue    = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE);
   double contractSize = SymbolInfoDouble(symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   double volMin       = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   double volMax       = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   double volStep      = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);
   long   stopsLevel   = SymbolInfoInteger(symbol, SYMBOL_TRADE_STOPS_LEVEL);
   long   freezeLevel  = SymbolInfoInteger(symbol, SYMBOL_TRADE_FREEZE_LEVEL);
   long   spreadNow    = SymbolInfoInteger(symbol, SYMBOL_SPREAD);
   bool   spreadFloat  = (SymbolInfoInteger(symbol, SYMBOL_SPREAD_FLOAT) != 0);
   long   swapMode     = SymbolInfoInteger(symbol, SYMBOL_SWAP_MODE);
   double swapLong     = SymbolInfoDouble(symbol, SYMBOL_SWAP_LONG);
   double swapShort    = SymbolInfoDouble(symbol, SYMBOL_SWAP_SHORT);
   long   swap3Days    = SymbolInfoInteger(symbol, SYMBOL_SWAP_ROLLOVER3DAYS);
   long   tradeMode    = SymbolInfoInteger(symbol, SYMBOL_TRADE_MODE);
   long   exeMode      = SymbolInfoInteger(symbol, SYMBOL_TRADE_EXEMODE);
   long   fillMode     = SymbolInfoInteger(symbol, SYMBOL_FILLING_MODE);

   double price          = 0.0;
   double moneyPerUnit   = 0.0; // dinero por 1.00 de movimiento del precio con 1 lote
   double marginMinLot   = 0.0;
   double marginOneLot   = 0.0;
   if(hasTick)
   {
      price = tick.ask;
      double profit = 0.0;
      if(OrderCalcProfit(ORDER_TYPE_BUY, symbol, 1.0, price, price + 1.0, profit))
         moneyPerUnit = profit;
      double margin = 0.0;
      if(OrderCalcMargin(ORDER_TYPE_BUY, symbol, volMin, price, margin))
         marginMinLot = margin;
      if(OrderCalcMargin(ORDER_TYPE_BUY, symbol, 1.0, price, margin))
         marginOneLot = margin;
   }

   Out("=== " + symbol + " ===");
   Out("descripcion: " + SymbolInfoString(symbol, SYMBOL_DESCRIPTION) + " | ruta: " + SymbolInfoString(symbol, SYMBOL_PATH));
   Out("divisas base/beneficio/margen: " + SymbolInfoString(symbol, SYMBOL_CURRENCY_BASE) + " / " +
       SymbolInfoString(symbol, SYMBOL_CURRENCY_PROFIT) + " / " + SymbolInfoString(symbol, SYMBOL_CURRENCY_MARGIN));
   Out("digitos: " + IntegerToString(digits) + " | point: " + D(point, 8) + " | tick size: " + D(tickSize, 8) +
       " | tick value: " + D(tickValue, 8) + " | contrato: " + D(contractSize, 4));
   Out("dinero por 1.00 de precio y 1 lote (OrderCalcProfit): " + D(moneyPerUnit, 4) + " " + AccountInfoString(ACCOUNT_CURRENCY));
   Out("volumen min/max/paso: " + D(volMin, 4) + " / " + D(volMax, 2) + " / " + D(volStep, 4));
   Out("margen para el lote minimo: " + D(marginMinLot, 2) + " | para 1 lote: " + D(marginOneLot, 2) + " (precio " + D(price, digits) + ")");
   Out("stops level: " + I(stopsLevel) + " | freeze level: " + I(freezeLevel) + " puntos");
   Out("spread actual: " + I(spreadNow) + " puntos | flotante: " + BoolText(spreadFloat));
   Out("swap modo " + I(swapMode) + " | largo " + D(swapLong, 4) + " | corto " + D(swapShort, 4) + " | triple el dia " + I(swap3Days));
   Out("modo de trading " + I(tradeMode) + " | ejecucion " + I(exeMode) + " | llenado " + I(fillMode));
   ReportSessions(symbol);

   datetime firstM1Server   = 0;
   datetime firstM1Terminal = 0;
   ReportHistoryDepth(symbol, firstM1Server, firstM1Terminal);

   double avgM1[];
   double p50M1[];
   double p90M1[];
   double avgTicks[];
   SpreadByHour(symbol, avgM1, p50M1, p90M1, avgTicks);

   double commissionPerLotSide = 0.0;
   ReportCosts(symbol, commissionPerLotSide);
   Out("");

   // CSV del spread por hora
   string csvName = "KQ_" + symbol + "_spread_por_hora.csv";
   int    csv     = FileOpen(csvName, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(csv != INVALID_HANDLE)
   {
      FileWriteString(csv, "hora_servidor,spread_m1_media,spread_m1_p50,spread_m1_p90,spread_ticks_media\r\n");
      for(int h = 0; h < 24; h++)
         FileWriteString(csv, IntegerToString(h) + "," + D(avgM1[h], 2) + "," + D(p50M1[h], 2) + "," +
                              D(p90M1[h], 2) + "," + D(avgTicks[h], 2) + "\r\n");
      FileClose(csv);
   }

   // JSON para el motor de investigacion
   string jsonName = "KQ_" + symbol + "_spec.json";
   int    json     = FileOpen(jsonName, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(json == INVALID_HANDLE)
   {
      Out("no se pudo crear " + jsonName);
      return;
   }
   string spreads = "";
   for(int h = 0; h < 24; h++)
   {
      if(h > 0)
         spreads += ", ";
      spreads += D(avgM1[h], 2);
   }
   FileWriteString(json, "{\r\n");
   FileWriteString(json, JsonText("symbol", symbol) + ",\r\n");
   FileWriteString(json, JsonText("server", AccountInfoString(ACCOUNT_SERVER)) + ",\r\n");
   FileWriteString(json, JsonText("account_currency", AccountInfoString(ACCOUNT_CURRENCY)) + ",\r\n");
   FileWriteString(json, JsonText("account_trade_mode", TradeModeName(AccountInfoInteger(ACCOUNT_TRADE_MODE))) + ",\r\n");
   FileWriteString(json, JsonText("account_margin_mode", MarginModeName(AccountInfoInteger(ACCOUNT_MARGIN_MODE))) + ",\r\n");
   FileWriteString(json, JsonNumber("account_leverage", I(AccountInfoInteger(ACCOUNT_LEVERAGE))) + ",\r\n");
   FileWriteString(json, JsonText("currency_profit", SymbolInfoString(symbol, SYMBOL_CURRENCY_PROFIT)) + ",\r\n");
   FileWriteString(json, JsonNumber("digits", IntegerToString(digits)) + ",\r\n");
   FileWriteString(json, JsonNumber("point", D(point, 8)) + ",\r\n");
   FileWriteString(json, JsonNumber("tick_size", D(tickSize, 8)) + ",\r\n");
   FileWriteString(json, JsonNumber("tick_value", D(tickValue, 8)) + ",\r\n");
   FileWriteString(json, JsonNumber("contract_size", D(contractSize, 4)) + ",\r\n");
   FileWriteString(json, JsonNumber("money_per_price_unit_per_lot", D(moneyPerUnit, 6)) + ",\r\n");
   FileWriteString(json, JsonNumber("volume_min", D(volMin, 4)) + ",\r\n");
   FileWriteString(json, JsonNumber("volume_max", D(volMax, 4)) + ",\r\n");
   FileWriteString(json, JsonNumber("volume_step", D(volStep, 4)) + ",\r\n");
   FileWriteString(json, JsonNumber("margin_min_lot", D(marginMinLot, 4)) + ",\r\n");
   FileWriteString(json, JsonNumber("stops_level", I(stopsLevel)) + ",\r\n");
   FileWriteString(json, JsonNumber("freeze_level", I(freezeLevel)) + ",\r\n");
   FileWriteString(json, JsonNumber("swap_mode", I(swapMode)) + ",\r\n");
   FileWriteString(json, JsonNumber("swap_long", D(swapLong, 6)) + ",\r\n");
   FileWriteString(json, JsonNumber("swap_short", D(swapShort, 6)) + ",\r\n");
   FileWriteString(json, JsonNumber("swap_3days", I(swap3Days)) + ",\r\n");
   FileWriteString(json, JsonNumber("commission_per_lot_side_observed", D(commissionPerLotSide, 6)) + ",\r\n");
   FileWriteString(json, JsonNumber("gmt_offset_seconds", I(gmtOffset)) + ",\r\n");
   FileWriteString(json, JsonText("first_date_m1_server", T(firstM1Server)) + ",\r\n");
   FileWriteString(json, JsonText("first_date_m1_terminal", T(firstM1Terminal)) + ",\r\n");
   FileWriteString(json, JsonText("export_time_server", T(TimeTradeServer())) + ",\r\n");
   FileWriteString(json, "  \"avg_spread_points_m1_by_server_hour\": [" + spreads + "]\r\n");
   FileWriteString(json, "}\r\n");
   FileClose(json);
}

//+------------------------------------------------------------------+
//| Programa                                                         |
//+------------------------------------------------------------------+
void OnStart()
{
   string reportName = "KQ_auditoria_" + IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN)) + ".txt";
   g_report = FileOpen(reportName, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(g_report == INVALID_HANDLE)
      Print("No se pudo crear ", reportName, ". Error ", GetLastError(), ". Se escribe solo en el registro.");

   long gmtOffset = ReportAccount();

   string symbols[];
   int    count = StringSplit(InpSymbols, ',', symbols);
   for(int i = 0; i < count; i++)
   {
      string symbol = symbols[i];
      StringTrimLeft(symbol);
      StringTrimRight(symbol);
      if(StringLen(symbol) == 0)
         continue;
      AuditSymbol(symbol, gmtOffset);
   }

   Out("Archivos en: Archivo > Abrir carpeta de datos > MQL5 > Files");
   if(g_report != INVALID_HANDLE)
      FileClose(g_report);
   Print("Auditoria terminada: ", reportName);
}
//+------------------------------------------------------------------+
