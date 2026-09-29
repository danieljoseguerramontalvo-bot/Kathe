// mql5_shim.hpp - declaraciones (no implementaciones) del lenguaje y la API de MQL5
// para el comprobador estático mql5check.py.
//
// Este archivo NO es MQL5: es C++17 que imita la semántica de MQL5 lo bastante como
// para que `g++ -std=c++17 -fsyntax-only` detecte los errores de compilación típicos
// (identificadores no declarados, número o tipo de argumentos incorrectos, etc.).
// Solo contiene declaraciones; nada se enlaza ni se ejecuta.
//
// Convenciones:
//   * Los nombres internos empiezan por `mql_` para no chocar con el código del usuario.
//   * No se incluye ninguna cabecera de C (<string>, <cmath>...) para no introducir en el
//     espacio de nombres global identificadores como `time`, `signal` o `rand`.
//   * Lo que en MQL5 compila con ADVERTENCIA se marca con [[deprecated("MQL5: ...")]]:
//     g++ lo informa como warning en la línea del usuario y el script lo muestra así.
//   * La parte de la Biblioteca Estándar (CTrade, CPositionInfo...) solo se declara si el
//     programa hizo el #include correspondiente (el traductor define MQL5CHECK_INC_*).
#ifndef MQL5CHECK_SHIM_CORE
#define MQL5CHECK_SHIM_CORE
#pragma GCC system_header

#include <initializer_list>
#include <type_traits>

static_assert(sizeof(long) == 8, "mql5check necesita una plataforma LP64 (long de 64 bits, como en MQL5)");

//====================================================================
// Tipos básicos
//====================================================================
typedef unsigned char  uchar;
typedef unsigned short ushort;
typedef unsigned int   uint;
typedef unsigned long  ulong;
// char, short, int, long (64 bits en LP64, igual que en MQL5), bool, float, double: nativos.

class string;
class datetime;
class color;
struct mql_null_t;

template<class T> struct mql_is_datetime : std::false_type {};
template<> struct mql_is_datetime<datetime> : std::true_type {};
template<class T> struct mql_is_color : std::false_type {};
template<> struct mql_is_color<color> : std::true_type {};

// "Numérico" en el sentido de MQL5: aritmético, enum, datetime o color.
template<class T> struct mql_numlike : std::integral_constant<bool,
    std::is_arithmetic<T>::value || std::is_enum<T>::value ||
    mql_is_datetime<T>::value || mql_is_color<T>::value> {};
template<class T> struct mql_numlike_noenum : std::integral_constant<bool,
    std::is_arithmetic<T>::value || mql_is_datetime<T>::value || mql_is_color<T>::value> {};
template<class T> using mql_if_arith  = std::enable_if_t<std::is_arithmetic<std::decay_t<T>>::value, int>;
template<class T> using mql_if_integral = std::enable_if_t<std::is_integral<std::decay_t<T>>::value, int>;
template<class T> using mql_if_index  = std::enable_if_t<std::is_integral<std::decay_t<T>>::value || std::is_enum<std::decay_t<T>>::value, int>;
template<class T> using mql_if_numlike = std::enable_if_t<mql_numlike<std::decay_t<T>>::value, int>;
template<class T> using mql_if_numlike_noenum = std::enable_if_t<mql_numlike_noenum<std::decay_t<T>>::value, int>;
template<class T> using mql_if_enum   = std::enable_if_t<std::is_enum<std::decay_t<T>>::value, int>;
template<class T> struct mql_type_identity { typedef T type; };
template<class T> using mql_nondeduced_t = typename mql_type_identity<T>::type;
// SFINAE en el tipo de retorno (los friend no admiten argumentos de plantilla por defecto)
template<class T, class R> using mql_arith_r   = std::enable_if_t<std::is_arithmetic<std::decay_t<T>>::value, R>;
template<class T, class R> using mql_numlike_r = std::enable_if_t<mql_numlike<std::decay_t<T>>::value, R>;
template<class T, class R> using mql_notstr_r  = std::enable_if_t<!std::is_same<std::decay_t<T>, string>::value, R>;

//--------------------------------------------------------------------
// datetime: entero de 64 bits distinto de long (segundos desde 1970)
//--------------------------------------------------------------------
class datetime {
public:
  constexpr datetime() : m_value(0) {}
  constexpr datetime(long value) : m_value(value) {}        // conversión implícita desde enteros
  template<class F, std::enable_if_t<std::is_floating_point<F>::value, int> = 0>
  explicit datetime(F value);                                // (datetime)x con x double: sin aviso, como en MQL5
  explicit datetime(const string &text);                     // (datetime)"2024.01.01 10:00"
  constexpr operator long() const { return m_value; }        // conversión implícita a entero
  datetime &operator+=(long seconds);
  datetime &operator-=(long seconds);
  datetime &operator++();
  datetime  operator++(int);
  datetime &operator--();
  datetime  operator--(int);
  // Operadores "hidden friend": solo participan si un operando es datetime (ADL), así no
  // crean ambigüedades en expresiones puramente numéricas.
  template<class T> friend mql_arith_r<T, datetime> operator+(datetime, T);
  template<class T> friend mql_arith_r<T, datetime> operator+(T, datetime);
  template<class T> friend mql_arith_r<T, datetime> operator-(datetime, T);
  friend long operator-(datetime, datetime);
  friend bool operator==(datetime, datetime);
  friend bool operator!=(datetime, datetime);
  friend bool operator< (datetime, datetime);
  friend bool operator> (datetime, datetime);
  friend bool operator<=(datetime, datetime);
  friend bool operator>=(datetime, datetime);
  template<class T> friend mql_arith_r<T, bool> operator==(datetime, T);
  template<class T> friend mql_arith_r<T, bool> operator!=(datetime, T);
  template<class T> friend mql_arith_r<T, bool> operator< (datetime, T);
  template<class T> friend mql_arith_r<T, bool> operator> (datetime, T);
  template<class T> friend mql_arith_r<T, bool> operator<=(datetime, T);
  template<class T> friend mql_arith_r<T, bool> operator>=(datetime, T);
  template<class T> friend mql_arith_r<T, bool> operator==(T, datetime);
  template<class T> friend mql_arith_r<T, bool> operator!=(T, datetime);
  template<class T> friend mql_arith_r<T, bool> operator< (T, datetime);
  template<class T> friend mql_arith_r<T, bool> operator> (T, datetime);
  template<class T> friend mql_arith_r<T, bool> operator<=(T, datetime);
  template<class T> friend mql_arith_r<T, bool> operator>=(T, datetime);
private:
  long m_value;
};

//--------------------------------------------------------------------
// color: entero de 32 bits (0x00BBGGRR); clrNONE = -1
//--------------------------------------------------------------------
class color {
public:
  constexpr color() : m_value(0) {}
  constexpr color(long value) : m_value((uint)value) {}
  template<class F, std::enable_if_t<std::is_floating_point<F>::value, int> = 0>
  explicit color(F value);
  explicit color(const string &text);
  constexpr operator uint() const { return m_value; }
  friend bool operator==(color, color);
  friend bool operator!=(color, color);
  template<class T> friend mql_arith_r<T, bool> operator==(color, T);
  template<class T> friend mql_arith_r<T, bool> operator!=(color, T);
  template<class T> friend mql_arith_r<T, bool> operator==(T, color);
  template<class T> friend mql_arith_r<T, bool> operator!=(T, color);
private:
  uint m_value;
};

//--------------------------------------------------------------------
// string: tipo de valor. Las conversiones número -> string que MQL5 hace con
// advertencia ("implicit conversion from 'number' to 'string'") se modelan con
// [[deprecated]]; las explícitas ((string)x) no avisan. No existe conversión
// implícita string -> número (el script la informa como advertencia de MQL5).
//--------------------------------------------------------------------
#define MQL5CHECK_NUM2STR "MQL5: implicit conversion from 'number' to 'string'"
class string {
public:
  string();
  string(const char *literal);
  string(const string &other);
  string(const mql_null_t &);                    // string s = NULL;
  explicit string(bool);           explicit string(char);          explicit string(signed char);
  explicit string(uchar);          explicit string(short);         explicit string(ushort);
  explicit string(int);            explicit string(uint);          explicit string(long);
  explicit string(ulong);          explicit string(long long);     explicit string(unsigned long long);
  explicit string(float);          explicit string(double);
  explicit string(datetime);       explicit string(color);
  template<class E, mql_if_enum<E> = 0> explicit string(E);
  template<class T, mql_if_numlike_noenum<T> = 0>
  [[deprecated(MQL5CHECK_NUM2STR)]] string(T);    // string s = 5;  (advertencia en MQL5)
  string &operator=(const string &other);
  string &operator+=(const string &other);
  // Conversión explícita (double)s, (int)s... permitida en MQL5
  explicit operator bool() const;    explicit operator char() const;   explicit operator uchar() const;
  explicit operator short() const;   explicit operator ushort() const; explicit operator int() const;
  explicit operator uint() const;    explicit operator long() const;   explicit operator ulong() const;
  explicit operator float() const;   explicit operator double() const;
  // Operadores "hidden friend" (solo si un operando es string)
  friend string operator+(const string &, const string &);
  template<class T> friend mql_numlike_r<T, string> operator+(const string &, T) __attribute__((deprecated(MQL5CHECK_NUM2STR)));
  template<class T> friend mql_numlike_r<T, string> operator+(T, const string &) __attribute__((deprecated(MQL5CHECK_NUM2STR)));
  friend bool operator==(const string &, const string &);
  friend bool operator!=(const string &, const string &);
  friend bool operator< (const string &, const string &);
  friend bool operator> (const string &, const string &);
  friend bool operator<=(const string &, const string &);
  friend bool operator>=(const string &, const string &);
  friend bool operator==(const string &, const mql_null_t &);
  friend bool operator!=(const string &, const mql_null_t &);
  friend bool operator==(const mql_null_t &, const string &);
  friend bool operator!=(const mql_null_t &, const string &);
  template<class T> friend mql_numlike_r<T, bool> operator==(const string &, T) __attribute__((deprecated(MQL5CHECK_NUM2STR)));
  template<class T> friend mql_numlike_r<T, bool> operator!=(const string &, T) __attribute__((deprecated(MQL5CHECK_NUM2STR)));
  template<class T> friend mql_numlike_r<T, bool> operator==(T, const string &) __attribute__((deprecated(MQL5CHECK_NUM2STR)));
  template<class T> friend mql_numlike_r<T, bool> operator!=(T, const string &) __attribute__((deprecated(MQL5CHECK_NUM2STR)));
  // En MQL5 una cadena solo admite la suma: el resto de operaciones aritméticas son error.
  template<class T> friend void operator-(const string &, const T &) = delete;
  template<class T> friend void operator*(const string &, const T &) = delete;
  template<class T> friend void operator/(const string &, const T &) = delete;
  template<class T> friend void operator%(const string &, const T &) = delete;
  template<class T> friend mql_notstr_r<T, void> operator-(const T &, const string &) = delete;
  template<class T> friend mql_notstr_r<T, void> operator*(const T &, const string &) = delete;
  template<class T> friend mql_notstr_r<T, void> operator/(const T &, const string &) = delete;
private:
  const char *m_data;
};

//--------------------------------------------------------------------
// NULL y WRONG_VALUE
//--------------------------------------------------------------------
struct mql_null_t {
  operator long() const;
  operator datetime() const;
  operator color() const;
  template<class T> operator T *() const;
};
extern const mql_null_t mql_null;
#undef NULL
#define NULL mql_null

struct mql_wrong_value_t {        // "puede convertirse implícitamente a cualquier enum"
  operator int() const;
  template<class E, mql_if_enum<E> = 0> operator E() const;
};
extern const mql_wrong_value_t mql_wrong_value;
#define WRONG_VALUE mql_wrong_value

// Parámetro enum de una función de la API: acepta el enum exacto o un entero
// (p. ej. iMA(NULL, 0, ...) con 0 = PERIOD_CURRENT), pero NO un enum de otro tipo.
template<class E> struct mql_enum_param {
  mql_enum_param(E value);
  template<class I, mql_if_integral<I> = 0> mql_enum_param(I value);
  mql_enum_param(const mql_null_t &);
  mql_enum_param(const mql_wrong_value_t &);
};

//====================================================================
// Arrays: dinámicos T name[]  ->  mql_array<T>
//         fijos     T name[N] ->  mql_fixed_array<T, N> (deriva de mql_array<T>,
//                                 así puede pasarse a parámetros T &arr[])
//====================================================================
template<class T> class mql_array {
public:
  typedef T value_type;
  mql_array();
  mql_array(std::initializer_list<T> values);
  template<class I, mql_if_index<I> = 0> T &operator[](I index);
  template<class I, mql_if_index<I> = 0> const T &operator[](I index) const;
};
template<class T, long N> class mql_fixed_array : public mql_array<T> {
public:
  mql_fixed_array();
  mql_fixed_array(std::initializer_list<T> values);
};
// Tipo escalar de los elementos (para arrays multidimensionales)
template<class T> struct mql_elem { typedef T type; };
template<class T, long N> struct mql_elem<mql_fixed_array<T, N>> { typedef typename mql_elem<T>::type type; };
template<class T> using mql_elem_t = typename mql_elem<T>::type;

//====================================================================
// Constantes
//====================================================================
constexpr char   CHAR_MIN = -128;           constexpr char   CHAR_MAX = 127;
constexpr uchar  UCHAR_MAX = 255;
constexpr short  SHORT_MIN = -32768;        constexpr short  SHORT_MAX = 32767;
constexpr ushort USHORT_MAX = 65535;
constexpr int    INT_MIN = -2147483647 - 1; constexpr int    INT_MAX = 2147483647;
constexpr uint   UINT_MAX = 4294967295u;
constexpr long   LONG_MIN = -9223372036854775807L - 1; constexpr long LONG_MAX = 9223372036854775807L;
constexpr ulong  ULONG_MAX = 18446744073709551615ul;
constexpr double DBL_MAX = 1.7976931348623158e+308;
constexpr double DBL_MIN = 2.2250738585072014e-308;
constexpr double DBL_EPSILON = 2.2204460492503131e-016;
constexpr int    DBL_DIG = 15;  constexpr int DBL_MANT_DIG = 53;
constexpr int    DBL_MAX_10_EXP = 308; constexpr int DBL_MAX_EXP = 1024;
constexpr int    DBL_MIN_10_EXP = -307; constexpr int DBL_MIN_EXP = -1021;
constexpr float  FLT_MAX = 3.402823466e+38f;
constexpr float  FLT_MIN = 1.175494351e-38f;
constexpr float  FLT_EPSILON = 1.192092896e-07f;
constexpr int    FLT_DIG = 6; constexpr int FLT_MANT_DIG = 24;
constexpr int    FLT_MAX_10_EXP = 38; constexpr int FLT_MAX_EXP = 128;
constexpr int    FLT_MIN_10_EXP = -37; constexpr int FLT_MIN_EXP = -125;
constexpr double M_E = 2.71828182845904523536;
constexpr double M_LOG2E = 1.44269504088896340736;
constexpr double M_LOG10E = 0.434294481903251827651;
constexpr double M_LN2 = 0.693147180559945309417;
constexpr double M_LN10 = 2.30258509299404568402;
constexpr double M_PI = 3.14159265358979323846;
constexpr double M_PI_2 = 1.57079632679489661923;
constexpr double M_PI_4 = 0.785398163397448309616;
constexpr double M_1_PI = 0.318309886183790671538;
constexpr double M_2_PI = 0.636619772367581343076;
constexpr double M_2_SQRTPI = 1.12837916709551257390;
constexpr double M_SQRT2 = 1.41421356237309504880;
constexpr double M_SQRT1_2 = 0.707106781186547524401;

constexpr double EMPTY_VALUE = DBL_MAX;
constexpr int    EMPTY = -1;
constexpr int    INVALID_HANDLE = -1;
constexpr int    WHOLE_ARRAY = -1;
constexpr int    CHARTS_MAX = 100;
constexpr bool   IS_DEBUG_MODE = false;
constexpr bool   IS_PROFILE_MODE = false;
constexpr int    TIME_DATE = 1, TIME_MINUTES = 2, TIME_SECONDS = 4;
constexpr int    REASON_PROGRAM = 0, REASON_REMOVE = 1, REASON_RECOMPILE = 2, REASON_CHARTCHANGE = 3,
                 REASON_CHARTCLOSE = 4, REASON_PARAMETERS = 5, REASON_ACCOUNT = 6, REASON_TEMPLATE = 7,
                 REASON_INITFAILED = 8, REASON_CLOSE = 9;
constexpr int    FILE_READ = 1, FILE_WRITE = 2, FILE_BIN = 4, FILE_CSV = 8, FILE_TXT = 16, FILE_ANSI = 32,
                 FILE_UNICODE = 64, FILE_SHARE_READ = 128, FILE_SHARE_WRITE = 256, FILE_REWRITE = 512,
                 FILE_COMMON = 4096;
