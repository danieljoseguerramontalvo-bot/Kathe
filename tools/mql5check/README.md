# mql5check: comprobador estático de MQL5 (sin MetaEditor)

`mql5check.py` detecta **errores de compilación típicos de MQL5** sin abrir MetaTrader: traduce el
`.mq5` a C++17, lo compila con `g++` contra `mql5_shim.hpp` (una copia en forma de *declaraciones*
de la API de MQL5) y muestra los errores con el **archivo y la línea originales del `.mq5`**.

> **No es un compilador de MQL5.** Es un filtro previo para no mandar código roto a quien lo
> pega en MetaEditor. **MetaEditor sigue siendo la autoridad**: que `mql5check` no dé errores no
> garantiza que MetaEditor compile, y (raramente) puede marcar como error algo que MetaEditor acepta.
> Ante la duda, gana MetaEditor; si hay discrepancia, conviene corregir el shim (ver más abajo).

## Uso

Requisitos: Python 3 y `g++` con C++17 (probado con g++ 13 en Ubuntu 24.04). No hace falta Wine.

```bash
python3 tools/mql5check/mql5check.py MQL5/Experts/EMA_Cross_DayTrade.mq5
python3 tools/mql5check/mql5check.py MQL5/Experts/*.mq5 MQL5/Experts/archive/*.mq5
```

Opciones:

| Opción | Efecto |
|---|---|
| `--keep` | conserva el `.cpp` generado (imprime su ruta) para depurar la traducción |
| `--strict` | las advertencias también cuentan como fallo (código de salida 1) |
| `--no-warnings` | muestra solo errores |
| `--no-source` | no imprime la línea de código bajo cada diagnóstico |
| `--notes` | muestra las notas de g++ (candidatos de una función, etc.) |
| `--syntax-only` | usa `g++ -fsyntax-only` puro (más rápido, pero no detecta "no todos los caminos devuelven un valor") |
| `--cxx RUTA` | otro compilador (o variable de entorno `MQL5CHECK_CXX`) |
| `--debug` | muestra la salida cruda de g++ |

Código de salida: `0` sin errores · `1` hay errores (o advertencias con `--strict`) · `2` fallo de la
herramienta (no hay g++, el archivo no existe...).

Ejemplo de salida:

```
EMA_Cross_DayTrade.mq5:475: error: no matching function for call to 'CopyBuffer(int&, int, int, double[]&)'
      475 |    if(CopyBuffer(g_atrHandle, 0, 1, atr) != 1)
          pista: ninguna versión de la función acepta estos argumentos: revise el número y los tipos
EMA_Cross_DayTrade.mq5: 1 error(es), 0 advertencia(s)
```

Los mensajes de error son los de g++ (en inglés, con los tipos internos traducidos a nombres de
MQL5: `double[]`, `ENUM_TIMEFRAMES`, `NULL`...) más una **pista** en español. Se informa la línea,
no la columna. Un `;` que falta se señala, como en g++, en la línea siguiente.

Tarda menos de un segundo por archivo. Flujo recomendado: `mql5check` → corregir → MetaEditor.

## Qué detecta

**Errores** (MetaEditor también los rechaza):

- Identificadores no declarados: variables, funciones propias o de la API mal escritas o inexistentes,
  constantes y enums mal escritos (`SYMBOL_TRADE_TICKSIZE`, `EA_STOP_ATR`...). g++ suele sugerir el
  nombre correcto (`did you mean ...?`).
- Número o tipo de argumentos incorrecto en funciones de la API (`CopyBuffer` con 4 argumentos,
  `iMA` al estilo MQL4 con 7, un `ENUM_MA_METHOD` donde va un `ENUM_APPLIED_PRICE`...) y en las propias.
- Métodos inexistentes de la Biblioteca Estándar (`CTrade`, `CPositionInfo`, `CSymbolInfo`, `CDealInfo`...)
  y usar esas clases sin su `#include`.
- Errores de sintaxis: `;`, paréntesis y llaves que faltan o sobran.
- Tipos incompatibles (pasar un `double` donde va un `MqlTick &`, un `string` donde va un `double &`...).
- Modificar un parámetro `input` (en MQL5 son de solo lectura).
- Funciones que no devuelven valor en todos los caminos (`not all control paths return a value`).
- Estructuras u objetos pasados por valor y arrays pasados sin `&` (MQL5 solo los admite por referencia).
- Restos de C++ que MQL5 no tiene: `->`, `nullptr`, `auto`, `unsigned`, `long long`, `static_cast`,
  `std::`, `try/catch`, punteros a tipos simples (`int *p`).
