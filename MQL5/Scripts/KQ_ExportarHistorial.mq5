//+------------------------------------------------------------------+
//|                                          KQ_ExportarHistorial.mq5 |
//| Exporta velas (por defecto M1) con spread a CSV para el motor de  |
//| investigacion en Python. Solo lee: no opera.                      |
//| Salida: MQL5\Files\KQ_<SIMBOLO>_<TF>.csv                          |
//| Formato: time,open,high,low,close,tick_volume,spread,real_volume  |
//|   time = hora del servidor "YYYY.MM.DD HH:MM"; precios = BID;     |
//|   spread en puntos                                                |
//+------------------------------------------------------------------+
#property copyright   "Kathe"
#property version     "1.00"
#property description "Exporta el historial de velas con spread a CSV (solo lectura)."
#property script_show_inputs

input string          InpSymbols   = "XAUUSD";          // Simbolos (separados por comas)
input ENUM_TIMEFRAMES InpTimeframe = PERIOD_M1;         // Temporalidad
input datetime        InpFrom      = D'2000.01.01';     // Desde (se ajusta al primer dato disponible)
input datetime        InpTo        = 0;                 // Hasta (0 = ahora)
input int             InpRetries   = 20;                // Reintentos por tramo mientras se descarga el historial

string TfName(const ENUM_TIMEFRAMES tf)
{
   return StringSubstr(EnumToString(tf), 7);
}

//--- Primer dia del mes siguiente
datetime NextMonth(const datetime t)
{
   MqlDateTime dt;
   TimeToStruct(t, dt);
   dt.day  = 1;
   dt.hour = 0;
   dt.min  = 0;
   dt.sec  = 0;
   dt.mon++;
   if(dt.mon > 12)
   {
      dt.mon = 1;
      dt.year++;
   }
   return StructToTime(dt);
}

datetime MonthStart(const datetime t)
{
   MqlDateTime dt;
   TimeToStruct(t, dt);
   dt.day  = 1;
   dt.hour = 0;
   dt.min  = 0;
   dt.sec  = 0;
   return StructToTime(dt);
}

//--- Copia un tramo con reintentos (la primera peticion puede disparar la descarga)
int CopyChunk(const string symbol, const datetime from, const datetime to, MqlRates &rates[])
{
   int n = -1;
   for(int attempt = 0; attempt < InpRetries; attempt++)
   {
      ResetLastError();
      n = CopyRates(symbol, InpTimeframe, from, to, rates);
      if(n >= 0)
         return n;
      if(GetLastError() == 4401) // ERR_HISTORY_NOT_FOUND: no hay datos en ese tramo; no insistir
         return 0;
      Sleep(500);
   }
   return n;
}