constexpr int    FILE_EXISTS = 0, FILE_CREATE_DATE = 1, FILE_MODIFY_DATE = 2, FILE_ACCESS_DATE = 3,
                 FILE_SIZE = 4, FILE_POSITION = 5, FILE_END = 6, FILE_LINE_END = 7, FILE_IS_COMMON = 8,
                 FILE_IS_TEXT = 9, FILE_IS_BINARY = 10, FILE_IS_CSV = 11, FILE_IS_ANSI = 12,
                 FILE_IS_READABLE = 13, FILE_IS_WRITABLE = 14;
constexpr int    CHAR_VALUE = 1, SHORT_VALUE = 2, INT_VALUE = 4, LONG_VALUE = 8, FLOAT_VALUE = 4, DOUBLE_VALUE = 8;
constexpr int    CP_ACP = 0, CP_OEMCP = 1, CP_MACCP = 2, CP_THREAD_ACP = 3, CP_SYMBOL = 42, CP_UTF7 = 65000, CP_UTF8 = 65001;
constexpr int    SYMBOL_FILLING_FOK = 1, SYMBOL_FILLING_IOC = 2, SYMBOL_FILLING_BOC = 4;
constexpr int    SYMBOL_EXPIRATION_GTC = 1, SYMBOL_EXPIRATION_DAY = 2, SYMBOL_EXPIRATION_SPECIFIED = 4,
                 SYMBOL_EXPIRATION_SPECIFIED_DAY = 8;
constexpr int    SYMBOL_ORDER_MARKET = 1, SYMBOL_ORDER_LIMIT = 2, SYMBOL_ORDER_STOP = 4,
                 SYMBOL_ORDER_STOP_LIMIT = 8, SYMBOL_ORDER_SL = 16, SYMBOL_ORDER_TP = 32, SYMBOL_ORDER_CLOSEBY = 64;
constexpr int    COPY_TICKS_INFO = 1, COPY_TICKS_TRADE = 2, COPY_TICKS_ALL = 3;
constexpr int    TICK_FLAG_BID = 2, TICK_FLAG_ASK = 4, TICK_FLAG_LAST = 8, TICK_FLAG_VOLUME = 16,
                 TICK_FLAG_BUY = 32, TICK_FLAG_SELL = 64;
// Líneas de los indicadores (búferes)
constexpr int    MAIN_LINE = 0, SIGNAL_LINE = 1, BASE_LINE = 0, UPPER_BAND = 1, LOWER_BAND = 2,
                 PLUSDI_LINE = 1, MINUSDI_LINE = 2, UPPER_LINE = 0, LOWER_LINE = 1,
                 TENKANSEN_LINE = 0, KIJUNSEN_LINE = 1, SENKOUSPANA_LINE = 2, SENKOUSPANB_LINE = 3,
                 CHIKOUSPAN_LINE = 4, GATORJAW_LINE = 0, GATORTEETH_LINE = 1, GATORLIPS_LINE = 2;
// Eventos de gráfico
constexpr int    CHARTEVENT_KEYDOWN = 0, CHARTEVENT_MOUSE_MOVE = 10, CHARTEVENT_MOUSE_WHEEL = 11,
                 CHARTEVENT_OBJECT_CREATE = 7, CHARTEVENT_OBJECT_CHANGE = 8, CHARTEVENT_OBJECT_DELETE = 6,
                 CHARTEVENT_CLICK = 4, CHARTEVENT_OBJECT_CLICK = 1, CHARTEVENT_OBJECT_DRAG = 2,
                 CHARTEVENT_OBJECT_ENDEDIT = 3, CHARTEVENT_CHART_CHANGE = 9, CHARTEVENT_CUSTOM = 1000,
                 CHARTEVENT_CUSTOM_LAST = 66534;
constexpr int    OBJ_NO_PERIODS = 0, OBJ_ALL_PERIODS = 0x1fffff, OBJ_PERIOD_M1 = 1, OBJ_PERIOD_M5 = 0x10,
                 OBJ_PERIOD_M15 = 0x40, OBJ_PERIOD_M30 = 0x100, OBJ_PERIOD_H1 = 0x200, OBJ_PERIOD_H4 = 0x2000,
                 OBJ_PERIOD_D1 = 0x10000, OBJ_PERIOD_W1 = 0x20000, OBJ_PERIOD_MN1 = 0x40000;
// Códigos de retorno del servidor de operaciones
constexpr uint   TRADE_RETCODE_REQUOTE = 10004, TRADE_RETCODE_REJECT = 10006, TRADE_RETCODE_CANCEL = 10007,
                 TRADE_RETCODE_PLACED = 10008, TRADE_RETCODE_DONE = 10009, TRADE_RETCODE_DONE_PARTIAL = 10010,
                 TRADE_RETCODE_ERROR = 10011, TRADE_RETCODE_TIMEOUT = 10012, TRADE_RETCODE_INVALID = 10013,
                 TRADE_RETCODE_INVALID_VOLUME = 10014, TRADE_RETCODE_INVALID_PRICE = 10015,
                 TRADE_RETCODE_INVALID_STOPS = 10016, TRADE_RETCODE_TRADE_DISABLED = 10017,
                 TRADE_RETCODE_MARKET_CLOSED = 10018, TRADE_RETCODE_NO_MONEY = 10019,
                 TRADE_RETCODE_PRICE_CHANGED = 10020, TRADE_RETCODE_PRICE_OFF = 10021,
                 TRADE_RETCODE_INVALID_EXPIRATION = 10022, TRADE_RETCODE_ORDER_CHANGED = 10023,
                 TRADE_RETCODE_TOO_MANY_REQUESTS = 10024, TRADE_RETCODE_NO_CHANGES = 10025,
                 TRADE_RETCODE_SERVER_DISABLES_AT = 10026, TRADE_RETCODE_CLIENT_DISABLES_AT = 10027,
                 TRADE_RETCODE_LOCKED = 10028, TRADE_RETCODE_FROZEN = 10029, TRADE_RETCODE_INVALID_FILL = 10030,
                 TRADE_RETCODE_CONNECTION = 10031, TRADE_RETCODE_ONLY_REAL = 10032,
                 TRADE_RETCODE_LIMIT_ORDERS = 10033, TRADE_RETCODE_LIMIT_VOLUME = 10034,
                 TRADE_RETCODE_INVALID_ORDER = 10035, TRADE_RETCODE_POSITION_CLOSED = 10036,
                 TRADE_RETCODE_INVALID_CLOSE_VOLUME = 10038, TRADE_RETCODE_CLOSE_ORDER_EXIST = 10039,
                 TRADE_RETCODE_LIMIT_POSITIONS = 10040, TRADE_RETCODE_REJECT_CANCEL = 10041,
                 TRADE_RETCODE_LONG_ONLY = 10042, TRADE_RETCODE_SHORT_ONLY = 10043,
                 TRADE_RETCODE_CLOSE_ONLY = 10044, TRADE_RETCODE_FIFO_CLOSE = 10045,
                 TRADE_RETCODE_HEDGE_PROHIBITED = 10046;
// Errores de ejecución (GetLastError)
constexpr int ERR_SUCCESS = 0, ERR_INTERNAL_ERROR = 4001, ERR_WRONG_INTERNAL_PARAMETER = 4002,
  ERR_INVALID_PARAMETER = 4003, ERR_NOT_ENOUGH_MEMORY = 4004, ERR_STRUCT_WITHOBJECTS_ORCLASS = 4005,
  ERR_INVALID_ARRAY = 4006, ERR_ARRAY_RESIZE_ERROR = 4007, ERR_STRING_RESIZE_ERROR = 4008,
  ERR_NOTINITIALIZED_STRING = 4009, ERR_INVALID_DATETIME = 4010, ERR_ARRAY_BAD_SIZE = 4011,
  ERR_INVALID_POINTER = 4012, ERR_INVALID_POINTER_TYPE = 4013, ERR_FUNCTION_NOT_ALLOWED = 4014,
  ERR_RESOURCE_NAME_DUPLICATED = 4015, ERR_RESOURCE_NOT_FOUND = 4016, ERR_RESOURCE_UNSUPPOTED_TYPE = 4017,
  ERR_RESOURCE_NAME_IS_TOO_LONG = 4018, ERR_MATH_OVERFLOW = 4019, ERR_SLEEP_ERROR = 4020,
  ERR_PROGRAM_STOPPED = 4022, ERR_CHART_WRONG_ID = 4101, ERR_CHART_NO_REPLY = 4102,
  ERR_CHART_NOT_FOUND = 4103, ERR_CHART_NO_EXPERT = 4104, ERR_CHART_CANNOT_OPEN = 4105,
  ERR_CHART_CANNOT_CHANGE = 4106, ERR_CHART_WRONG_PARAMETER = 4107, ERR_CHART_CANNOT_CREATE_TIMER = 4108,
  ERR_CHART_WRONG_PROPERTY = 4109, ERR_OBJECT_ERROR = 4201, ERR_OBJECT_NOT_FOUND = 4202,
  ERR_OBJECT_WRONG_PROPERTY = 4203, ERR_OBJECT_GETDATE_FAILED = 4204, ERR_OBJECT_GETVALUE_FAILED = 4205,
  ERR_MARKET_UNKNOWN_SYMBOL = 4301, ERR_MARKET_NOT_SELECTED = 4302, ERR_MARKET_WRONG_PROPERTY = 4303,
  ERR_MARKET_LASTTIME_UNKNOWN = 4304, ERR_MARKET_SELECT_ERROR = 4305, ERR_HISTORY_NOT_FOUND = 4401,
  ERR_HISTORY_WRONG_PROPERTY = 4402, ERR_HISTORY_TIMEOUT = 4403, ERR_HISTORY_BARS_LIMIT = 4404,
  ERR_HISTORY_LOAD_ERRORS = 4405, ERR_HISTORY_SMALL_BUFFER = 4407, ERR_GLOBALVARIABLE_NOT_FOUND = 4501,
  ERR_GLOBALVARIABLE_EXISTS = 4502, ERR_GLOBALVARIABLE_NOT_MODIFIED = 4503,
  ERR_GLOBALVARIABLE_CANNOTREAD = 4504, ERR_GLOBALVARIABLE_CANNOTWRITE = 4505,
  ERR_MAIL_SEND_FAILED = 4510, ERR_PLAY_SOUND_FAILED = 4511, ERR_MQL5_WRONG_PROPERTY = 4512,
  ERR_TERMINAL_WRONG_PROPERTY = 4513, ERR_FTP_SEND_FAILED = 4514, ERR_NOTIFICATION_SEND_FAILED = 4515,
  ERR_NOTIFICATION_WRONG_PARAMETER = 4516, ERR_NOTIFICATION_WRONG_SETTINGS = 4517,
  ERR_NOTIFICATION_TOO_FREQUENT = 4518, ERR_BUFFERS_NO_MEMORY = 4601, ERR_BUFFERS_WRONG_INDEX = 4602,
  ERR_CUSTOM_WRONG_PROPERTY = 4603, ERR_ACCOUNT_WRONG_PROPERTY = 4701, ERR_SERIES_ARRAY = 4702,
  ERR_TRADE_WRONG_PROPERTY = 4751, ERR_TRADE_DISABLED = 4752, ERR_TRADE_POSITION_NOT_FOUND = 4753,
  ERR_TRADE_ORDER_NOT_FOUND = 4754, ERR_TRADE_DEAL_NOT_FOUND = 4755, ERR_TRADE_SEND_FAILED = 4756,
  ERR_TRADE_CALC_FAILED = 4758, ERR_INDICATOR_UNKNOWN_SYMBOL = 4801, ERR_INDICATOR_CANNOT_CREATE = 4802,
  ERR_INDICATOR_NO_MEMORY = 4803, ERR_INDICATOR_CANNOT_APPLY = 4804, ERR_INDICATOR_CANNOT_ADD = 4805,
  ERR_INDICATOR_DATA_NOT_FOUND = 4806, ERR_INDICATOR_WRONG_HANDLE = 4807,
  ERR_INDICATOR_WRONG_PARAMETERS = 4808, ERR_INDICATOR_PARAMETERS_MISSING = 4809,
  ERR_INDICATOR_CUSTOM_NAME = 4810, ERR_INDICATOR_PARAMETER_TYPE = 4811, ERR_INDICATOR_WRONG_INDEX = 4812,
  ERR_BOOKS_CANNOT_ADD = 4901, ERR_BOOKS_CANNOT_DELETE = 4902, ERR_BOOKS_CANNOT_GET = 4903,
  ERR_BOOKS_CANNOT_SUBSCRIBE = 4904, ERR_TOO_LONG_FILENAME = 5002, ERR_CANNOT_OPEN_FILE = 5004,
  ERR_FILE_CACHEBUFFER_ERROR = 5005, ERR_CANNOT_DELETE_FILE = 5006, ERR_TOO_MANY_FILES = 5007,
  ERR_WRONG_FILEHANDLE = 5008, ERR_FILE_NOTTOWRITE = 5009, ERR_FILE_NOTTOREAD = 5010,
  ERR_FILE_NOTBIN = 5011, ERR_FILE_NOTTXT = 5012, ERR_FILE_NOTTXTORCSV = 5013, ERR_FILE_NOTCSV = 5014,
  ERR_FILE_READERROR = 5015, ERR_FILE_BINSTRINGSIZE = 5016, ERR_INCOMPATIBLE_FILE = 5017,
  ERR_FILE_IS_DIRECTORY = 5018, ERR_FILE_NOT_EXIST = 5019, ERR_FILE_CANNOT_REWRITE = 5020,
  ERR_WRONG_DIRECTORYNAME = 5021, ERR_DIRECTORY_NOT_EXIST = 5022, ERR_FILE_ISNOT_DIRECTORY = 5023,
  ERR_CANNOT_DELETE_DIRECTORY = 5024, ERR_CANNOT_CLEAN_DIRECTORY = 5025, ERR_FILE_WRITEERROR = 5026,
  ERR_FILE_ENDOFFILE = 5027, ERR_NO_STRING_DATE = 5030, ERR_WRONG_STRING_DATE = 5031,
  ERR_WRONG_STRING_TIME = 5032, ERR_STRING_TIME_ERROR = 5033, ERR_STRING_OUT_OF_MEMORY = 5034,
  ERR_STRING_SMALL_LEN = 5035, ERR_STRING_TOO_BIGNUMBER = 5036, ERR_WRONG_FORMATSTRING = 5037,
  ERR_TOO_MANY_FORMATTERS = 5038, ERR_TOO_MANY_PARAMETERS = 5039, ERR_WRONG_STRING_PARAMETER = 5040,
  ERR_STRINGPOS_OUTOFRANGE = 5041, ERR_STRING_ZEROADDED = 5042, ERR_STRING_UNKNOWNTYPE = 5043,
  ERR_WRONG_STRING_OBJECT = 5044, ERR_INCOMPATIBLE_ARRAYS = 5050, ERR_SMALL_ASSERIES_ARRAY = 5051,
  ERR_SMALL_ARRAY = 5052, ERR_ZEROSIZE_ARRAY = 5053, ERR_NUMBER_ARRAYS_ONLY = 5054,
  ERR_ONEDIM_ARRAYS_ONLY = 5055, ERR_DOUBLE_ARRAY_ONLY = 5057, ERR_FLOAT_ARRAY_ONLY = 5058,
  ERR_LONG_ARRAY_ONLY = 5059, ERR_INT_ARRAY_ONLY = 5060, ERR_SHORT_ARRAY_ONLY = 5061,
  ERR_CHAR_ARRAY_ONLY = 5062, ERR_STRING_ARRAY_ONLY = 5063, ERR_WEBREQUEST_INVALID_ADDRESS = 5200,
  ERR_WEBREQUEST_CONNECT_FAILED = 5201, ERR_WEBREQUEST_TIMEOUT = 5202, ERR_WEBREQUEST_REQUEST_FAILED = 5203,
  ERR_USER_ERROR_FIRST = 65536;

//====================================================================
// Enumeraciones
//====================================================================
enum ENUM_TIMEFRAMES {
  PERIOD_CURRENT = 0, PERIOD_M1 = 1, PERIOD_M2 = 2, PERIOD_M3 = 3, PERIOD_M4 = 4, PERIOD_M5 = 5,
  PERIOD_M6 = 6, PERIOD_M10 = 10, PERIOD_M12 = 12, PERIOD_M15 = 15, PERIOD_M20 = 20, PERIOD_M30 = 30,
  PERIOD_H1 = 16385, PERIOD_H2 = 16386, PERIOD_H3 = 16387, PERIOD_H4 = 16388, PERIOD_H6 = 16390,
  PERIOD_H8 = 16392, PERIOD_H12 = 16396, PERIOD_D1 = 16408, PERIOD_W1 = 32769, PERIOD_MN1 = 49153
};
enum ENUM_APPLIED_PRICE { PRICE_CLOSE = 1, PRICE_OPEN, PRICE_HIGH, PRICE_LOW, PRICE_MEDIAN, PRICE_TYPICAL, PRICE_WEIGHTED };
enum ENUM_APPLIED_VOLUME { VOLUME_TICK, VOLUME_REAL };
enum ENUM_MA_METHOD { MODE_SMA, MODE_EMA, MODE_SMMA, MODE_LWMA };
enum ENUM_STO_PRICE { STO_LOWHIGH, STO_CLOSECLOSE };
enum ENUM_SERIESMODE { MODE_OPEN, MODE_LOW, MODE_HIGH, MODE_CLOSE, MODE_VOLUME, MODE_REAL_VOLUME, MODE_SPREAD };
enum ENUM_SERIES_INFO_INTEGER { SERIES_BARS_COUNT, SERIES_FIRSTDATE, SERIES_LASTBAR_DATE,
  SERIES_SERVER_FIRSTDATE, SERIES_TERMINAL_FIRSTDATE, SERIES_SYNCHRONIZED };
