# -*- coding: utf-8 -*-
"""Pruebas de mql5check.py (pytest).

    pytest tools/mql5check/test_mql5check.py -v

1) Calibración: los EA que COMPILAN en MetaEditor deben dar 0 errores.
2) Mutaciones: copias temporales del EA v4 con un error típico introducido; el comprobador
   debe informarlo en la línea correcta. Las mutaciones se localizan con expresiones
   regulares (no con números de línea) para que sigan funcionando si el EA cambia.
3) Regresiones de la traducción (sintaxis válida de MQL5 que no debe dar error, etc.).
"""
import os
import re
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CHECKER = os.path.join(HERE, 'mql5check.py')
EXPERTS = os.path.join(ROOT, 'MQL5', 'Experts')
V4 = os.path.join(EXPERTS, 'EMA_Cross_DayTrade.mq5')

CALIBRATION = [
    os.path.join(EXPERTS, 'archive', 'EMA_Cross_DayTrade_v1_original.mq5'),
    os.path.join(EXPERTS, 'archive', 'EMA_Cross_DayTrade_v3_referencia.mq5'),
    V4,
]

pytestmark = pytest.mark.skipif(shutil.which('g++') is None, reason='g++ no está instalado')


def run(path, *args):
    p = subprocess.run([sys.executable, CHECKER, '--no-source', path] + list(args),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    return p.returncode, p.stdout


def read_text(path):
    with open(path, 'rb') as f:
        data = f.read()
    if data.startswith(b'\xef\xbb\xbf'):
        data = data[3:]
    return data.decode('utf-8')


def diag_lines(output, severity):
    """[(línea, mensaje)] de los diagnósticos de una severidad ('error' o 'advertencia')."""
    out = []
    for line in output.splitlines():
        m = re.match(r'^.*?:(\d+): (error|advertencia): (.*)$', line)
        if m and m.group(2) == severity:
            out.append((int(m.group(1)), m.group(3)))
    return out


# ---------------------------------------------------------------------------
# 1) Calibración
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('path', CALIBRATION, ids=[os.path.basename(p) for p in CALIBRATION])
def test_calibration_files_have_no_errors(path):
    assert os.path.isfile(path), 'falta el archivo de calibración %s' % path
    rc, out = run(path)
    assert rc == 0, out
    assert diag_lines(out, 'error') == [], out
    assert '0 error(es)' in out


# ---------------------------------------------------------------------------
# 2) Mutaciones del EA v4
# ---------------------------------------------------------------------------
def _sub_last(pattern, repl):
    def apply(src):
        ms = list(re.finditer(pattern, src, re.M))
        if not ms:
            return None
        m = ms[-1]
        return src[:m.start()] + m.expand(repl) + src[m.end():], m.start()
    return apply


def _sub_first(pattern, repl):
    def apply(src):
        m = re.search(pattern, src, re.M)
        if not m:
            return None
        return src[:m.start()] + m.expand(repl) + src[m.end():], m.start()
    return apply


# (id, mutación, severidad esperada, regex del mensaje, desplazamiento de línea admitido)
MUTATIONS = [
    ('identificador_no_declarado',
     _sub_last(r'\bg_pip\b', 'g_pipTypo'),
     'error', r"'g_pipTypo' was not declared", (0,)),
    ('CopyBuffer_con_4_argumentos',
     _sub_first(r'CopyBuffer\((\w+), (\w+), (\w+), (\w+), (\w+)\)', r'CopyBuffer(\1, \2, \3, \5)'),
     'error', r"no matching function for call to 'CopyBuffer", (0,)),
    ('falta_punto_y_coma',
     _sub_first(r'^(\s+double \w+\s*=\s*\(?\w[^;\n]*);(\s*)$', r'\1\2'),
     'error', r"expected", (0, 1)),   # g++ (y MetaEditor) lo señalan en esa línea o en la siguiente
    ('llamada_a_funcion_inexistente',
     _sub_first(r'^(\s+)(Manage\w+)\(\);', r'\1\2Typo();'),
     'error', r"'Manage\w+Typo' was not declared", (0,)),
    ('constante_enum_mal_escrita',
     _sub_first(r'\bSYMBOL_TRADE_TICK_SIZE\b', 'SYMBOL_TRADE_TICKSIZE'),
     'error', r"'SYMBOL_TRADE_TICKSIZE' was not declared", (0,)),
    ('enum_propio_mal_escrito',
     _sub_first(r'==\s*EA_STOPS_ATR\b', '== EA_STOP_ATR'),
     'error', r"'EA_STOP_ATR' was not declared", (0,)),
    ('tipo_incompatible_struct',
     _sub_first(r'SymbolInfoTick\(_Symbol, (\w+)\)', 'SymbolInfoTick(_Symbol, g_pip)'),
     'error', r"MqlTick&", (0,)),
    ('enum_de_otro_tipo_en_API',
     _sub_first(r'iATR\(_Symbol, (\w+), ', 'iATR(_Symbol, MODE_EMA, '),
     'error', r"could not convert 'MODE_EMA'", (0,)),
    ('metodo_inexistente_de_CTrade',
     _sub_first(r'g_trade\.PositionModify\(', 'g_trade.ModifyPosition('),
     'error', r"has no member named 'ModifyPosition'", (0,)),
    ('asignar_a_un_input',
     _sub_first(r'^(\s+)(g_pip = InpPipSize;)', r'\1InpPipSize = 1.0; \2'),
     'error', r"read-only variable 'InpPipSize'", (0,)),
    ('no_todos_los_caminos_devuelven',
     _sub_first(r'(string DirName\(const int dir\)\s*\{[^}]*?)\n\s*return "VENTA";', r'\1'),
     'error', r"no todos los caminos devuelven un valor", (0, 1, 2, 3, 4, 5)),
    ('struct_por_valor',
     _sub_first(r'const MqlTick &tick\)', 'MqlTick tick)'),
     'error', r"solo se pasan por referencia", (0,)),
    ('operador_flecha_de_C++',
     _sub_first(r'g_trade\.ResultRetcode\(\)', 'g_trade->ResultRetcode()'),
     'error', r"'->' no existe en MQL5", (0,)),
]


@pytest.mark.parametrize('name,mutate,severity,pattern,offsets', MUTATIONS, ids=[m[0] for m in MUTATIONS])
def test_mutations_are_reported(tmp_path, name, mutate, severity, pattern, offsets):
    src = read_text(V4)
    res = mutate(src)
    assert res is not None, 'la mutación %s ya no encuentra su punto de anclaje en el EA v4: actualice la prueba' % name
    mutated, offset = res
    line = src.count('\n', 0, offset) + 1
    path = str(tmp_path / ('mut_%s.mq5' % name))
    with open(path, 'wb') as f:
        f.write(b'\xef\xbb\xbf' + mutated.encode('utf-8'))   # con BOM, como los originales
    rc, out = run(path)
    diags = diag_lines(out, severity)
    hits = [(l, m) for l, m in diags if re.search(pattern, m) and (l - line) in offsets]
    assert hits, 'no se informó el error esperado en la línea %d:\n%s' % (line, out)
    if severity == 'error':
        assert rc == 1, out


def test_string_to_double_is_reported_as_mql5_warning(tmp_path):
    """Asignar una cadena a un double: MQL5 compila con la advertencia
    "implicit conversion from 'string' to 'number'". El comprobador la informa igual,
    y con --strict la cuenta como fallo."""
    src = read_text(V4)
    res = _sub_first(r'(double \w+\s*=\s*)AccountInfoDouble\(ACCOUNT_\w+\);', r'\1AccountInfoString(ACCOUNT_CURRENCY);')(src)
    assert res is not None
    mutated, offset = res
    line = src.count('\n', 0, offset) + 1
    path = str(tmp_path / 'mut_string_a_double.mq5')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(mutated)
    rc, out = run(path)
    warns = diag_lines(out, 'advertencia')
    assert (line, "MQL5: implicit conversion from 'string' to 'number' (conversión implícita de cadena a número)") in warns, out
    assert rc == 0, out
    rc_strict, out_strict = run(path, '--strict')
    assert rc_strict == 1, out_strict


# ---------------------------------------------------------------------------
# 3) Regresiones de la traducción
# ---------------------------------------------------------------------------
VALID_SNIPPET = r'''
#property strict
#include <Trade\Trade.mqh>
#include <Arrays\ArrayObj.mqh>
#define PREFIX "EA_"
enum ENUM_SIDE { SIDE_BUY = 1, SIDE_SELL = -1 };
input group "Grupo"
input ENUM_SIDE InpSide = SIDE_BUY;
input datetime  InpFrom = D'2024.01.01 00:00';
input color     InpColor = clrRed;
struct SRow { double v[]; int n; };
class CNode : public CObject { public: int id; CNode(void) : id(0) {} int Id(void) const { return this.id; } };
CArrayObj g_list;
double    g_grid[][3];
string    g_names[] = {"a", "b"};
int OnInit()
  {
   CNode *node = new CNode();
   g_list.Add(node);
   CNode *back = g_list.At(0);             // conversión implícita base -> derivada
   Print(back.Id(), " ", Later(2), " ", Later());   // función definida más abajo + valor por defecto
   ArrayResize(g_grid, 2);
   g_grid[1][2] = 3.0;
   string name = PREFIX + "x" + "y";
   MqlTradeRequest req = {0};
   req.action = TRADE_ACTION_DEAL;
   datetime t = TimeCurrent() - PeriodSeconds(PERIOD_D1);
   if(t > InpFrom && ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0))
      ObjectSetInteger(0, name, OBJPROP_COLOR, InpColor);
   int h = iMA(NULL, 0, 14, 0, MODE_SMA, PRICE_CLOSE);
   delete node;
   return h == INVALID_HANDLE ? INIT_FAILED : INIT_SUCCEEDED;
  }
int Later(const int x = 1) { return x * (int)InpSide; }
void OnTick() {}
'''


def test_valid_mql5_constructs_compile(tmp_path):
    path = str(tmp_path / 'valido.mq5')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(VALID_SNIPPET)
    rc, out = run(path)
    assert rc == 0, out
    assert diag_lines(out, 'error') == [], out
    warns = [m for _, m in diag_lines(out, 'advertencia')]
    # Sintaxis exclusiva de MQL5: se informa como advertencia, no se acepta en silencio
    assert any("'this.miembro'" in w for w in warns), out
    assert any("acceso con '.' al puntero 'back'" in w for w in warns), out


def test_utf16_source_is_supported(tmp_path):
    path = str(tmp_path / 'utf16.mq5')
    with open(path, 'wb') as f:
        f.write(b'\xff\xfe' + 'void OnStart() { Print("año ñ"); }\n'.encode('utf-16-le'))
    rc, out = run(path)
    assert rc == 0, out


def test_keep_flag_keeps_generated_cpp(tmp_path):
    path = str(tmp_path / 'k.mq5')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('void OnStart() { Print(1); }\n')
    rc, out = run(path, '--keep')
    assert rc == 0, out
    m = re.search(r'C\+\+ generado: (\S+\.cpp)', out)
    assert m and os.path.isfile(m.group(1)), out
    shutil.rmtree(os.path.dirname(m.group(1)), ignore_errors=True)


def test_missing_file_is_a_tool_failure():
    rc, out = run(os.path.join(HERE, 'no_existe.mq5'))
    assert rc == 2, out