- Restos de MQL4: `Bid`, `Ask`, `Close[0]`, `OrderSelect(i, SELECT_BY_POS)`, `AccountBalance()`,
  `DoubleToStr`, `TimeHour`...
- Redeclaraciones, `return valor;` en una función `void`, operaciones no permitidas con cadenas (`s - 1`).

**Advertencias** (como las de MetaEditor, no impiden compilar):

- `implicit conversion from 'number' to 'string'` y de `'string' to 'number'` (p. ej. asignar una cadena
  a un `double`: MQL5 lo compila con advertencia; con `--strict` cuenta como fallo).
- `possible loss of data due to type conversion` (double→int, long→int...), `sign mismatch`,
  variables que ocultan otras, entero convertido implícitamente a un enum.
- Sintaxis exclusiva de MQL5 sin equivalente en C++, que se **informa** en lugar de aceptarse en
  silencio: `this.miembro`, acceso con `.` a un puntero a objeto y pasar un puntero a un parámetro por
  referencia. Se comprueban como `this->miembro`, `p->m` y `*p`, así que el resto de la expresión sí se verifica.
- `#include <...>` de la Biblioteca Estándar que el shim no modela.

## Cómo funciona

1. Lee el `.mq5` (UTF-8 con o sin BOM, UTF-16 de MetaEditor) e incorpora los `#include "..."` locales
   (y los de una carpeta `MQL5/Include` del repositorio).
2. Lo traduce a C++ manteniendo una tabla línea generada → línea original:
   - quita `#property`, `#import`, `#resource` e `input group "..."`;
   - `#include <Trade\Trade.mqh>` (y `PositionInfo`, `SymbolInfo`, `DealInfo`, `OrderInfo`,
     `HistoryOrderInfo`, `AccountInfo`, `Object`, `Arrays\*`) activa la parte correspondiente del shim;
   - `input`/`sinput` globales → `const` (solo lectura, como en MQL5);
   - `T x[]` → `mql_array<T> x`, `T &x[]` → `mql_array<T> &x`, `T x[N]` → `mql_fixed_array<T,N> x`
     (derivado de `mql_array<T>`, así un array fijo puede pasarse a `T &arr[]` como en MQL5);
   - los literales `"..."` pasan a ser `string` (en MQL5 son cadenas: `"a" + "b"` es válido);
     `D'2024.01.01'` y `C'255,0,0'` → `datetime`/`color`; `= {0}` → `= {}`;
   - palabras clave de C++ que no lo son en MQL5 (`auto`, `try`, `unsigned`...) se renombran, para que
     sigan siendo identificadores válidos y su uso "a lo C++" dé error;
   - como MQL5 permite llamar a una función definida más abajo, genera prototipos de todas las
     funciones globales (con sus valores por defecto) y declaraciones adelantadas de clases/estructuras,
     colocados justo después de lo que necesita cada firma (enums, `#define`, inputs...).
3. Compila con `g++ -std=c++17` (por defecto con `-S -o /dev/null`, que equivale a `-fsyntax-only` más el
   análisis de flujo que detecta funciones sin `return`) y reclasifica los diagnósticos según MQL5:
   p. ej. la conversión implícita de puntero base → derivada (`CItem *p = lista.At(i);`) es válida en
   MQL5 y se descarta; la conversión cadena → número pasa a advertencia.

`mql5_shim.hpp` modela: `string` (con `+` y comparaciones; número→cadena implícito = advertencia),
`datetime` (entero de 64 bits distinto de `long`, con aritmética y comparaciones con enteros), `color`,
`uchar/ushort/uint/ulong` (y `long` de 64 bits), `NULL` y `WRONG_VALUE` como en MQL5, arrays dinámicos y
fijos con `ArrayResize/ArraySize/ArraySetAsSeries/ArrayInitialize/ArrayFree/ArrayCopy/ArraySort...`,
las estructuras `Mql*`, los enums y constantes habituales (`ENUM_TIMEFRAMES`, `SYMBOL_*`, `ACCOUNT_*`,
`TRADE_RETCODE_*`, `OBJPROP_*`, `clr*`, `STAT_*`...), variables predefinidas (`_Symbol`, `_Point`,
`_Digits`, `_Period`, `_LastError`, `_StopFlag`) y unas 350 funciones (matemáticas, cadenas, tiempo,
series e indicadores, información de símbolo/cuenta/terminal, operaciones e historial, variables
globales, archivos, gráficos y objetos, eventos, probador, indicadores personalizados), además de
`CObject`, `CTrade`, `CPositionInfo`, `COrderInfo`, `CHistoryOrderInfo`, `CDealInfo`, `CSymbolInfo`,
`CAccountInfo` y `CArrayObj/Int/Long/Double/String`. Solo contiene declaraciones: nada se enlaza.
No incluye `<string>` ni cabeceras de C a propósito, para que nombres como `time`, `signal` o `rand`
sigan libres en el código MQL5 (por eso `string` es una clase propia en vez de envolver `std::string`).