enum ENUM_INDICATOR { IND_AC, IND_AD, IND_ADX, IND_ADXW, IND_ALLIGATOR, IND_AMA, IND_AO, IND_ATR, IND_BANDS,
  IND_BEARS, IND_BULLS, IND_BWMFI, IND_CCI, IND_CHAIKIN, IND_CUSTOM, IND_DEMA, IND_DEMARKER, IND_ENVELOPES,
  IND_FORCE, IND_FRACTALS, IND_FRAMA, IND_GATOR, IND_ICHIMOKU, IND_MA, IND_MACD, IND_MFI, IND_MOMENTUM,
  IND_OBV, IND_OSMA, IND_RSI, IND_RVI, IND_SAR, IND_STDDEV, IND_STOCHASTIC, IND_TEMA, IND_TRIX, IND_VIDYA,
  IND_VOLUMES, IND_WPR };
enum ENUM_DATATYPE { TYPE_BOOL, TYPE_CHAR, TYPE_UCHAR, TYPE_SHORT, TYPE_USHORT, TYPE_COLOR, TYPE_INT,
  TYPE_UINT, TYPE_DATETIME, TYPE_LONG, TYPE_ULONG, TYPE_FLOAT, TYPE_DOUBLE, TYPE_STRING };
enum ENUM_DAY_OF_WEEK { SUNDAY, MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY };
enum ENUM_INIT_RETCODE { INIT_SUCCEEDED = 0, INIT_FAILED = 1, INIT_PARAMETERS_INCORRECT = 2, INIT_AGENT_NOT_SUITABLE = 3 };
enum ENUM_POINTER_TYPE { POINTER_INVALID, POINTER_DYNAMIC, POINTER_AUTOMATIC };
enum ENUM_FILE_POSITION { SEEK_SET, SEEK_CUR, SEEK_END };
enum ENUM_PROGRAM_TYPE { PROGRAM_SCRIPT, PROGRAM_EXPERT, PROGRAM_INDICATOR, PROGRAM_SERVICE };
enum ENUM_LICENSE_TYPE { LICENSE_FREE, LICENSE_DEMO, LICENSE_FULL, LICENSE_TIME };

// Órdenes, posiciones, operaciones (deals)
enum ENUM_ORDER_TYPE { ORDER_TYPE_BUY, ORDER_TYPE_SELL, ORDER_TYPE_BUY_LIMIT, ORDER_TYPE_SELL_LIMIT,
  ORDER_TYPE_BUY_STOP, ORDER_TYPE_SELL_STOP, ORDER_TYPE_BUY_STOP_LIMIT, ORDER_TYPE_SELL_STOP_LIMIT,
  ORDER_TYPE_CLOSE_BY };
enum ENUM_ORDER_TYPE_FILLING { ORDER_FILLING_FOK, ORDER_FILLING_IOC, ORDER_FILLING_RETURN, ORDER_FILLING_BOC };
enum ENUM_ORDER_TYPE_TIME { ORDER_TIME_GTC, ORDER_TIME_DAY, ORDER_TIME_SPECIFIED, ORDER_TIME_SPECIFIED_DAY };
enum ENUM_ORDER_STATE { ORDER_STATE_STARTED, ORDER_STATE_PLACED, ORDER_STATE_CANCELED, ORDER_STATE_PARTIAL,
  ORDER_STATE_FILLED, ORDER_STATE_REJECTED, ORDER_STATE_EXPIRED, ORDER_STATE_REQUEST_ADD,
  ORDER_STATE_REQUEST_MODIFY, ORDER_STATE_REQUEST_CANCEL };
enum ENUM_ORDER_REASON { ORDER_REASON_CLIENT, ORDER_REASON_MOBILE, ORDER_REASON_WEB, ORDER_REASON_EXPERT,
  ORDER_REASON_SL, ORDER_REASON_TP, ORDER_REASON_SO };
enum ENUM_ORDER_PROPERTY_INTEGER { ORDER_TICKET, ORDER_TIME_SETUP, ORDER_TYPE, ORDER_STATE,
  ORDER_TIME_EXPIRATION, ORDER_TIME_DONE, ORDER_TIME_SETUP_MSC, ORDER_TIME_DONE_MSC, ORDER_TYPE_FILLING,
  ORDER_TYPE_TIME, ORDER_MAGIC, ORDER_REASON, ORDER_POSITION_ID, ORDER_POSITION_BY_ID };
enum ENUM_ORDER_PROPERTY_DOUBLE { ORDER_VOLUME_INITIAL, ORDER_VOLUME_CURRENT, ORDER_PRICE_OPEN, ORDER_SL,
  ORDER_TP, ORDER_PRICE_CURRENT, ORDER_PRICE_STOPLIMIT };
enum ENUM_ORDER_PROPERTY_STRING { ORDER_SYMBOL, ORDER_COMMENT, ORDER_EXTERNAL_ID };
enum ENUM_POSITION_TYPE { POSITION_TYPE_BUY, POSITION_TYPE_SELL };
enum ENUM_POSITION_REASON { POSITION_REASON_CLIENT, POSITION_REASON_MOBILE, POSITION_REASON_WEB, POSITION_REASON_EXPERT };
enum ENUM_POSITION_PROPERTY_INTEGER { POSITION_TICKET, POSITION_TIME, POSITION_TIME_MSC, POSITION_TIME_UPDATE,
  POSITION_TIME_UPDATE_MSC, POSITION_TYPE, POSITION_MAGIC, POSITION_IDENTIFIER, POSITION_REASON };
enum ENUM_POSITION_PROPERTY_DOUBLE { POSITION_VOLUME, POSITION_PRICE_OPEN, POSITION_SL, POSITION_TP,
  POSITION_PRICE_CURRENT, POSITION_SWAP, POSITION_PROFIT, POSITION_COMMISSION };
enum ENUM_POSITION_PROPERTY_STRING { POSITION_SYMBOL, POSITION_COMMENT, POSITION_EXTERNAL_ID };
enum ENUM_DEAL_TYPE { DEAL_TYPE_BUY, DEAL_TYPE_SELL, DEAL_TYPE_BALANCE, DEAL_TYPE_CREDIT, DEAL_TYPE_CHARGE,
  DEAL_TYPE_CORRECTION, DEAL_TYPE_BONUS, DEAL_TYPE_COMMISSION, DEAL_TYPE_COMMISSION_DAILY,
  DEAL_TYPE_COMMISSION_MONTHLY, DEAL_TYPE_COMMISSION_AGENT_DAILY, DEAL_TYPE_COMMISSION_AGENT_MONTHLY,
  DEAL_TYPE_INTEREST, DEAL_TYPE_BUY_CANCELED, DEAL_TYPE_SELL_CANCELED, DEAL_DIVIDEND, DEAL_DIVIDEND_FRANKED,
  DEAL_TAX };
enum ENUM_DEAL_ENTRY { DEAL_ENTRY_IN, DEAL_ENTRY_OUT, DEAL_ENTRY_INOUT, DEAL_ENTRY_OUT_BY };
enum ENUM_DEAL_REASON { DEAL_REASON_CLIENT, DEAL_REASON_MOBILE, DEAL_REASON_WEB, DEAL_REASON_EXPERT,
  DEAL_REASON_SL, DEAL_REASON_TP, DEAL_REASON_SO, DEAL_REASON_ROLLOVER, DEAL_REASON_VMARGIN, DEAL_REASON_SPLIT };
enum ENUM_DEAL_PROPERTY_INTEGER { DEAL_TICKET, DEAL_ORDER, DEAL_TIME, DEAL_TIME_MSC, DEAL_TYPE, DEAL_ENTRY,
  DEAL_MAGIC, DEAL_REASON, DEAL_POSITION_ID };
enum ENUM_DEAL_PROPERTY_DOUBLE { DEAL_VOLUME, DEAL_PRICE, DEAL_COMMISSION, DEAL_SWAP, DEAL_PROFIT, DEAL_FEE,
  DEAL_SL, DEAL_TP };
enum ENUM_DEAL_PROPERTY_STRING { DEAL_SYMBOL, DEAL_COMMENT, DEAL_EXTERNAL_ID };
enum ENUM_TRADE_REQUEST_ACTIONS { TRADE_ACTION_DEAL = 1, TRADE_ACTION_PENDING = 5, TRADE_ACTION_SLTP = 6,
  TRADE_ACTION_MODIFY = 7, TRADE_ACTION_REMOVE = 8, TRADE_ACTION_CLOSE_BY = 10 };
enum ENUM_TRADE_TRANSACTION_TYPE { TRADE_TRANSACTION_ORDER_ADD, TRADE_TRANSACTION_ORDER_UPDATE,
  TRADE_TRANSACTION_ORDER_DELETE, TRADE_TRANSACTION_DEAL_ADD, TRADE_TRANSACTION_DEAL_UPDATE,
  TRADE_TRANSACTION_DEAL_DELETE, TRADE_TRANSACTION_HISTORY_ADD, TRADE_TRANSACTION_HISTORY_UPDATE,
  TRADE_TRANSACTION_HISTORY_DELETE, TRADE_TRANSACTION_POSITION, TRADE_TRANSACTION_REQUEST };
enum ENUM_BOOK_TYPE { BOOK_TYPE_SELL = 1, BOOK_TYPE_BUY, BOOK_TYPE_SELL_MARKET, BOOK_TYPE_BUY_MARKET };

// Símbolos
enum ENUM_SYMBOL_INFO_INTEGER { SYMBOL_SELECT, SYMBOL_VISIBLE, SYMBOL_SESSION_DEALS, SYMBOL_SESSION_BUY_ORDERS,
  SYMBOL_SESSION_SELL_ORDERS, SYMBOL_VOLUME, SYMBOL_VOLUMEHIGH, SYMBOL_VOLUMELOW, SYMBOL_TIME, SYMBOL_TIME_MSC,
  SYMBOL_DIGITS, SYMBOL_SPREAD_FLOAT, SYMBOL_SPREAD, SYMBOL_TICKS_BOOKDEPTH, SYMBOL_TRADE_CALC_MODE,
  SYMBOL_TRADE_MODE, SYMBOL_START_TIME, SYMBOL_EXPIRATION_TIME, SYMBOL_TRADE_STOPS_LEVEL,
  SYMBOL_TRADE_FREEZE_LEVEL, SYMBOL_TRADE_EXEMODE, SYMBOL_SWAP_MODE, SYMBOL_SWAP_ROLLOVER3DAYS,
  SYMBOL_MARGIN_HEDGED_USE_LEG, SYMBOL_EXPIRATION_MODE, SYMBOL_FILLING_MODE, SYMBOL_ORDER_MODE,
  SYMBOL_ORDER_GTC_MODE, SYMBOL_OPTION_MODE, SYMBOL_OPTION_RIGHT, SYMBOL_CUSTOM, SYMBOL_BACKGROUND_COLOR,
  SYMBOL_CHART_MODE, SYMBOL_EXIST, SYMBOL_INDUSTRY, SYMBOL_SECTOR };
enum ENUM_SYMBOL_INFO_DOUBLE { SYMBOL_BID, SYMBOL_BIDHIGH, SYMBOL_BIDLOW, SYMBOL_ASK, SYMBOL_ASKHIGH,
  SYMBOL_ASKLOW, SYMBOL_LAST, SYMBOL_LASTHIGH, SYMBOL_LASTLOW, SYMBOL_VOLUME_REAL, SYMBOL_VOLUMEHIGH_REAL,
  SYMBOL_VOLUMELOW_REAL, SYMBOL_OPTION_STRIKE, SYMBOL_POINT, SYMBOL_TRADE_TICK_VALUE,
  SYMBOL_TRADE_TICK_VALUE_PROFIT, SYMBOL_TRADE_TICK_VALUE_LOSS, SYMBOL_TRADE_TICK_SIZE,
  SYMBOL_TRADE_CONTRACT_SIZE, SYMBOL_TRADE_ACCRUED_INTEREST, SYMBOL_TRADE_FACE_VALUE,
  SYMBOL_TRADE_LIQUIDITY_RATE, SYMBOL_VOLUME_MIN, SYMBOL_VOLUME_MAX, SYMBOL_VOLUME_STEP, SYMBOL_VOLUME_LIMIT,
  SYMBOL_SWAP_LONG, SYMBOL_SWAP_SHORT, SYMBOL_SWAP_SUNDAY, SYMBOL_SWAP_MONDAY, SYMBOL_SWAP_TUESDAY,
  SYMBOL_SWAP_WEDNESDAY, SYMBOL_SWAP_THURSDAY, SYMBOL_SWAP_FRIDAY, SYMBOL_SWAP_SATURDAY,
  SYMBOL_MARGIN_INITIAL, SYMBOL_MARGIN_MAINTENANCE, SYMBOL_SESSION_VOLUME, SYMBOL_SESSION_TURNOVER,
  SYMBOL_SESSION_INTEREST, SYMBOL_SESSION_BUY_ORDERS_VOLUME, SYMBOL_SESSION_SELL_ORDERS_VOLUME,
  SYMBOL_SESSION_OPEN, SYMBOL_SESSION_CLOSE, SYMBOL_SESSION_AW, SYMBOL_SESSION_PRICE_SETTLEMENT,
  SYMBOL_SESSION_PRICE_LIMIT_MIN, SYMBOL_SESSION_PRICE_LIMIT_MAX, SYMBOL_MARGIN_HEDGED, SYMBOL_PRICE_CHANGE,
  SYMBOL_PRICE_VOLATILITY, SYMBOL_PRICE_THEORETICAL, SYMBOL_PRICE_DELTA, SYMBOL_PRICE_THETA,
  SYMBOL_PRICE_GAMMA, SYMBOL_PRICE_VEGA, SYMBOL_PRICE_RHO, SYMBOL_PRICE_OMEGA, SYMBOL_PRICE_SENSITIVITY };
enum ENUM_SYMBOL_INFO_STRING { SYMBOL_BASIS, SYMBOL_CATEGORY, SYMBOL_COUNTRY, SYMBOL_SECTOR_NAME,
  SYMBOL_INDUSTRY_NAME, SYMBOL_CURRENCY_BASE, SYMBOL_CURRENCY_PROFIT, SYMBOL_CURRENCY_MARGIN, SYMBOL_BANK,
  SYMBOL_DESCRIPTION, SYMBOL_EXCHANGE, SYMBOL_FORMULA, SYMBOL_ISIN, SYMBOL_PAGE, SYMBOL_PATH };
enum ENUM_SYMBOL_TRADE_MODE { SYMBOL_TRADE_MODE_DISABLED, SYMBOL_TRADE_MODE_LONGONLY,
  SYMBOL_TRADE_MODE_SHORTONLY, SYMBOL_TRADE_MODE_CLOSEONLY, SYMBOL_TRADE_MODE_FULL };
enum ENUM_SYMBOL_TRADE_EXECUTION { SYMBOL_TRADE_EXECUTION_REQUEST, SYMBOL_TRADE_EXECUTION_INSTANT,
  SYMBOL_TRADE_EXECUTION_MARKET, SYMBOL_TRADE_EXECUTION_EXCHANGE };
enum ENUM_SYMBOL_CALC_MODE { SYMBOL_CALC_MODE_FOREX, SYMBOL_CALC_MODE_FOREX_NO_LEVERAGE,
  SYMBOL_CALC_MODE_FUTURES, SYMBOL_CALC_MODE_CFD, SYMBOL_CALC_MODE_CFDINDEX, SYMBOL_CALC_MODE_CFDLEVERAGE,
  SYMBOL_CALC_MODE_EXCH_STOCKS, SYMBOL_CALC_MODE_EXCH_FUTURES, SYMBOL_CALC_MODE_EXCH_FUTURES_FORTS,
  SYMBOL_CALC_MODE_EXCH_BONDS, SYMBOL_CALC_MODE_EXCH_STOCKS_MOEX, SYMBOL_CALC_MODE_EXCH_BONDS_MOEX,
  SYMBOL_CALC_MODE_SERV_COLLATERAL };
enum ENUM_SYMBOL_SWAP_MODE { SYMBOL_SWAP_MODE_DISABLED, SYMBOL_SWAP_MODE_POINTS,
  SYMBOL_SWAP_MODE_CURRENCY_SYMBOL, SYMBOL_SWAP_MODE_CURRENCY_MARGIN, SYMBOL_SWAP_MODE_CURRENCY_DEPOSIT,
  SYMBOL_SWAP_MODE_CURRENCY_PROFIT, SYMBOL_SWAP_MODE_INTEREST_CURRENT, SYMBOL_SWAP_MODE_INTEREST_OPEN,
  SYMBOL_SWAP_MODE_REOPEN_CURRENT, SYMBOL_SWAP_MODE_REOPEN_BID };