void ExportSymbol(const string symbol)
{
   if(!SymbolSelect(symbol, true))
   {
      Print("[EXPORT] ", symbol, ": no existe en esta cuenta");
      return;
   }

   // La primera fecha puede tardar en conocerse mientras el terminal sincroniza con el servidor
   datetime serverFirst = 0;
   for(int attempt = 0; attempt < 20 && serverFirst <= 0; attempt++)
   {
      serverFirst = (datetime)SeriesInfoInteger(symbol, InpTimeframe, SERIES_SERVER_FIRSTDATE);
      if(serverFirst <= 0)
         serverFirst = (datetime)SeriesInfoInteger(symbol, InpTimeframe, SERIES_TERMINAL_FIRSTDATE);
      if(serverFirst <= 0)
         Sleep(500);
   }
   datetime start = InpFrom;
   if(serverFirst > start)
      start = serverFirst;
   // Hasta el final de la ultima vela cerrada (la vela en curso no se exporta)
   datetime stop = InpTo;
   if(stop <= 0)
      stop = iTime(symbol, InpTimeframe, 0) - 1;
   long neededBars = (long)((stop - start) / PeriodSeconds(InpTimeframe));
   if(TerminalInfoInteger(TERMINAL_MAXBARS) < neededBars)
      Print("[EXPORT] Aviso: 'Max. barras en ventana' (", TerminalInfoInteger(TERMINAL_MAXBARS),
            ") puede ser menor que las velas del periodo. Si la exportacion sale corta, ponlo en 'Unlimited' y reinicia MT5.");

   string fileName = "KQ_" + symbol + "_" + TfName(InpTimeframe) + ".csv";
   int    file     = FileOpen(fileName, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(file == INVALID_HANDLE)
   {
      Print("[EXPORT] No se pudo crear ", fileName, ". Error ", GetLastError());
      return;
   }
   FileWriteString(file, "time,open,high,low,close,tick_volume,spread,real_volume\r\n");

   int      digits    = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   long     rows      = 0;
   int      emptyMonths = 0;
   datetime firstBar  = 0;
   datetime lastBar   = 0;
   datetime lastWritten = 0;
   datetime monthFrom = MonthStart(start);

   Print("[EXPORT] ", symbol, " ", TfName(InpTimeframe), " desde ", TimeToString(start), " hasta ", TimeToString(stop),
         " | primera fecha en el servidor: ", TimeToString(serverFirst),
         " | max. barras en grafico: ", TerminalInfoInteger(TERMINAL_MAXBARS));

   while(monthFrom <= stop && !IsStopped())
   {
      datetime monthTo = NextMonth(monthFrom) - 1;
      if(monthTo > stop)
         monthTo = stop;

      MqlRates rates[];
      int      n = CopyChunk(symbol, monthFrom, monthTo, rates);
      if(n < 0)
      {
         Print("[EXPORT] ", symbol, " ", TimeToString(monthFrom, TIME_DATE), ": error ", GetLastError(), " (se omite el tramo)");
         emptyMonths++;
      }
      else if(n == 0)
         emptyMonths++;

      for(int i = 0; i < n; i++)
      {
         // CopyRates por fechas incluye los extremos: se evitan duplicados entre tramos
         if(rates[i].time <= lastWritten)
            continue;
         string line = TimeToString(rates[i].time, TIME_DATE | TIME_MINUTES) + "," +
                       DoubleToString(rates[i].open, digits) + "," +
                       DoubleToString(rates[i].high, digits) + "," +
                       DoubleToString(rates[i].low, digits) + "," +
                       DoubleToString(rates[i].close, digits) + "," +
                       IntegerToString(rates[i].tick_volume) + "," +
                       IntegerToString(rates[i].spread) + "," +
                       IntegerToString(rates[i].real_volume) + "\r\n";
         FileWriteString(file, line);
         lastWritten = rates[i].time;
         if(firstBar == 0)
            firstBar = rates[i].time;
         lastBar = rates[i].time;
         rows++;
      }
      if(n > 0)
         Print("[EXPORT] ", symbol, " ", TimeToString(monthFrom, TIME_DATE), ": ", n, " velas");
      monthFrom = NextMonth(monthFrom);
   }
   FileClose(file);

   Print("[EXPORT] ", symbol, " terminado: ", rows, " velas de ", TimeToString(firstBar), " a ", TimeToString(lastBar),
         " | tramos vacios o con error: ", emptyMonths, " | archivo MQL5\\Files\\", fileName);
   if(firstBar > start + 7 * 86400)
      Print("[EXPORT] Aviso: la primera vela exportada es posterior a la fecha pedida. Si el servidor tiene mas historial, ",
            "sube 'Max. barras en ventana' a 'Unlimited' (Herramientas > Opciones > Graficos), reinicia MT5 y repite.");
}

void OnStart()
{
   string symbols[];
   int    count = StringSplit(InpSymbols, ',', symbols);
   for(int i = 0; i < count; i++)
   {
      string symbol = symbols[i];
      StringTrimLeft(symbol);
      StringTrimRight(symbol);
      if(StringLen(symbol) == 0)
         continue;
      ExportSymbol(symbol);
   }
   Print("[EXPORT] Archivos en: Archivo > Abrir carpeta de datos > MQL5 > Files");
}
//+------------------------------------------------------------------+