## Qué NO puede comprobar (limitaciones)

- **No ejecuta nada**: errores de lógica, de ejecución (`4756`, `invalid stops`, arrays fuera de
  rango, divisiones por cero, punteros inválidos) y resultados del probador quedan fuera.
- **La API está modelada a mano y es parcial.** Una función, constante o método de MQL5 que falte en
  el shim aparecerá como "no declarado" aunque exista (**falso positivo**): hay que añadirlo a
  `mql5_shim.hpp`. Los `#include <...>` no modelados (`Indicators\*`, `ChartObjects\*`, `Math\*`,
  `Expert\*`, `Generic\*`...) se avisan y sus símbolos darán "no declarado".
- **La semántica es la de C++ aproximada a MQL5**, no la de MQL5. Diferencias conocidas:
  - Posibles *falsos positivos*: usar una variable global antes de su declaración (se trata como
    error); `->`, que se da por inválido en MQL5; `CObj copia = puntero;`; una función cuya firma usa un
    tipo anidado de una clase (`CFoo::ENUM_X F()`) llamada antes de la definición de esa clase;
    comportamientos no documentados de MQL5.
  - El operador ternario que mezcla `datetime` y un entero (`c ? TimeCurrent() : 0`) es válido en MQL5
    pero ambiguo en C++: se informa como advertencia y esa expresión queda sin comprobar.
  - Posibles *falsos negativos* (C++ lo acepta, MQL5 quizá no): `case` o tamaño de array con un `input`,
    referencias locales (`int &r = x;`), funciones que devuelven referencias, inicializadores de miembros
    dentro de la clase, conversiones implícitas entre punteros de clases no relacionadas vía plantillas,
    asignación directa entre arrays, `printf`/`std::` que g++ conoce, sobrecarga de operadores globales.
  - Algunas advertencias de MetaEditor no se reproducen (o aparecen donde MetaEditor no avisa); los
    textos no son idénticos a los de MetaEditor.
- La conversión entero → enum en variables propias se informa como advertencia; en funciones de la API
  (`iMA(NULL, 0, ...)`) se acepta en silencio, como hace MQL5.
- Solo se valida la rama activa de `#ifdef __MQL5__ ... #else ... #endif` (se define `__MQL5__`).

## Ampliar el shim

Si MetaEditor compila algo que `mql5check` rechaza por un símbolo que falta, añada la declaración a
`mql5_shim.hpp` con la firma de la documentación de MQL5:

- parámetros de entrada `const string &`, de salida `T &`; arrays `mql_array<T> &`;
- parámetros enum de la API como `mql_enum_param<ENUM_X>` (acepta el enum o un entero, no otro enum);
- las clases de la Biblioteca Estándar van en su bloque `#if defined(MQL5CHECK_INC_...)`, y el nombre
  del `#include` en `STD_INCLUDES` de `mql5check.py`.

Después ejecute las pruebas.

## Pruebas

```bash
pytest tools/mql5check/test_mql5check.py -v
```

- **Calibración**: `archive/EMA_Cross_DayTrade_v1_original.mq5`, `archive/EMA_Cross_DayTrade_v3_referencia.mq5`
  y `EMA_Cross_DayTrade.mq5` (v4), que compilan en MetaEditor, deben dar 0 errores.
- **Mutaciones**: copias temporales del v4 con un error introducido (identificador no declarado,
  `CopyBuffer` con 4 argumentos, `;` que falta, función inexistente, constante/enum mal escritos,
  tipo incompatible, enum de otro tipo, método inexistente de `CTrade`, asignar a un `input`, función
  sin `return`, estructura por valor, `->`, cadena asignada a `double`) deben informarse en su línea.
  Se localizan con expresiones regulares: si el EA cambia y una mutación pierde su ancla, la prueba lo dice.
- **Regresiones** de la traducción (sintaxis válida de MQL5, UTF-16, `--keep`, archivo inexistente).

## Archivos

- `mql5check.py`: traductor MQL5 → C++, ejecución de g++ y presentación de los diagnósticos.
- `mql5_shim.hpp`: declaraciones del lenguaje y la API de MQL5.
- `test_mql5check.py`: pruebas (pytest).