enum ENUM_SYMBOL_ORDER_GTC_MODE { SYMBOL_ORDERS_GTC, SYMBOL_ORDERS_DAILY, SYMBOL_ORDERS_DAILY_EXCLUDING_STOPS };

// Cuenta, terminal, programa
enum ENUM_ACCOUNT_INFO_INTEGER { ACCOUNT_LOGIN, ACCOUNT_TRADE_MODE, ACCOUNT_LEVERAGE, ACCOUNT_LIMIT_ORDERS,
  ACCOUNT_MARGIN_SO_MODE, ACCOUNT_TRADE_ALLOWED, ACCOUNT_TRADE_EXPERT, ACCOUNT_MARGIN_MODE,
  ACCOUNT_CURRENCY_DIGITS, ACCOUNT_FIFO_CLOSE, ACCOUNT_HEDGE_ALLOWED };
enum ENUM_ACCOUNT_INFO_DOUBLE { ACCOUNT_BALANCE, ACCOUNT_CREDIT, ACCOUNT_PROFIT, ACCOUNT_EQUITY, ACCOUNT_MARGIN,
  ACCOUNT_MARGIN_FREE, ACCOUNT_MARGIN_LEVEL, ACCOUNT_MARGIN_SO_CALL, ACCOUNT_MARGIN_SO_SO,
  ACCOUNT_MARGIN_INITIAL, ACCOUNT_MARGIN_MAINTENANCE, ACCOUNT_ASSETS, ACCOUNT_LIABILITIES,
  ACCOUNT_COMMISSION_BLOCKED };
enum ENUM_ACCOUNT_INFO_STRING { ACCOUNT_NAME, ACCOUNT_SERVER, ACCOUNT_CURRENCY, ACCOUNT_COMPANY };
enum ENUM_ACCOUNT_TRADE_MODE { ACCOUNT_TRADE_MODE_DEMO, ACCOUNT_TRADE_MODE_CONTEST, ACCOUNT_TRADE_MODE_REAL };
enum ENUM_ACCOUNT_STOPOUT_MODE { ACCOUNT_STOPOUT_MODE_PERCENT, ACCOUNT_STOPOUT_MODE_MONEY };
enum ENUM_ACCOUNT_MARGIN_MODE { ACCOUNT_MARGIN_MODE_RETAIL_NETTING, ACCOUNT_MARGIN_MODE_EXCHANGE,
  ACCOUNT_MARGIN_MODE_RETAIL_HEDGING };
enum ENUM_TERMINAL_INFO_INTEGER { TERMINAL_BUILD, TERMINAL_COMMUNITY_ACCOUNT, TERMINAL_COMMUNITY_CONNECTION,
  TERMINAL_CONNECTED, TERMINAL_DLLS_ALLOWED, TERMINAL_TRADE_ALLOWED, TERMINAL_EMAIL_ENABLED,
  TERMINAL_FTP_ENABLED, TERMINAL_NOTIFICATIONS_ENABLED, TERMINAL_MAXBARS, TERMINAL_MQID, TERMINAL_CODEPAGE,
  TERMINAL_CPU_CORES, TERMINAL_DISK_SPACE, TERMINAL_MEMORY_PHYSICAL, TERMINAL_MEMORY_TOTAL,
  TERMINAL_MEMORY_AVAILABLE, TERMINAL_MEMORY_USED, TERMINAL_X64, TERMINAL_OPENCL_SUPPORT, TERMINAL_SCREEN_DPI,
  TERMINAL_SCREEN_LEFT, TERMINAL_SCREEN_TOP, TERMINAL_SCREEN_WIDTH, TERMINAL_SCREEN_HEIGHT,
  TERMINAL_LEFT, TERMINAL_TOP, TERMINAL_RIGHT, TERMINAL_BOTTOM, TERMINAL_PING_LAST, TERMINAL_VPS,
  TERMINAL_KEYSTATE_LEFT, TERMINAL_KEYSTATE_UP, TERMINAL_KEYSTATE_RIGHT, TERMINAL_KEYSTATE_DOWN,
  TERMINAL_KEYSTATE_SHIFT, TERMINAL_KEYSTATE_CONTROL, TERMINAL_KEYSTATE_MENU, TERMINAL_KEYSTATE_CAPSLOCK,
  TERMINAL_KEYSTATE_NUMLOCK, TERMINAL_KEYSTATE_SCRLOCK, TERMINAL_KEYSTATE_ENTER, TERMINAL_KEYSTATE_INSERT,
  TERMINAL_KEYSTATE_DELETE, TERMINAL_KEYSTATE_HOME, TERMINAL_KEYSTATE_END, TERMINAL_KEYSTATE_TAB,
  TERMINAL_KEYSTATE_PAGEUP, TERMINAL_KEYSTATE_PAGEDOWN, TERMINAL_KEYSTATE_ESCAPE };
enum ENUM_TERMINAL_INFO_DOUBLE { TERMINAL_COMMUNITY_BALANCE, TERMINAL_RETRANSMISSION };
enum ENUM_TERMINAL_INFO_STRING { TERMINAL_LANGUAGE, TERMINAL_COMPANY, TERMINAL_NAME, TERMINAL_PATH,
  TERMINAL_DATA_PATH, TERMINAL_COMMONDATA_PATH };
enum ENUM_MQL_INFO_INTEGER { MQL_MEMORY_LIMIT, MQL_MEMORY_USED, MQL_PROGRAM_TYPE, MQL_DLLS_ALLOWED,
  MQL_TRADE_ALLOWED, MQL_SIGNALS_ALLOWED, MQL_DEBUG, MQL_PROFILER, MQL_TESTER, MQL_FORWARD, MQL_OPTIMIZATION,
  MQL_VISUAL_MODE, MQL_FRAME_MODE, MQL_LICENSE_TYPE, MQL_HANDLES_USED };
enum ENUM_MQL_INFO_STRING { MQL_PROGRAM_NAME, MQL_PROGRAM_PATH };

// Probador de estrategias
enum ENUM_STATISTICS { STAT_INITIAL_DEPOSIT, STAT_WITHDRAWAL, STAT_PROFIT, STAT_GROSS_PROFIT, STAT_GROSS_LOSS,
  STAT_MAX_PROFITTRADE, STAT_MAX_LOSSTRADE, STAT_CONPROFITMAX, STAT_CONPROFITMAX_TRADES, STAT_MAX_CONWINS,
  STAT_MAX_CONPROFIT_TRADES, STAT_CONLOSSMAX, STAT_CONLOSSMAX_TRADES, STAT_MAX_CONLOSSES,
  STAT_MAX_CONLOSS_TRADES, STAT_BALANCEMIN, STAT_BALANCE_DD, STAT_BALANCEDD_PERCENT,
  STAT_BALANCE_DDREL_PERCENT, STAT_BALANCE_DD_RELATIVE, STAT_EQUITYMIN, STAT_EQUITY_DD,
  STAT_EQUITYDD_PERCENT, STAT_EQUITY_DDREL_PERCENT, STAT_EQUITY_DD_RELATIVE, STAT_EXPECTED_PAYOFF,
  STAT_PROFIT_FACTOR, STAT_RECOVERY_FACTOR, STAT_SHARPE_RATIO, STAT_MIN_MARGINLEVEL, STAT_CUSTOM_ONTESTER,
  STAT_DEALS, STAT_TRADES, STAT_PROFIT_TRADES, STAT_LOSS_TRADES, STAT_SHORT_TRADES, STAT_LONG_TRADES,
  STAT_PROFIT_SHORTTRADES, STAT_PROFIT_LONGTRADES, STAT_PROFITTRADES_AVGCON, STAT_LOSSTRADES_AVGCON,
  STAT_COMPLEX_CRITERION };

// Gráficos y objetos
enum ENUM_CHART_PROPERTY_INTEGER { CHART_SHOW, CHART_IS_OBJECT, CHART_BRING_TO_TOP, CHART_CONTEXT_MENU,
  CHART_CROSSHAIR_TOOL, CHART_MOUSE_SCROLL, CHART_EVENT_MOUSE_WHEEL, CHART_EVENT_MOUSE_MOVE,
  CHART_EVENT_OBJECT_CREATE, CHART_EVENT_OBJECT_DELETE, CHART_MODE, CHART_FOREGROUND, CHART_SHIFT,
  CHART_AUTOSCROLL, CHART_KEYBOARD_CONTROL, CHART_QUICK_NAVIGATION, CHART_SCALE, CHART_SCALEFIX,
  CHART_SCALEFIX_11, CHART_SCALE_PT_PER_BAR, CHART_SHOW_TICKER, CHART_SHOW_OHLC, CHART_SHOW_BID_LINE,
  CHART_SHOW_ASK_LINE, CHART_SHOW_LAST_LINE, CHART_SHOW_PERIOD_SEP, CHART_SHOW_GRID, CHART_SHOW_VOLUMES,
  CHART_SHOW_OBJECT_DESCR, CHART_SHOW_TRADE_LEVELS, CHART_SHOW_DATE_SCALE, CHART_SHOW_PRICE_SCALE,
  CHART_SHOW_ONE_CLICK, CHART_IS_MAXIMIZED, CHART_IS_MINIMIZED, CHART_IS_DOCKED, CHART_FLOAT_LEFT,
  CHART_FLOAT_TOP, CHART_FLOAT_RIGHT, CHART_FLOAT_BOTTOM, CHART_VISIBLE_BARS, CHART_WINDOWS_TOTAL,
  CHART_WINDOW_IS_VISIBLE, CHART_WINDOW_HANDLE, CHART_WINDOW_YDISTANCE, CHART_FIRST_VISIBLE_BAR,
  CHART_WIDTH_IN_BARS, CHART_WIDTH_IN_PIXELS, CHART_HEIGHT_IN_PIXELS, CHART_COLOR_BACKGROUND,
  CHART_COLOR_FOREGROUND, CHART_COLOR_GRID, CHART_COLOR_VOLUME, CHART_COLOR_CHART_UP, CHART_COLOR_CHART_DOWN,
  CHART_COLOR_CHART_LINE, CHART_COLOR_CANDLE_BULL, CHART_COLOR_CANDLE_BEAR, CHART_COLOR_BID, CHART_COLOR_ASK,
  CHART_COLOR_LAST, CHART_COLOR_STOP_LEVEL };
enum ENUM_CHART_PROPERTY_DOUBLE { CHART_SHIFT_SIZE, CHART_FIXED_POSITION, CHART_FIXED_MAX, CHART_FIXED_MIN,
  CHART_POINTS_PER_BAR, CHART_PRICE_MIN, CHART_PRICE_MAX };
enum ENUM_CHART_PROPERTY_STRING { CHART_COMMENT, CHART_EXPERT_NAME, CHART_SCRIPT_NAME };
enum ENUM_CHART_MODE { CHART_BARS, CHART_CANDLES, CHART_LINE };
enum ENUM_CHART_VOLUME_MODE { CHART_VOLUME_HIDE, CHART_VOLUME_TICK, CHART_VOLUME_REAL };
enum ENUM_CHART_POSITION { CHART_BEGIN, CHART_CURRENT_POS, CHART_END };
enum ENUM_OBJECT { OBJ_VLINE, OBJ_HLINE, OBJ_TREND, OBJ_TRENDBYANGLE, OBJ_CYCLES, OBJ_ARROWED_LINE,
  OBJ_CHANNEL, OBJ_STDDEVCHANNEL, OBJ_REGRESSION, OBJ_PITCHFORK, OBJ_GANNLINE, OBJ_GANNFAN, OBJ_GANNGRID,
  OBJ_FIBO, OBJ_FIBOTIMES, OBJ_FIBOFAN, OBJ_FIBOARC, OBJ_FIBOCHANNEL, OBJ_EXPANSION, OBJ_ELLIOTWAVE5,
  OBJ_ELLIOTWAVE3, OBJ_RECTANGLE, OBJ_TRIANGLE, OBJ_ELLIPSE, OBJ_ARROW_THUMB_UP, OBJ_ARROW_THUMB_DOWN,
  OBJ_ARROW_UP, OBJ_ARROW_DOWN, OBJ_ARROW_STOP, OBJ_ARROW_CHECK, OBJ_ARROW_LEFT_PRICE,
  OBJ_ARROW_RIGHT_PRICE, OBJ_ARROW_BUY, OBJ_ARROW_SELL, OBJ_ARROW, OBJ_TEXT, OBJ_LABEL, OBJ_BUTTON,
  OBJ_CHART, OBJ_BITMAP, OBJ_BITMAP_LABEL, OBJ_EDIT, OBJ_EVENT, OBJ_RECTANGLE_LABEL };
enum ENUM_OBJECT_PROPERTY_INTEGER { OBJPROP_COLOR, OBJPROP_STYLE, OBJPROP_WIDTH, OBJPROP_BACK, OBJPROP_ZORDER,
  OBJPROP_FILL, OBJPROP_HIDDEN, OBJPROP_SELECTED, OBJPROP_READONLY, OBJPROP_TYPE, OBJPROP_TIME,
  OBJPROP_SELECTABLE, OBJPROP_CREATETIME, OBJPROP_LEVELS, OBJPROP_LEVELCOLOR, OBJPROP_LEVELSTYLE,
  OBJPROP_LEVELWIDTH, OBJPROP_ALIGN, OBJPROP_FONTSIZE, OBJPROP_RAY_LEFT, OBJPROP_RAY_RIGHT, OBJPROP_RAY,
  OBJPROP_ELLIPSE, OBJPROP_ARROWCODE, OBJPROP_TIMEFRAMES, OBJPROP_ANCHOR, OBJPROP_XDISTANCE,
  OBJPROP_YDISTANCE, OBJPROP_DIRECTION, OBJPROP_DEGREE, OBJPROP_DRAWLINES, OBJPROP_STATE, OBJPROP_CHART_ID,
  OBJPROP_XSIZE, OBJPROP_YSIZE, OBJPROP_XOFFSET, OBJPROP_YOFFSET, OBJPROP_PERIOD, OBJPROP_DATE_SCALE,
  OBJPROP_PRICE_SCALE, OBJPROP_CHART_SCALE, OBJPROP_BGCOLOR, OBJPROP_CORNER, OBJPROP_BORDER_TYPE,
  OBJPROP_BORDER_COLOR };
enum ENUM_OBJECT_PROPERTY_DOUBLE { OBJPROP_PRICE, OBJPROP_LEVELVALUE, OBJPROP_SCALE, OBJPROP_ANGLE,
  OBJPROP_DEVIATION };
enum ENUM_OBJECT_PROPERTY_STRING { OBJPROP_NAME, OBJPROP_TEXT, OBJPROP_TOOLTIP, OBJPROP_LEVELTEXT,
  OBJPROP_FONT, OBJPROP_BMPFILE, OBJPROP_SYMBOL };
enum ENUM_BASE_CORNER { CORNER_LEFT_UPPER, CORNER_LEFT_LOWER, CORNER_RIGHT_LOWER, CORNER_RIGHT_UPPER };
enum ENUM_ANCHOR_POINT { ANCHOR_LEFT_UPPER, ANCHOR_LEFT, ANCHOR_LEFT_LOWER, ANCHOR_LOWER, ANCHOR_RIGHT_LOWER,
  ANCHOR_RIGHT, ANCHOR_RIGHT_UPPER, ANCHOR_UPPER, ANCHOR_CENTER };
enum ENUM_ARROW_ANCHOR { ANCHOR_TOP, ANCHOR_BOTTOM };
enum ENUM_LINE_STYLE { STYLE_SOLID, STYLE_DASH, STYLE_DOT, STYLE_DASHDOT, STYLE_DASHDOTDOT };
enum ENUM_BORDER_TYPE { BORDER_FLAT, BORDER_RAISED, BORDER_SUNKEN };
enum ENUM_ALIGN_MODE { ALIGN_LEFT, ALIGN_CENTER, ALIGN_RIGHT };

//====================================================================
// Colores (clr*)
//====================================================================
extern const color clrNONE, CLR_NONE, clrBlack, clrDarkGreen, clrDarkSlateGray, clrOlive, clrGreen, clrTeal,
  clrNavy, clrPurple, clrMaroon, clrIndigo, clrMidnightBlue, clrDarkBlue, clrDarkOliveGreen, clrSaddleBrown,
  clrForestGreen, clrOliveDrab, clrSeaGreen, clrDarkGoldenrod, clrDarkSlateBlue, clrSienna, clrMediumBlue,
  clrBrown, clrDarkTurquoise, clrDimGray, clrLightSeaGreen, clrDarkViolet, clrFireBrick, clrMediumVioletRed,
  clrMediumSeaGreen, clrChocolate, clrCrimson, clrSteelBlue, clrGoldenrod, clrMediumSpringGreen,
  clrLawnGreen, clrCadetBlue, clrDarkOrchid, clrYellowGreen, clrLimeGreen, clrOrangeRed, clrDarkOrange,
  clrOrange, clrGold, clrYellow, clrChartreuse, clrLime, clrSpringGreen, clrAqua, clrDeepSkyBlue, clrBlue,
  clrMagenta, clrRed, clrGray, clrSlateGray, clrPeru, clrBlueViolet, clrLightSlateGray, clrDeepPink,
  clrMediumTurquoise, clrDodgerBlue, clrTurquoise, clrRoyalBlue, clrSlateBlue, clrDarkKhaki, clrIndianRed,
  clrMediumOrchid, clrGreenYellow, clrMediumAquamarine, clrDarkSeaGreen, clrTomato, clrRosyBrown, clrOrchid,
  clrMediumPurple, clrPaleVioletRed, clrCoral, clrCornflowerBlue, clrDarkGray, clrSandyBrown,
  clrMediumSlateBlue, clrTan, clrDarkSalmon, clrBurlyWood, clrHotPink, clrSalmon, clrViolet, clrLightCoral,
  clrSkyBlue, clrLightSalmon, clrPlum, clrKhaki, clrLightGreen, clrAquamarine, clrSilver, clrLightSkyBlue,
  clrLightSteelBlue, clrLightBlue, clrPaleGreen, clrThistle, clrPowderBlue, clrPaleGoldenrod,
  clrPaleTurquoise, clrLightGray, clrWheat, clrNavajoWhite, clrMoccasin, clrLightPink, clrGainsboro,
  clrPeachPuff, clrPink, clrBisque, clrLightGoldenrod, clrBlanchedAlmond, clrLemonChiffon, clrBeige,
  clrAntiqueWhite, clrPapayaWhip, clrCornsilk, clrLightYellow, clrLightCyan, clrLinen, clrLavender,
  clrMistyRose, clrOldLace, clrWhiteSmoke, clrSeashell, clrIvory, clrHoneydew, clrAliceBlue, clrLavenderBlush,
  clrMintCream, clrSnow, clrWhite;

//====================================================================
// Estructuras
//====================================================================
struct MqlDateTime { int year; int mon; int day; int hour; int min; int sec; int day_of_week; int day_of_year; };
struct MqlTick { datetime time; double bid; double ask; double last; ulong volume; long time_msc; uint flags; double volume_real; };
struct MqlRates { datetime time; double open; double high; double low; double close; long tick_volume; int spread; long real_volume; };
struct MqlTradeRequest {
  ENUM_TRADE_REQUEST_ACTIONS action; ulong magic; ulong order; string symbol; double volume; double price;
  double stoplimit; double sl; double tp; ulong deviation; ENUM_ORDER_TYPE type;
  ENUM_ORDER_TYPE_FILLING type_filling; ENUM_ORDER_TYPE_TIME type_time; datetime expiration; string comment;
  ulong position; ulong position_by;
};
struct MqlTradeResult {
  uint retcode; ulong deal; ulong order; double volume; double price; double bid; double ask; string comment;
  uint request_id; int retcode_external;
};
struct MqlTradeCheckResult {
  uint retcode; double balance; double equity; double profit; double margin; double margin_free;
  double margin_level; string comment;
};
struct MqlTradeTransaction {
  ulong deal; ulong order; string symbol; ENUM_TRADE_TRANSACTION_TYPE type; ENUM_ORDER_TYPE order_type;
  ENUM_ORDER_STATE order_state; ENUM_DEAL_TYPE deal_type; ENUM_ORDER_TYPE_TIME time_type;
  datetime time_expiration; double price; double price_trigger; double price_sl; double price_tp;
  double volume; ulong position; ulong position_by;
};
struct MqlParam { ENUM_DATATYPE type; long integer_value; double double_value; string string_value; };
struct MqlBookInfo { ENUM_BOOK_TYPE type; double price; long volume; double volume_real; };

//====================================================================
// Variables predefinidas (solo lectura)
//====================================================================
extern const string          _Symbol;
extern const double          _Point;
extern const int             _Digits;
extern const ENUM_TIMEFRAMES _Period;
extern const int             _LastError;
extern const bool            _StopFlag;
extern const int             _UninitReason;
extern const int             _RandomSeed;
extern const bool            _IsX64;
extern const int             _AppliedTo;

// Macros predefinidas de MQL5
#define __MQL5__ 1
#define __MQL__ 1
#define __MQLBUILD__ 4000
#define __MQL5BUILD__ 4000
extern const datetime mql_compile_datetime;
#define __DATETIME__ mql_compile_datetime
#undef __DATE__
#define __DATE__ mql_compile_datetime
#define __PATH__ __FILE__
#define __FUNCSIG__ __PRETTY_FUNCTION__

//====================================================================
// Funciones de salida (argumentos variables de tipos simples)
//====================================================================
template<class T> struct mql_printable : std::integral_constant<bool,
    mql_numlike<T>::value || std::is_pointer<T>::value || std::is_same<T, string>::value ||
    std::is_same<T, mql_null_t>::value || std::is_same<T, mql_wrong_value_t>::value> {};
template<class... A> using mql_if_printable = std::enable_if_t<(mql_printable<std::decay_t<A>>::value && ...), int>;

template<class... A, mql_if_printable<A...> = 0> void   Print(const A &... args);
template<class... A, mql_if_printable<A...> = 0> void   PrintFormat(const string &format, const A &... args);
template<class... A, mql_if_printable<A...> = 0> void   Comment(const A &... args);
template<class... A, mql_if_printable<A...> = 0> void   Alert(const A &... args);
template<class... A, mql_if_printable<A...> = 0> string StringFormat(const string &format, const A &... args);
template<class... A, mql_if_printable<A...> = 0> int    StringConcatenate(string &string_var, const A &... args);
bool SendNotification(const string &text);
bool SendMail(const string &subject, const string &some_text);
bool SendFTP(const string &filename, const string &ftp_path = NULL);
bool PlaySound(const string &filename);
void DebugBreak();

//====================================================================
// Errores, entorno, utilidades
//====================================================================
int    GetLastError();
void   ResetLastError();
void   SetUserError(ushort user_error);
bool   IsStopped();
void   Sleep(int milliseconds);
uint   GetTickCount();
ulong  GetTickCount64();
ulong  GetMicrosecondCount();
void   ExpertRemove();
bool   TerminalClose(int ret_code);
string Symbol();
ENUM_TIMEFRAMES Period();
double Point();
int    Digits();
bool   MQLSetInteger(mql_enum_param<ENUM_MQL_INFO_INTEGER> property_id, int property_value);
int    MQLInfoInteger(mql_enum_param<ENUM_MQL_INFO_INTEGER> property_id);
string MQLInfoString(mql_enum_param<ENUM_MQL_INFO_STRING> property_id);
int    TerminalInfoInteger(mql_enum_param<ENUM_TERMINAL_INFO_INTEGER> property_id);
double TerminalInfoDouble(mql_enum_param<ENUM_TERMINAL_INFO_DOUBLE> property_id);
string TerminalInfoString(mql_enum_param<ENUM_TERMINAL_INFO_STRING> property_id);
template<class T> void ZeroMemory(T &variable);
template<class T> T *GetPointer(T &object);
template<class T> T *GetPointer(T *pointer);        // con un puntero devuelve el mismo puntero
template<class T> ENUM_POINTER_TYPE CheckPointer(T *pointer);
template<class T> bool MathSwap(T &a, T &b);
int    WebRequest(const string &method, const string &url, const string &headers, int timeout,
                  const mql_array<char> &data, mql_array<char> &result, string &result_headers);
int    WebRequest(const string &method, const string &url, const string &cookie, const string &referer,
                  int timeout, const mql_array<char> &data, int data_size, mql_array<char> &result,
                  string &result_headers);

//====================================================================
// Matemáticas
//====================================================================
template<class T> struct mql_as_num { typedef T type; };
template<> struct mql_as_num<datetime> { typedef long type; };
template<> struct mql_as_num<color> { typedef uint type; };
template<class T> using mql_as_num_t = typename mql_as_num<std::conditional_t<std::is_enum<T>::value, int, T>>::type;
template<class A, class B> using mql_common_t = std::common_type_t<mql_as_num_t<std::decay_t<A>>, mql_as_num_t<std::decay_t<B>>>;

template<class A, class B, mql_if_numlike<A> = 0, mql_if_numlike<B> = 0> mql_common_t<A, B> MathMax(A a, B b);
template<class A, class B, mql_if_numlike<A> = 0, mql_if_numlike<B> = 0> mql_common_t<A, B> MathMin(A a, B b);
template<class A, class B, mql_if_numlike<A> = 0, mql_if_numlike<B> = 0> mql_common_t<A, B> fmax(A a, B b);
template<class A, class B, mql_if_numlike<A> = 0, mql_if_numlike<B> = 0> mql_common_t<A, B> fmin(A a, B b);
template<class T, mql_if_numlike<T> = 0> mql_as_num_t<std::decay_t<T>> MathAbs(T value);
template<class T, mql_if_numlike<T> = 0> mql_as_num_t<std::decay_t<T>> fabs(T value);
double MathArccos(double);  double MathArcsin(double);  double MathArctan(double);
double MathArctan2(double y, double x);
double MathCeil(double);    double MathCos(double);     double MathExp(double);
double MathFloor(double);   double MathLog(double);     double MathLog10(double);
double MathLog1p(double);   double MathExpm1(double);   double MathMod(double, double);
double MathPow(double base, double exponent);            double MathRound(double);
double MathSin(double);     double MathSqrt(double);    double MathTan(double);
double MathSinh(double);    double MathCosh(double);    double MathTanh(double);
double MathArcsinh(double); double MathArccosh(double); double MathArctanh(double);
bool   MathIsValidNumber(double);
int    MathRand();
void   MathSrand(int seed);
void   srand(int seed);
int    rand();
double acos(double); double asin(double); double atan(double); double ceil(double); double cos(double);
double exp(double);  double floor(double); double log(double); double log10(double); double fmod(double, double);
double pow(double, double); double round(double); double sin(double); double sqrt(double); double tan(double);
double NormalizeDouble(double value, int digits);

//====================================================================
// Cadenas y conversiones
//====================================================================
int    StringLen(const string &string_value);
int    StringFind(const string &string_value, const string &match_substring, int start_pos = 0);
string StringSubstr(const string &string_value, int start_pos, int length = -1);
bool   StringToUpper(string &string_var);
bool   StringToLower(string &string_var);
int    StringReplace(string &str, const string &find, const string &replacement);
int    StringSplit(const string &string_value, ushort separator, mql_array<string> &result);
int    StringTrimLeft(string &string_var);
int    StringTrimRight(string &string_var);
bool   StringAdd(string &string_var, const string &add_substring);
int    StringCompare(const string &string1, const string &string2, bool case_sensitive = true);
ushort StringGetCharacter(const string &string_value, int pos);
bool   StringSetCharacter(string &string_var, int pos, ushort character);
bool   StringFill(string &string_var, ushort character);
bool   StringInit(string &string_var, int new_len = 0, ushort character = 0);
int    StringBufferLen(const string &string_var);
bool   StringSetLength(string &string_var, uint new_length);
bool   StringReserve(string &string_var, uint new_capacity);
int    StringToCharArray(const string &text_string, mql_array<uchar> &array, int start = 0, int count = -1, uint codepage = CP_ACP);
int    StringToCharArray(const string &text_string, mql_array<char> &array, int start = 0, int count = -1, uint codepage = CP_ACP);
string CharArrayToString(const mql_array<uchar> &array, int start = 0, int count = -1, uint codepage = CP_ACP);
string CharArrayToString(const mql_array<char> &array, int start = 0, int count = -1, uint codepage = CP_ACP);
int    StringToShortArray(const string &text_string, mql_array<ushort> &array, int start = 0, int count = -1);
string ShortArrayToString(const mql_array<ushort> &array, int start = 0, int count = -1);
string IntegerToString(long number, int str_len = 0, ushort fill_symbol = ' ');
string DoubleToString(double value, int digits = 8);
double StringToDouble(const string &value);
long   StringToInteger(const string &value);
string CharToString(uchar char_code);
string ShortToString(ushort symbol_code);
string ColorToString(color color_value, bool color_name = false);
color  StringToColor(const string &color_string);
string TimeToString(datetime value, int mode = TIME_DATE | TIME_MINUTES);
datetime StringToTime(const string &value);
template<class E, mql_if_enum<E> = 0> string EnumToString(E value);

//====================================================================
// Fecha y hora
//====================================================================
datetime TimeCurrent();
datetime TimeCurrent(MqlDateTime &dt_struct);
datetime TimeLocal();
datetime TimeLocal(MqlDateTime &dt_struct);
datetime TimeGMT();
datetime TimeGMT(MqlDateTime &dt_struct);
datetime TimeTradeServer();
datetime TimeTradeServer(MqlDateTime &dt_struct);
int      TimeDaylightSavings();
int      TimeGMTOffset();
bool     TimeToStruct(datetime dt, MqlDateTime &dt_struct);
datetime StructToTime(const MqlDateTime &dt_struct);
int      PeriodSeconds(mql_enum_param<ENUM_TIMEFRAMES> period = PERIOD_CURRENT);

//====================================================================
// Arrays
//====================================================================
template<class T> int  ArraySize(const mql_array<T> &array);
template<class T> int  ArrayResize(mql_array<T> &array, int new_size, int reserve_size = 0);
template<class T> bool ArraySetAsSeries(const mql_array<T> &array, bool flag);
template<class T> bool ArrayGetAsSeries(const mql_array<T> &array);
template<class T> bool ArrayIsSeries(const mql_array<T> &array);
template<class T> bool ArrayIsDynamic(const mql_array<T> &array);
template<class T> int  ArrayInitialize(mql_array<T> &array, mql_nondeduced_t<mql_elem_t<T>> value);
template<class T> void ArrayFill(mql_array<T> &array, int start, int count, mql_nondeduced_t<mql_elem_t<T>> value);
template<class T> void ArrayFree(mql_array<T> &array);
template<class T, class U> int ArrayCopy(mql_array<T> &dst_array, const mql_array<U> &src_array,
                                         int dst_start = 0, int src_start = 0, int count = WHOLE_ARRAY);
template<class T> bool ArraySort(mql_array<T> &array);
template<class T> int  ArrayMaximum(const mql_array<T> &array, int start = 0, int count = WHOLE_ARRAY);
template<class T> int  ArrayMinimum(const mql_array<T> &array, int start = 0, int count = WHOLE_ARRAY);
template<class T> int  ArrayBsearch(const mql_array<T> &array, mql_nondeduced_t<T> value);
template<class T> int  ArrayRange(const mql_array<T> &array, int rank_index);
template<class T> int  ArrayDimension(const mql_array<T> &array);
template<class T> bool ArrayReverse(mql_array<T> &array, uint start = 0, uint count = WHOLE_ARRAY);
template<class T> bool ArrayInsert(mql_array<T> &dst_array, const mql_array<T> &src_array, uint dst_start,
                                   uint src_start = 0, uint count = WHOLE_ARRAY);
template<class T> bool ArrayRemove(mql_array<T> &array, uint start, uint count = WHOLE_ARRAY);
template<class T> bool ArraySwap(mql_array<T> &array1, mql_array<T> &array2);
template<class T> int  ArrayCompare(const mql_array<T> &array1, const mql_array<T> &array2,
                                    int start1 = 0, int start2 = 0, int count = WHOLE_ARRAY);
template<class T> void ArrayPrint(const mql_array<T> &array, uint digits = 8, const string &separator = NULL,
                                  ulong start = 0, ulong count = WHOLE_ARRAY, ulong flags = 0);

//====================================================================
// Series temporales e indicadores
//====================================================================
typedef mql_enum_param<ENUM_TIMEFRAMES> mql_tf;
datetime iTime(const string &symbol, mql_tf timeframe, int shift);
double   iOpen(const string &symbol, mql_tf timeframe, int shift);
double   iHigh(const string &symbol, mql_tf timeframe, int shift);
double   iLow(const string &symbol, mql_tf timeframe, int shift);
double   iClose(const string &symbol, mql_tf timeframe, int shift);
long     iVolume(const string &symbol, mql_tf timeframe, int shift);
long     iTickVolume(const string &symbol, mql_tf timeframe, int shift);
long     iRealVolume(const string &symbol, mql_tf timeframe, int shift);
long     iSpread(const string &symbol, mql_tf timeframe, int shift);
int      iBars(const string &symbol, mql_tf timeframe);
int      iBarShift(const string &symbol, mql_tf timeframe, datetime time, bool exact = false);
int      iHighest(const string &symbol, mql_tf timeframe, mql_enum_param<ENUM_SERIESMODE> type, int count = WHOLE_ARRAY, int start = 0);
int      iLowest(const string &symbol, mql_tf timeframe, mql_enum_param<ENUM_SERIESMODE> type, int count = WHOLE_ARRAY, int start = 0);
int      Bars(const string &symbol_name, mql_tf timeframe);
int      Bars(const string &symbol_name, mql_tf timeframe, datetime start_time, datetime stop_time);
long     SeriesInfoInteger(const string &symbol_name, mql_tf timeframe, mql_enum_param<ENUM_SERIES_INFO_INTEGER> prop_id);
bool     SeriesInfoInteger(const string &symbol_name, mql_tf timeframe, mql_enum_param<ENUM_SERIES_INFO_INTEGER> prop_id, long &long_var);

#define MQL5CHECK_COPY(NAME, ELEM) \
  int NAME(const string &symbol_name, mql_tf timeframe, int start_pos, int count, mql_array<ELEM> &array); \
  int NAME(const string &symbol_name, mql_tf timeframe, datetime start_time, int count, mql_array<ELEM> &array); \
  int NAME(const string &symbol_name, mql_tf timeframe, datetime start_time, datetime stop_time, mql_array<ELEM> &array);
MQL5CHECK_COPY(CopyRates, MqlRates)
MQL5CHECK_COPY(CopyTime, datetime)
MQL5CHECK_COPY(CopyOpen, double)
MQL5CHECK_COPY(CopyHigh, double)
MQL5CHECK_COPY(CopyLow, double)
MQL5CHECK_COPY(CopyClose, double)
MQL5CHECK_COPY(CopyTickVolume, long)
MQL5CHECK_COPY(CopyRealVolume, long)
MQL5CHECK_COPY(CopySpread, int)
#undef MQL5CHECK_COPY
int CopyBuffer(int indicator_handle, int buffer_num, int start_pos, int count, mql_array<double> &buffer);
int CopyBuffer(int indicator_handle, int buffer_num, datetime start_time, int count, mql_array<double> &buffer);
int CopyBuffer(int indicator_handle, int buffer_num, datetime start_time, datetime stop_time, mql_array<double> &buffer);
int CopyTicks(const string &symbol_name, mql_array<MqlTick> &ticks_array, uint flags = COPY_TICKS_ALL, ulong from = 0, uint count = 0);
int CopyTicksRange(const string &symbol_name, mql_array<MqlTick> &ticks_array, uint flags = COPY_TICKS_ALL, ulong from_msc = 0, ulong to_msc = 0);
int  BarsCalculated(int indicator_handle);
bool IndicatorRelease(int indicator_handle);
int  IndicatorCreate(const string &symbol, mql_tf period, mql_enum_param<ENUM_INDICATOR> indicator_type,
                     int parameters_cnt = 0);
int  IndicatorCreate(const string &symbol, mql_tf period, mql_enum_param<ENUM_INDICATOR> indicator_type,
                     int parameters_cnt, const mql_array<MqlParam> &parameters_array);

typedef mql_enum_param<ENUM_APPLIED_PRICE>  mql_price;
typedef mql_enum_param<ENUM_MA_METHOD>      mql_ma;
typedef mql_enum_param<ENUM_APPLIED_VOLUME> mql_vol;
int iMA(const string &symbol, mql_tf period, int ma_period, int ma_shift, mql_ma ma_method, mql_price applied_price);
int iATR(const string &symbol, mql_tf period, int ma_period);
int iADX(const string &symbol, mql_tf period, int adx_period);
int iADXWilder(const string &symbol, mql_tf period, int adx_period);
int iRSI(const string &symbol, mql_tf period, int ma_period, mql_price applied_price);
int iBands(const string &symbol, mql_tf period, int bands_period, int bands_shift, double deviation, mql_price applied_price);
int iStdDev(const string &symbol, mql_tf period, int ma_period, int ma_shift, mql_ma ma_method, mql_price applied_price);
int iMACD(const string &symbol, mql_tf period, int fast_ema_period, int slow_ema_period, int signal_period, mql_price applied_price);
int iStochastic(const string &symbol, mql_tf period, int Kperiod, int Dperiod, int slowing, mql_ma ma_method,
                mql_enum_param<ENUM_STO_PRICE> price_field);
int iCCI(const string &symbol, mql_tf period, int ma_period, mql_price applied_price);
int iMomentum(const string &symbol, mql_tf period, int mom_period, mql_price applied_price);
int iSAR(const string &symbol, mql_tf period, double step, double maximum);
int iEnvelopes(const string &symbol, mql_tf period, int ma_period, int ma_shift, mql_ma ma_method,
               mql_price applied_price, double deviation);
int iIchimoku(const string &symbol, mql_tf period, int tenkan_sen, int kijun_sen, int senkou_span_b);
int iWPR(const string &symbol, mql_tf period, int calc_period);
int iAO(const string &symbol, mql_tf period);
int iAC(const string &symbol, mql_tf period);
int iAD(const string &symbol, mql_tf period, mql_vol applied_volume);
int iAlligator(const string &symbol, mql_tf period, int jaw_period, int jaw_shift, int teeth_period, int teeth_shift,
               int lips_period, int lips_shift, mql_ma ma_method, mql_price applied_price);
int iGator(const string &symbol, mql_tf period, int jaw_period, int jaw_shift, int teeth_period, int teeth_shift,
           int lips_period, int lips_shift, mql_ma ma_method, mql_price applied_price);
int iFractals(const string &symbol, mql_tf period);
int iOBV(const string &symbol, mql_tf period, mql_vol applied_volume);
int iMFI(const string &symbol, mql_tf period, int ma_period, mql_vol applied_volume);
int iDeMarker(const string &symbol, mql_tf period, int ma_period);
int iForce(const string &symbol, mql_tf period, int ma_period, mql_ma ma_method, mql_vol applied_volume);
int iRVI(const string &symbol, mql_tf period, int ma_period);
int iDEMA(const string &symbol, mql_tf period, int ma_period, int ma_shift, mql_price applied_price);
int iTEMA(const string &symbol, mql_tf period, int ma_period, int ma_shift, mql_price applied_price);
int iAMA(const string &symbol, mql_tf period, int ama_period, int fast_ma_period, int slow_ma_period, int ama_shift, mql_price applied_price);
int iFrAMA(const string &symbol, mql_tf period, int ma_period, int ma_shift, mql_price applied_price);
int iVIDyA(const string &symbol, mql_tf period, int cmo_period, int ema_period, int ma_shift, mql_price applied_price);
int iTriX(const string &symbol, mql_tf period, int ma_period, mql_price applied_price);
int iOsMA(const string &symbol, mql_tf period, int fast_ema_period, int slow_ema_period, int signal_period, mql_price applied_price);
int iBearsPower(const string &symbol, mql_tf period, int ma_period);
int iBullsPower(const string &symbol, mql_tf period, int ma_period);
int iChaikin(const string &symbol, mql_tf period, int fast_ma_period, int slow_ma_period, mql_ma ma_method, mql_vol applied_volume);
int iVolumes(const string &symbol, mql_tf period, mql_vol applied_volume);
int iBWMFI(const string &symbol, mql_tf period, mql_vol applied_volume);
template<class... A, mql_if_printable<A...> = 0> int iCustom(const string &symbol, mql_tf period, const string &name, const A &... params);

//====================================================================
// Información de símbolos, cuenta
//====================================================================
double SymbolInfoDouble(const string &name, mql_enum_param<ENUM_SYMBOL_INFO_DOUBLE> prop_id);
bool   SymbolInfoDouble(const string &name, mql_enum_param<ENUM_SYMBOL_INFO_DOUBLE> prop_id, double &double_var);
long   SymbolInfoInteger(const string &name, mql_enum_param<ENUM_SYMBOL_INFO_INTEGER> prop_id);
bool   SymbolInfoInteger(const string &name, mql_enum_param<ENUM_SYMBOL_INFO_INTEGER> prop_id, long &long_var);
string SymbolInfoString(const string &name, mql_enum_param<ENUM_SYMBOL_INFO_STRING> prop_id);
bool   SymbolInfoString(const string &name, mql_enum_param<ENUM_SYMBOL_INFO_STRING> prop_id, string &string_var);
bool   SymbolInfoTick(const string &symbol, MqlTick &tick);
bool   SymbolInfoSessionQuote(const string &name, mql_enum_param<ENUM_DAY_OF_WEEK> day_of_week, uint session_index,
                              datetime &from, datetime &to);
bool   SymbolInfoSessionTrade(const string &name, mql_enum_param<ENUM_DAY_OF_WEEK> day_of_week, uint session_index,
                              datetime &from, datetime &to);
bool   SymbolInfoMarginRate(const string &name, mql_enum_param<ENUM_ORDER_TYPE> order_type,
                            double &initial_margin_rate, double &maintenance_margin_rate);
bool   SymbolSelect(const string &name, bool select);
int    SymbolsTotal(bool selected);
string SymbolName(int pos, bool selected);
bool   SymbolExist(const string &name, bool &is_custom);
bool   SymbolIsSynchronized(const string &name);
bool   MarketBookAdd(const string &symbol);
bool   MarketBookRelease(const string &symbol);
bool   MarketBookGet(const string &symbol, mql_array<MqlBookInfo> &book);
double AccountInfoDouble(mql_enum_param<ENUM_ACCOUNT_INFO_DOUBLE> property_id);
long   AccountInfoInteger(mql_enum_param<ENUM_ACCOUNT_INFO_INTEGER> property_id);
string AccountInfoString(mql_enum_param<ENUM_ACCOUNT_INFO_STRING> property_id);

//====================================================================
// Operaciones, posiciones, órdenes e historial
//====================================================================
typedef mql_enum_param<ENUM_ORDER_TYPE> mql_order_type;
bool  OrderCalcMargin(mql_order_type action, const string &symbol, double volume, double price, double &margin);
bool  OrderCalcProfit(mql_order_type action, const string &symbol, double volume, double price_open,
                      double price_close, double &profit);
bool  OrderCheck(const MqlTradeRequest &request, MqlTradeCheckResult &result);
bool  OrderSend(const MqlTradeRequest &request, MqlTradeResult &result);
bool  OrderSendAsync(const MqlTradeRequest &request, MqlTradeResult &result);
int    PositionsTotal();
string PositionGetSymbol(int index);
bool   PositionSelect(const string &symbol);
bool   PositionSelectByTicket(ulong ticket);
ulong  PositionGetTicket(int index);
double PositionGetDouble(mql_enum_param<ENUM_POSITION_PROPERTY_DOUBLE> property_id);
bool   PositionGetDouble(mql_enum_param<ENUM_POSITION_PROPERTY_DOUBLE> property_id, double &double_var);
long   PositionGetInteger(mql_enum_param<ENUM_POSITION_PROPERTY_INTEGER> property_id);
bool   PositionGetInteger(mql_enum_param<ENUM_POSITION_PROPERTY_INTEGER> property_id, long &long_var);
string PositionGetString(mql_enum_param<ENUM_POSITION_PROPERTY_STRING> property_id);
bool   PositionGetString(mql_enum_param<ENUM_POSITION_PROPERTY_STRING> property_id, string &string_var);
int    OrdersTotal();
ulong  OrderGetTicket(int index);
bool   OrderSelect(ulong ticket);
double OrderGetDouble(mql_enum_param<ENUM_ORDER_PROPERTY_DOUBLE> property_id);
bool   OrderGetDouble(mql_enum_param<ENUM_ORDER_PROPERTY_DOUBLE> property_id, double &double_var);
long   OrderGetInteger(mql_enum_param<ENUM_ORDER_PROPERTY_INTEGER> property_id);
bool   OrderGetInteger(mql_enum_param<ENUM_ORDER_PROPERTY_INTEGER> property_id, long &long_var);
string OrderGetString(mql_enum_param<ENUM_ORDER_PROPERTY_STRING> property_id);
bool   OrderGetString(mql_enum_param<ENUM_ORDER_PROPERTY_STRING> property_id, string &string_var);
bool   HistorySelect(datetime from_date, datetime to_date);
bool   HistorySelectByPosition(long position_id);
bool   HistoryOrderSelect(ulong ticket);
int    HistoryOrdersTotal();
ulong  HistoryOrderGetTicket(int index);
double HistoryOrderGetDouble(ulong ticket_number, mql_enum_param<ENUM_ORDER_PROPERTY_DOUBLE> property_id);
bool   HistoryOrderGetDouble(ulong ticket_number, mql_enum_param<ENUM_ORDER_PROPERTY_DOUBLE> property_id, double &double_var);
long   HistoryOrderGetInteger(ulong ticket_number, mql_enum_param<ENUM_ORDER_PROPERTY_INTEGER> property_id);
bool   HistoryOrderGetInteger(ulong ticket_number, mql_enum_param<ENUM_ORDER_PROPERTY_INTEGER> property_id, long &long_var);
string HistoryOrderGetString(ulong ticket_number, mql_enum_param<ENUM_ORDER_PROPERTY_STRING> property_id);
bool   HistoryOrderGetString(ulong ticket_number, mql_enum_param<ENUM_ORDER_PROPERTY_STRING> property_id, string &string_var);
bool   HistoryDealSelect(ulong ticket);
int    HistoryDealsTotal();
ulong  HistoryDealGetTicket(int index);
double HistoryDealGetDouble(ulong ticket_number, mql_enum_param<ENUM_DEAL_PROPERTY_DOUBLE> property_id);
bool   HistoryDealGetDouble(ulong ticket_number, mql_enum_param<ENUM_DEAL_PROPERTY_DOUBLE> property_id, double &double_var);
long   HistoryDealGetInteger(ulong ticket_number, mql_enum_param<ENUM_DEAL_PROPERTY_INTEGER> property_id);
bool   HistoryDealGetInteger(ulong ticket_number, mql_enum_param<ENUM_DEAL_PROPERTY_INTEGER> property_id, long &long_var);
string HistoryDealGetString(ulong ticket_number, mql_enum_param<ENUM_DEAL_PROPERTY_STRING> property_id);
bool   HistoryDealGetString(ulong ticket_number, mql_enum_param<ENUM_DEAL_PROPERTY_STRING> property_id, string &string_var);

//====================================================================
// Variables globales del terminal
//====================================================================
datetime GlobalVariableSet(const string &name, double value);
double   GlobalVariableGet(const string &name);
bool     GlobalVariableGet(const string &name, double &double_var);
bool     GlobalVariableCheck(const string &name);
bool     GlobalVariableDel(const string &name);
bool     GlobalVariableTemp(const string &name);
datetime GlobalVariableTime(const string &name);
string   GlobalVariableName(int index);
int      GlobalVariablesTotal();
int      GlobalVariablesDeleteAll(const string &prefix_name = NULL, datetime limit_data = 0);
bool     GlobalVariableSetOnCondition(const string &name, double value, double check_value);
void     GlobalVariablesFlush();

//====================================================================
// Archivos
//====================================================================
int    FileOpen(const string &file_name, int open_flags, short delimiter = '\t', uint codepage = CP_ACP);
void   FileClose(int file_handle);
template<class... A, mql_if_printable<A...> = 0> uint FileWrite(int file_handle, const A &... args);
uint   FileWriteString(int file_handle, const string &text_string, int length = -1);
uint   FileWriteDouble(int file_handle, double value, int size = DOUBLE_VALUE);
uint   FileWriteInteger(int file_handle, int value, int size = INT_VALUE);
uint   FileWriteLong(int file_handle, long value);
uint   FileWriteFloat(int file_handle, float value);
string FileReadString(int file_handle, int length = -1);
double FileReadNumber(int file_handle);
double FileReadDouble(int file_handle, int size = DOUBLE_VALUE);
int    FileReadInteger(int file_handle, int size = INT_VALUE);
long   FileReadLong(int file_handle);
float  FileReadFloat(int file_handle);
bool   FileReadBool(int file_handle);
datetime FileReadDatetime(int file_handle);
template<class T> uint FileReadArray(int file_handle, mql_array<T> &array, int start = 0, int count = WHOLE_ARRAY);
template<class T> uint FileWriteArray(int file_handle, const mql_array<T> &array, int start = 0, int count = WHOLE_ARRAY);
template<class T> uint FileReadStruct(int file_handle, T &struct_object, int size = -1);
template<class T> uint FileWriteStruct(int file_handle, const T &struct_object, int size = -1);
bool   FileIsEnding(int file_handle);
bool   FileIsLineEnding(int file_handle);
bool   FileIsExist(const string &file_name, int common_flag = 0);
bool   FileDelete(const string &file_name, int common_flag = 0);
void   FileFlush(int file_handle);
bool   FileSeek(int file_handle, long offset, mql_enum_param<ENUM_FILE_POSITION> origin);
ulong  FileSize(int file_handle);
ulong  FileTell(int file_handle);
bool   FileCopy(const string &src_file_name, int common_flag, const string &dst_file_name, int mode_flags);
bool   FileMove(const string &src_file_name, int common_flag, const string &dst_file_name, int mode_flags);
long   FileGetInteger(int file_handle, int property_id);
long   FileGetInteger(const string &file_name, int property_id, bool common_folder = false);
long   FileFindFirst(const string &file_filter, string &returned_filename, int common_flag = 0);
bool   FileFindNext(long search_handle, string &returned_filename);
void   FileFindClose(long search_handle);
bool   FolderCreate(const string &folder_name, int common_flag = 0);
bool   FolderDelete(const string &folder_name, int common_flag = 0);
bool   FolderClean(const string &folder_name, int common_flag = 0);

//====================================================================
// Gráficos y objetos gráficos
//====================================================================
long   ChartID();
void   ChartRedraw(long chart_id = 0);
string ChartSymbol(long chart_id = 0);
ENUM_TIMEFRAMES ChartPeriod(long chart_id = 0);
long   ChartOpen(const string &symbol, mql_tf period);
bool   ChartClose(long chart_id = 0);
long   ChartFirst();
long   ChartNext(long chart_id);
bool   ChartSetSymbolPeriod(long chart_id, const string &symbol, mql_tf period);
int    ChartWindowFind();
int    ChartWindowFind(long chart_id, const string &indicator_shortname);
bool   ChartSetInteger(long chart_id, mql_enum_param<ENUM_CHART_PROPERTY_INTEGER> prop_id, long value);
bool   ChartSetInteger(long chart_id, mql_enum_param<ENUM_CHART_PROPERTY_INTEGER> prop_id, int sub_window, long value);
bool   ChartSetDouble(long chart_id, mql_enum_param<ENUM_CHART_PROPERTY_DOUBLE> prop_id, double value);
bool   ChartSetString(long chart_id, mql_enum_param<ENUM_CHART_PROPERTY_STRING> prop_id, const string &str_value);
long   ChartGetInteger(long chart_id, mql_enum_param<ENUM_CHART_PROPERTY_INTEGER> prop_id, int sub_window = 0);
bool   ChartGetInteger(long chart_id, mql_enum_param<ENUM_CHART_PROPERTY_INTEGER> prop_id, int sub_window, long &long_var);
double ChartGetDouble(long chart_id, mql_enum_param<ENUM_CHART_PROPERTY_DOUBLE> prop_id, int sub_window = 0);
bool   ChartGetDouble(long chart_id, mql_enum_param<ENUM_CHART_PROPERTY_DOUBLE> prop_id, int sub_window, double &double_var);
string ChartGetString(long chart_id, mql_enum_param<ENUM_CHART_PROPERTY_STRING> prop_id);
bool   ChartGetString(long chart_id, mql_enum_param<ENUM_CHART_PROPERTY_STRING> prop_id, string &string_var);
bool   ChartNavigate(long chart_id, mql_enum_param<ENUM_CHART_POSITION> position, int shift = 0);
bool   ChartTimePriceToXY(long chart_id, int sub_window, datetime time, double price, int &x, int &y);
bool   ChartXYToTimePrice(long chart_id, int x, int y, int &sub_window, datetime &time, double &price);
bool   ChartApplyTemplate(long chart_id, const string &filename);
bool   ChartSaveTemplate(long chart_id, const string &filename);
bool   ChartScreenShot(long chart_id, const string &filename, int width, int height, mql_enum_param<ENUM_ALIGN_MODE> align_mode = ALIGN_RIGHT);
bool   ChartIndicatorAdd(long chart_id, int sub_window, int indicator_handle);
bool   ChartIndicatorDelete(long chart_id, int sub_window, const string &indicator_shortname);

bool   ObjectCreate(long chart_id, const string &object_name, mql_enum_param<ENUM_OBJECT> object_type, int sub_window,
                    datetime time1, double price1,
                    datetime time2 = 0, double price2 = 0, datetime time3 = 0, double price3 = 0,
                    datetime time4 = 0, double price4 = 0, datetime time5 = 0, double price5 = 0);
bool   ObjectDelete(long chart_id, const string &object_name);
int    ObjectsDeleteAll(long chart_id, int sub_window = -1, int object_type = -1);
int    ObjectsDeleteAll(long chart_id, const string &prefix, int sub_window = -1, int object_type = -1);
int    ObjectFind(long chart_id, const string &object_name);
int    ObjectsTotal(long chart_id, int sub_window = -1, int type = -1);
string ObjectName(long chart_id, int pos, int sub_window = -1, int type = -1);
bool   ObjectMove(long chart_id, const string &object_name, int point_index, datetime time, double price);
datetime ObjectGetTimeByValue(long chart_id, const string &object_name, double value, int line_id = 0);
double ObjectGetValueByTime(long chart_id, const string &object_name, datetime time, int line_id = 0);
typedef mql_enum_param<ENUM_OBJECT_PROPERTY_INTEGER> mql_objprop_i;
typedef mql_enum_param<ENUM_OBJECT_PROPERTY_DOUBLE>  mql_objprop_d;
typedef mql_enum_param<ENUM_OBJECT_PROPERTY_STRING>  mql_objprop_s;
bool   ObjectSetInteger(long chart_id, const string &object_name, mql_objprop_i prop_id, long prop_value);
bool   ObjectSetInteger(long chart_id, const string &object_name, mql_objprop_i prop_id, int prop_modifier, long prop_value);
bool   ObjectSetDouble(long chart_id, const string &object_name, mql_objprop_d prop_id, double prop_value);
bool   ObjectSetDouble(long chart_id, const string &object_name, mql_objprop_d prop_id, int prop_modifier, double prop_value);
bool   ObjectSetString(long chart_id, const string &object_name, mql_objprop_s prop_id, const string &prop_value);
bool   ObjectSetString(long chart_id, const string &object_name, mql_objprop_s prop_id, int prop_modifier, const string &prop_value);
long   ObjectGetInteger(long chart_id, const string &object_name, mql_objprop_i prop_id, int prop_modifier = 0);
bool   ObjectGetInteger(long chart_id, const string &object_name, mql_objprop_i prop_id, int prop_modifier, long &long_var);
double ObjectGetDouble(long chart_id, const string &object_name, mql_objprop_d prop_id, int prop_modifier = 0);
bool   ObjectGetDouble(long chart_id, const string &object_name, mql_objprop_d prop_id, int prop_modifier, double &double_var);
string ObjectGetString(long chart_id, const string &object_name, mql_objprop_s prop_id, int prop_modifier = 0);
bool   ObjectGetString(long chart_id, const string &object_name, mql_objprop_s prop_id, int prop_modifier, string &string_var);
bool   TextSetFont(const string &name, int size, uint flags = 0, int orientation = 0);
bool   TextOut(const string &text, int x, int y, uint anchor, mql_array<uint> &data, uint width, uint height,
               uint color_value, int color_format);
bool   TextGetSize(const string &text, uint &width, uint &height);

//====================================================================
// Eventos y probador
//====================================================================
bool   EventSetTimer(int seconds);
bool   EventSetMillisecondTimer(int milliseconds);
void   EventKillTimer();
bool   EventChartCustom(long chart_id, ushort custom_event_id, long lparam, double dparam, const string &sparam);
double TesterStatistics(mql_enum_param<ENUM_STATISTICS> statistic_id);
void   TesterStop();
bool   TesterWithdrawal(double money);
bool   TesterDeposit(double money);
void   TesterHideIndicators(bool hide);

//====================================================================
// Indicadores personalizados (OnCalculate)
//====================================================================
enum ENUM_INDEXBUFFER_TYPE { INDICATOR_DATA, INDICATOR_COLOR_INDEX, INDICATOR_CALCULATIONS };
enum ENUM_PLOT_PROPERTY_INTEGER { PLOT_ARROW, PLOT_ARROW_SHIFT, PLOT_DRAW_BEGIN, PLOT_DRAW_TYPE, PLOT_SHOW_DATA,
  PLOT_SHIFT, PLOT_LINE_STYLE, PLOT_LINE_WIDTH, PLOT_COLOR_INDEXES, PLOT_LINE_COLOR };
enum ENUM_PLOT_PROPERTY_DOUBLE { PLOT_EMPTY_VALUE };
enum ENUM_PLOT_PROPERTY_STRING { PLOT_LABEL };
enum ENUM_CUSTOMIND_PROPERTY_INTEGER { INDICATOR_DIGITS, INDICATOR_HEIGHT, INDICATOR_LEVELS, INDICATOR_LEVELCOLOR,
  INDICATOR_LEVELSTYLE, INDICATOR_LEVELWIDTH, INDICATOR_FIXED_MINIMUM, INDICATOR_FIXED_MAXIMUM };
enum ENUM_CUSTOMIND_PROPERTY_DOUBLE { INDICATOR_MINIMUM, INDICATOR_MAXIMUM, INDICATOR_LEVELVALUE };
enum ENUM_CUSTOMIND_PROPERTY_STRING { INDICATOR_SHORTNAME, INDICATOR_LEVELTEXT };
enum ENUM_DRAW_TYPE { DRAW_NONE, DRAW_LINE, DRAW_SECTION, DRAW_HISTOGRAM, DRAW_HISTOGRAM2, DRAW_ARROW, DRAW_ZIGZAG,
  DRAW_FILLING, DRAW_BARS, DRAW_CANDLES, DRAW_COLOR_LINE, DRAW_COLOR_SECTION, DRAW_COLOR_HISTOGRAM,
  DRAW_COLOR_HISTOGRAM2, DRAW_COLOR_ARROW, DRAW_COLOR_ZIGZAG, DRAW_COLOR_BARS, DRAW_COLOR_CANDLES };
bool SetIndexBuffer(int index, mql_array<double> &buffer, mql_enum_param<ENUM_INDEXBUFFER_TYPE> data_type = INDICATOR_DATA);
bool IndicatorSetDouble(mql_enum_param<ENUM_CUSTOMIND_PROPERTY_DOUBLE> prop_id, double prop_value);
bool IndicatorSetDouble(mql_enum_param<ENUM_CUSTOMIND_PROPERTY_DOUBLE> prop_id, int prop_modifier, double prop_value);
bool IndicatorSetInteger(mql_enum_param<ENUM_CUSTOMIND_PROPERTY_INTEGER> prop_id, int prop_value);
bool IndicatorSetInteger(mql_enum_param<ENUM_CUSTOMIND_PROPERTY_INTEGER> prop_id, int prop_modifier, int prop_value);
bool IndicatorSetString(mql_enum_param<ENUM_CUSTOMIND_PROPERTY_STRING> prop_id, const string &prop_value);
bool IndicatorSetString(mql_enum_param<ENUM_CUSTOMIND_PROPERTY_STRING> prop_id, int prop_modifier, const string &prop_value);
bool PlotIndexSetDouble(int plot_index, mql_enum_param<ENUM_PLOT_PROPERTY_DOUBLE> prop_id, double prop_value);
bool PlotIndexSetInteger(int plot_index, mql_enum_param<ENUM_PLOT_PROPERTY_INTEGER> prop_id, int prop_value);
bool PlotIndexSetInteger(int plot_index, mql_enum_param<ENUM_PLOT_PROPERTY_INTEGER> prop_id, int prop_modifier, int prop_value);
bool PlotIndexSetString(int plot_index, mql_enum_param<ENUM_PLOT_PROPERTY_STRING> prop_id, const string &prop_value);
int  PlotIndexGetInteger(int plot_index, mql_enum_param<ENUM_PLOT_PROPERTY_INTEGER> prop_id, int prop_modifier = 0);

//====================================================================
// Otros
//====================================================================
constexpr int MB_OK = 0, MB_OKCANCEL = 1, MB_ABORTRETRYIGNORE = 2, MB_YESNOCANCEL = 3, MB_YESNO = 4,
              MB_RETRYCANCEL = 5, MB_CANCELTRYCONTINUE = 6, MB_ICONSTOP = 0x10, MB_ICONERROR = 0x10,
              MB_ICONHAND = 0x10, MB_ICONQUESTION = 0x20, MB_ICONEXCLAMATION = 0x30, MB_ICONWARNING = 0x30,
              MB_ICONINFORMATION = 0x40, MB_ICONASTERISK = 0x40, MB_DEFBUTTON1 = 0, MB_DEFBUTTON2 = 0x100,
              MB_DEFBUTTON3 = 0x200, MB_DEFBUTTON4 = 0x300;
constexpr int IDOK = 1, IDCANCEL = 2, IDABORT = 3, IDRETRY = 4, IDIGNORE = 5, IDYES = 6, IDNO = 7,
              IDTRYAGAIN = 10, IDCONTINUE = 11;
int    MessageBox(const string &text, const string &caption = NULL, int flags = 0);
uint   ColorToARGB(color clr, uchar alpha = 255);
int    UninitializeReason();
int    ChartIndicatorGet(long chart_id, int sub_window, const string &indicator_shortname);
int    ChartIndicatorsTotal(long chart_id, int sub_window);
string ChartIndicatorName(long chart_id, int sub_window, int index);
enum ENUM_CRYPT_METHOD { CRYPT_BASE64, CRYPT_AES128, CRYPT_AES256, CRYPT_DES, CRYPT_HASH_SHA1, CRYPT_HASH_SHA256,
  CRYPT_HASH_MD5, CRYPT_ARCH_ZIP };
int    CryptEncode(mql_enum_param<ENUM_CRYPT_METHOD> method, const mql_array<uchar> &data, const mql_array<uchar> &key,
                   mql_array<uchar> &result);
int    CryptDecode(mql_enum_param<ENUM_CRYPT_METHOD> method, const mql_array<uchar> &data, const mql_array<uchar> &key,
                   mql_array<uchar> &result);

#endif // MQL5CHECK_SHIM_CORE

//====================================================================
// Biblioteca Estándar: solo se declara lo que el programa incluyó.
// Trade.mqh incluye Object.mqh, OrderInfo.mqh, HistoryOrderInfo.mqh,
// PositionInfo.mqh y DealInfo.mqh (igual que en MetaTrader 5).
//====================================================================
#if (defined(MQL5CHECK_INC_TRADE) || defined(MQL5CHECK_INC_POSITIONINFO) || defined(MQL5CHECK_INC_ORDERINFO) || \
     defined(MQL5CHECK_INC_HISTORYORDERINFO) || defined(MQL5CHECK_INC_DEALINFO) || defined(MQL5CHECK_INC_SYMBOLINFO) || \
     defined(MQL5CHECK_INC_ACCOUNTINFO) || defined(MQL5CHECK_INC_ARRAYS) || defined(MQL5CHECK_INC_OBJECT)) && \
    !defined(MQL5CHECK_SHIM_OBJECT)
#define MQL5CHECK_SHIM_OBJECT
class CObject {
public:
  CObject();
  virtual ~CObject();
  CObject *Prev() const;
  void     Prev(CObject *node);
  CObject *Next() const;
  void     Next(CObject *node);
  virtual bool Save(const int file_handle);
  virtual bool Load(const int file_handle);
  virtual int  Type() const;
  virtual int  Compare(const CObject *node, const int mode = 0) const;
};
#endif

#if defined(MQL5CHECK_INC_TRADE) && !defined(MQL5CHECK_SHIM_TRADE)
#define MQL5CHECK_SHIM_TRADE
#ifndef MQL5CHECK_INC_POSITIONINFO
#define MQL5CHECK_INC_POSITIONINFO
#endif
#ifndef MQL5CHECK_INC_ORDERINFO
#define MQL5CHECK_INC_ORDERINFO
#endif
#ifndef MQL5CHECK_INC_HISTORYORDERINFO
#define MQL5CHECK_INC_HISTORYORDERINFO
#endif
#ifndef MQL5CHECK_INC_DEALINFO
#define MQL5CHECK_INC_DEALINFO
#endif
enum ENUM_LOG_LEVELS { LOG_LEVEL_NO_LOGS, LOG_LEVEL_ERRORS, LOG_LEVEL_ALL };
class CTrade : public CObject {
public:
  CTrade();
  ~CTrade();
  void   LogLevel(const mql_enum_param<ENUM_LOG_LEVELS> log_level);
  void   Request(MqlTradeRequest &request) const;
  ENUM_TRADE_REQUEST_ACTIONS RequestAction() const;
  string RequestActionDescription() const;
  ulong  RequestMagic() const;
  ulong  RequestOrder() const;
  ulong  RequestPosition() const;
  ulong  RequestPositionBy() const;
  string RequestSymbol() const;
  double RequestVolume() const;
  double RequestPrice() const;
  double RequestStopLimit() const;
  double RequestSL() const;
  double RequestTP() const;
  ulong  RequestDeviation() const;
  ENUM_ORDER_TYPE RequestType() const;
  string RequestTypeDescription() const;
  ENUM_ORDER_TYPE_FILLING RequestTypeFilling() const;
  string RequestTypeFillingDescription() const;
  ENUM_ORDER_TYPE_TIME RequestTypeTime() const;
  string RequestTypeTimeDescription() const;
  datetime RequestExpiration() const;
  string RequestComment() const;
  void   Result(MqlTradeResult &result) const;
  uint   ResultRetcode() const;
  string ResultRetcodeDescription() const;
  int    ResultRetcodeExternal() const;
  ulong  ResultDeal() const;
  ulong  ResultOrder() const;
  double ResultVolume() const;
  double ResultPrice() const;
  double ResultBid() const;
  double ResultAsk() const;
  string ResultComment() const;
  void   CheckResult(MqlTradeCheckResult &check_result) const;
  uint   CheckResultRetcode() const;
  string CheckResultRetcodeDescription() const;
  double CheckResultBalance() const;
  double CheckResultEquity() const;
  double CheckResultProfit() const;
  double CheckResultMargin() const;
  double CheckResultMarginFree() const;
  double CheckResultMarginLevel() const;
  string CheckResultComment() const;
  void   SetAsyncMode(const bool mode);
  void   SetExpertMagicNumber(const ulong magic);
  void   SetDeviationInPoints(const ulong deviation);
  void   SetTypeFilling(const mql_enum_param<ENUM_ORDER_TYPE_FILLING> filling);
  bool   SetTypeFillingBySymbol(const string &symbol);
  void   SetMarginMode();
  bool   PositionOpen(const string &symbol, const mql_enum_param<ENUM_ORDER_TYPE> order_type, const double volume,
                      const double price, const double sl, const double tp, const string &comment = "");
  bool   PositionModify(const string &symbol, const double sl, const double tp);
  bool   PositionModify(const ulong ticket, const double sl, const double tp);
  bool   PositionClose(const string &symbol, const ulong deviation = ULONG_MAX);
  bool   PositionClose(const ulong ticket, const ulong deviation = ULONG_MAX);
  bool   PositionCloseBy(const ulong ticket, const ulong ticket_by);
  bool   PositionClosePartial(const string &symbol, const double volume, const ulong deviation = ULONG_MAX);
  bool   PositionClosePartial(const ulong ticket, const double volume, const ulong deviation = ULONG_MAX);
  bool   OrderOpen(const string &symbol, const mql_enum_param<ENUM_ORDER_TYPE> order_type, const double volume,
                   const double limit_price, const double price, const double sl, const double tp,
                   mql_enum_param<ENUM_ORDER_TYPE_TIME> type_time = ORDER_TIME_GTC, const datetime expiration = 0,
                   const string &comment = "");
  bool   OrderModify(const ulong ticket, const double price, const double sl, const double tp,
                     const mql_enum_param<ENUM_ORDER_TYPE_TIME> type_time, const datetime expiration,
                     const double stoplimit = 0.0);
  bool   OrderDelete(const ulong ticket);
  bool   Buy(const double volume, const string &symbol = NULL, double price = 0.0, const double sl = 0.0,
             const double tp = 0.0, const string &comment = "");
  bool   Sell(const double volume, const string &symbol = NULL, double price = 0.0, const double sl = 0.0,
              const double tp = 0.0, const string &comment = "");
  bool   BuyLimit(const double volume, const double price, const string &symbol = NULL, const double sl = 0.0,
                  const double tp = 0.0, const mql_enum_param<ENUM_ORDER_TYPE_TIME> type_time = ORDER_TIME_GTC,
                  const datetime expiration = 0, const string &comment = "");
  bool   BuyStop(const double volume, const double price, const string &symbol = NULL, const double sl = 0.0,
                 const double tp = 0.0, const mql_enum_param<ENUM_ORDER_TYPE_TIME> type_time = ORDER_TIME_GTC,
                 const datetime expiration = 0, const string &comment = "");
  bool   SellLimit(const double volume, const double price, const string &symbol = NULL, const double sl = 0.0,
                   const double tp = 0.0, const mql_enum_param<ENUM_ORDER_TYPE_TIME> type_time = ORDER_TIME_GTC,
                   const datetime expiration = 0, const string &comment = "");
  bool   SellStop(const double volume, const double price, const string &symbol = NULL, const double sl = 0.0,
                  const double tp = 0.0, const mql_enum_param<ENUM_ORDER_TYPE_TIME> type_time = ORDER_TIME_GTC,
                  const datetime expiration = 0, const string &comment = "");
  virtual double CheckVolume(const string &symbol, double volume, double price, mql_enum_param<ENUM_ORDER_TYPE> order_type);
  virtual bool   OrderCheck(const MqlTradeRequest &request, MqlTradeCheckResult &check_result);
  virtual bool   OrderSend(const MqlTradeRequest &request, MqlTradeResult &result);
  void   PrintRequest() const;
  void   PrintResult() const;
  string FormatRequest(string &str, const MqlTradeRequest &request) const;
  string FormatRequestResult(string &str, const MqlTradeRequest &request, const MqlTradeResult &result) const;
};
#endif

#if defined(MQL5CHECK_INC_POSITIONINFO) && !defined(MQL5CHECK_SHIM_POSITIONINFO)
#define MQL5CHECK_SHIM_POSITIONINFO
class CPositionInfo : public CObject {
public:
  CPositionInfo();
  ~CPositionInfo();
  ulong    Ticket() const;
  datetime Time() const;
  ulong    TimeMsc() const;
  datetime TimeUpdate() const;
  ulong    TimeUpdateMsc() const;
  ENUM_POSITION_TYPE PositionType() const;
  string   TypeDescription() const;
  long     Magic() const;
  long     Identifier() const;
  double   Volume() const;
  double   PriceOpen() const;
  double   StopLoss() const;
  double   TakeProfit() const;
  double   PriceCurrent() const;
  double   Commission() const;
  double   Swap() const;
  double   Profit() const;
  string   Symbol() const;
  string   Comment() const;
  bool     InfoInteger(const mql_enum_param<ENUM_POSITION_PROPERTY_INTEGER> prop_id, long &var) const;
  bool     InfoDouble(const mql_enum_param<ENUM_POSITION_PROPERTY_DOUBLE> prop_id, double &var) const;
  bool     InfoString(const mql_enum_param<ENUM_POSITION_PROPERTY_STRING> prop_id, string &var) const;
  string   FormatType(string &str, const uint type) const;
  string   FormatPosition(string &str) const;
  bool     Select(const string &symbol);
  bool     SelectByMagic(const string &symbol, const ulong magic);
  bool     SelectByTicket(const ulong ticket);
  bool     SelectByIndex(const int index);
  void     StoreState();
  bool     CheckState();
};
#endif

#if defined(MQL5CHECK_INC_ORDERINFO) && !defined(MQL5CHECK_SHIM_ORDERINFO)
#define MQL5CHECK_SHIM_ORDERINFO
class COrderInfo : public CObject {
public:
  COrderInfo();
  ~COrderInfo();
  ulong    Ticket() const;
  datetime TimeSetup() const;
  ulong    TimeSetupMsc() const;
  datetime TimeDone() const;
  ulong    TimeDoneMsc() const;
  ENUM_ORDER_TYPE OrderType() const;
  string   TypeDescription() const;
  ENUM_ORDER_STATE State() const;
  string   StateDescription() const;
  datetime TimeExpiration() const;
  ENUM_ORDER_TYPE_FILLING TypeFilling() const;
  string   TypeFillingDescription() const;
  ENUM_ORDER_TYPE_TIME TypeTime() const;
  string   TypeTimeDescription() const;
  long     Magic() const;
  long     PositionId() const;
  long     PositionById() const;
  double   VolumeInitial() const;
  double   VolumeCurrent() const;
  double   PriceOpen() const;
  double   StopLoss() const;
  double   TakeProfit() const;
  double   PriceCurrent() const;
  double   PriceStopLimit() const;
  string   Symbol() const;
  string   Comment() const;
  string   ExternalId() const;
  bool     InfoInteger(const mql_enum_param<ENUM_ORDER_PROPERTY_INTEGER> prop_id, long &var) const;
  bool     InfoDouble(const mql_enum_param<ENUM_ORDER_PROPERTY_DOUBLE> prop_id, double &var) const;
  bool     InfoString(const mql_enum_param<ENUM_ORDER_PROPERTY_STRING> prop_id, string &var) const;
  bool     Select();
  bool     Select(const ulong ticket);
  bool     SelectByIndex(const int index);
  void     StoreState();
  bool     CheckState();
};
#endif

#if defined(MQL5CHECK_INC_HISTORYORDERINFO) && !defined(MQL5CHECK_SHIM_HISTORYORDERINFO)
#define MQL5CHECK_SHIM_HISTORYORDERINFO
class CHistoryOrderInfo : public CObject {
public:
  CHistoryOrderInfo();
  ~CHistoryOrderInfo();
  datetime TimeSetup() const;
  ulong    TimeSetupMsc() const;
  datetime TimeDone() const;
  ulong    TimeDoneMsc() const;
  ENUM_ORDER_TYPE OrderType() const;
  string   TypeDescription() const;
  ENUM_ORDER_STATE State() const;
  string   StateDescription() const;
  datetime TimeExpiration() const;
  ENUM_ORDER_TYPE_FILLING TypeFilling() const;
  ENUM_ORDER_TYPE_TIME TypeTime() const;
  long     Magic() const;
  long     PositionId() const;
  double   VolumeInitial() const;
  double   VolumeCurrent() const;
  double   PriceOpen() const;
  double   StopLoss() const;
  double   TakeProfit() const;
  double   PriceCurrent() const;
  double   PriceStopLimit() const;
  string   Symbol() const;
  string   Comment() const;
  string   ExternalId() const;
  void     Ticket(const ulong ticket);
  ulong    Ticket() const;
  bool     SelectByIndex(const int index);
};
#endif

#if defined(MQL5CHECK_INC_DEALINFO) && !defined(MQL5CHECK_SHIM_DEALINFO)
#define MQL5CHECK_SHIM_DEALINFO
class CDealInfo : public CObject {
public:
  CDealInfo();
  ~CDealInfo();
  long     Order() const;
  datetime Time() const;
  ulong    TimeMsc() const;
  ENUM_DEAL_TYPE DealType() const;
  string   TypeDescription() const;
  ENUM_DEAL_ENTRY Entry() const;
  string   EntryDescription() const;
  long     Magic() const;
  long     PositionId() const;
  double   Volume() const;
  double   Price() const;
  double   Commission() const;
  double   Swap() const;
  double   Profit() const;
  string   Symbol() const;
  string   Comment() const;
  string   ExternalId() const;
  bool     InfoInteger(const mql_enum_param<ENUM_DEAL_PROPERTY_INTEGER> prop_id, long &var) const;
  bool     InfoDouble(const mql_enum_param<ENUM_DEAL_PROPERTY_DOUBLE> prop_id, double &var) const;
  bool     InfoString(const mql_enum_param<ENUM_DEAL_PROPERTY_STRING> prop_id, string &var) const;
  void     Ticket(const ulong ticket);
  ulong    Ticket() const;
  bool     SelectByIndex(const int index);
};
#endif

#if defined(MQL5CHECK_INC_SYMBOLINFO) && !defined(MQL5CHECK_SHIM_SYMBOLINFO)
#define MQL5CHECK_SHIM_SYMBOLINFO
class CSymbolInfo : public CObject {
public:
  CSymbolInfo();
  ~CSymbolInfo();
  string   Name() const;
  bool     Name(const string &name);
  bool     Refresh();
  bool     RefreshRates();
  bool     Select() const;
  bool     Select(const bool select);
  bool     IsSynchronized() const;
  ulong    Volume() const;
  ulong    VolumeHigh() const;
  ulong    VolumeLow() const;
  datetime Time() const;
  int      Spread() const;
  bool     SpreadFloat() const;
  int      TicksBookDepth() const;
  int      StopsLevel() const;
  int      FreezeLevel() const;
  double   Bid() const;
  double   BidHigh() const;
  double   BidLow() const;
  double   Ask() const;
  double   AskHigh() const;
  double   AskLow() const;
  double   Last() const;
  double   LastHigh() const;
  double   LastLow() const;
  ENUM_SYMBOL_CALC_MODE TradeCalcMode() const;
  string   TradeCalcModeDescription() const;
  ENUM_SYMBOL_TRADE_MODE TradeMode() const;
  string   TradeModeDescription() const;
  ENUM_SYMBOL_TRADE_EXECUTION TradeExecution() const;
  string   TradeExecutionDescription() const;
  ENUM_SYMBOL_SWAP_MODE SwapMode() const;
  string   SwapModeDescription() const;
  ENUM_DAY_OF_WEEK SwapRollover3days() const;
  string   SwapRollover3daysDescription() const;
  datetime StartTime() const;
  datetime ExpirationTime() const;
  int      ExpirationMode() const;
  int      FillingMode() const;
  int      OrderMode() const;
  double   MarginInitial() const;
  double   MarginMaintenance() const;
  double   MarginHedged() const;
  double   TickValue() const;
  double   TickValueProfit() const;
  double   TickValueLoss() const;
  double   TickSize() const;
  double   ContractSize() const;
  double   LotsMin() const;
  double   LotsMax() const;
  double   LotsStep() const;
  double   LotsLimit() const;
  double   SwapLong() const;
  double   SwapShort() const;
  string   CurrencyBase() const;
  string   CurrencyProfit() const;
  string   CurrencyMargin() const;
  string   Bank() const;
  string   Description() const;
  string   Path() const;
  long     SessionDeals() const;
  long     SessionBuyOrders() const;
  long     SessionSellOrders() const;
  double   SessionTurnover() const;
  double   SessionInterest() const;
  double   SessionBuyOrdersVolume() const;
  double   SessionSellOrdersVolume() const;
  double   SessionOpen() const;
  double   SessionClose() const;
  double   SessionAW() const;
  double   SessionPriceSettlement() const;
  double   SessionPriceLimitMin() const;
  double   SessionPriceLimitMax() const;
  int      Digits() const;
  double   Point() const;
  bool     InfoInteger(const mql_enum_param<ENUM_SYMBOL_INFO_INTEGER> prop_id, long &var) const;
  bool     InfoDouble(const mql_enum_param<ENUM_SYMBOL_INFO_DOUBLE> prop_id, double &var) const;
  bool     InfoString(const mql_enum_param<ENUM_SYMBOL_INFO_STRING> prop_id, string &var) const;
  double   NormalizePrice(const double price) const;
  bool     CheckMarketWatch();
};
#endif

#if defined(MQL5CHECK_INC_ACCOUNTINFO) && !defined(MQL5CHECK_SHIM_ACCOUNTINFO)
#define MQL5CHECK_SHIM_ACCOUNTINFO
class CAccountInfo : public CObject {
public:
  CAccountInfo();
  ~CAccountInfo();
  long     Login() const;
  ENUM_ACCOUNT_TRADE_MODE TradeMode() const;
  string   TradeModeDescription() const;
  long     Leverage() const;
  ENUM_ACCOUNT_STOPOUT_MODE StopoutMode() const;
  string   StopoutModeDescription() const;
  ENUM_ACCOUNT_MARGIN_MODE MarginMode() const;
  string   MarginModeDescription() const;
  bool     TradeAllowed() const;
  bool     TradeExpert() const;
  int      LimitOrders() const;
  double   Balance() const;
  double   Credit() const;
  double   Profit() const;
  double   Equity() const;
  double   Margin() const;
  double   FreeMargin() const;
  double   MarginLevel() const;
  double   MarginCall() const;
  double   MarginStopOut() const;
  string   Name() const;
  string   Server() const;
  string   Currency() const;
  string   Company() const;
  long     InfoInteger(const mql_enum_param<ENUM_ACCOUNT_INFO_INTEGER> prop_id) const;
  double   InfoDouble(const mql_enum_param<ENUM_ACCOUNT_INFO_DOUBLE> prop_id) const;
  string   InfoString(const mql_enum_param<ENUM_ACCOUNT_INFO_STRING> prop_id) const;
  double   OrderProfitCheck(const string &symbol, const mql_enum_param<ENUM_ORDER_TYPE> trade_operation,
                            const double volume, const double price_open, const double price_close) const;
  double   MarginCheck(const string &symbol, const mql_enum_param<ENUM_ORDER_TYPE> trade_operation,
                       const double volume, const double price) const;
  double   FreeMarginCheck(const string &symbol, const mql_enum_param<ENUM_ORDER_TYPE> trade_operation,
                           const double volume, const double price) const;
  double   MaxLotCheck(const string &symbol, const mql_enum_param<ENUM_ORDER_TYPE> trade_operation,
                       const double price, const double percent = 100) const;
};
#endif

#if defined(MQL5CHECK_INC_ARRAYS) && !defined(MQL5CHECK_SHIM_ARRAYS)
#define MQL5CHECK_SHIM_ARRAYS
class CArray : public CObject {
public:
  int  Step() const;
  bool Step(const int step);
  int  Total() const;
  int  Available() const;
  int  Max() const;
  bool IsSorted(const int mode = 0) const;
  int  SortMode() const;
  void Clear();
  void Sort(const int mode = 0);
};
#define MQL5CHECK_ARRAY_CLASS(CLS, T) \
  class CLS : public CArray { public: CLS(); ~CLS(); \
    bool Reserve(const int size); bool Resize(const int size); bool Shutdown(); \
    bool Add(const T element); bool AddArray(const mql_array<T> &src); bool AddArray(const CLS *src); \
    bool Insert(const T element, const int pos); bool AssignArray(const mql_array<T> &src); \
    bool Update(const int index, const T element); bool Shift(const int index, const int shift); \
    bool Delete(const int index); bool DeleteRange(int from, int to); \
    T At(const int index) const; T operator[](const int index) const; \
    int Search(const T element) const; int SearchGreat(const T element) const; int SearchLess(const T element) const; \
    int Minimum(const int start, const int count) const; int Maximum(const int start, const int count) const; \
    bool InsertSort(const T element); };
MQL5CHECK_ARRAY_CLASS(CArrayInt, int)
MQL5CHECK_ARRAY_CLASS(CArrayLong, long)
MQL5CHECK_ARRAY_CLASS(CArrayDouble, double)
MQL5CHECK_ARRAY_CLASS(CArrayString, string)
#undef MQL5CHECK_ARRAY_CLASS
class CArrayObj : public CArray {
public:
  CArrayObj();
  ~CArrayObj();
  bool FreeMode() const;
  void FreeMode(const bool mode);
  bool Reserve(const int size);
  bool Resize(const int size);
  bool Shutdown();
  bool Add(CObject *element);
  bool AddArray(const CArrayObj *src);
  bool Insert(CObject *element, const int pos);
  bool AssignArray(const CArrayObj *src);
  bool Update(const int index, CObject *element);
  bool Shift(const int index, const int shift);
  CObject *Detach(const int index);
  bool Delete(const int index);
  bool DeleteRange(int from, int to);
  CObject *At(const int index) const;
  int  Search(const CObject *element) const;
  bool InsertSort(CObject *element);
  virtual bool CreateElement(const int index);
};
#endif
