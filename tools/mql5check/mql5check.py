#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mql5check: comprobador estático de errores de compilación MQL5 (sin MetaEditor).

Traduce el código MQL5 a C++17, lo compila con g++ contra `mql5_shim.hpp` (declaraciones
de la API de MQL5) y muestra los errores con el archivo y la línea ORIGINALES del .mq5.

NO es un compilador de MQL5: MetaEditor sigue siendo la autoridad. Ver README.md.

Uso:
    python3 tools/mql5check/mql5check.py Archivo.mq5 [otros.mq5 ...] [--keep] [--strict]

Código de salida: 0 = sin errores, 1 = hay errores (o advertencias con --strict),
                  2 = fallo de la herramienta (g++ ausente, archivo ilegible...).
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SHIM = os.path.join(HERE, 'mql5_shim.hpp')

# ---------------------------------------------------------------------------
# Conocimiento del lenguaje
# ---------------------------------------------------------------------------
BUILTIN_TYPES = {'bool', 'char', 'uchar', 'short', 'ushort', 'int', 'uint', 'long', 'ulong',
                 'float', 'double', 'string', 'datetime', 'color', 'void'}
SCALAR_TYPES = BUILTIN_TYPES - {'void'}

# Palabras clave de C++ que NO lo son en MQL5. Se renombran (x -> x__cxx) para que:
#  - si el código MQL5 las usa como identificadores (válido en MQL5) siga compilando;
#  - si las usa como palabra clave de C++ (inválido en MQL5), g++ dé error.
CPP_ONLY_KEYWORDS = {
    'alignas', 'alignof', 'asm', 'auto', 'catch', 'char8_t', 'char16_t', 'char32_t', 'co_await',
    'co_return', 'co_yield', 'const_cast', 'consteval', 'constexpr', 'constinit', 'decltype',
    'explicit', 'export', 'friend', 'goto', 'inline', 'mutable', 'noexcept', 'nullptr', 'register',
    'reinterpret_cast', 'signed', 'static_assert', 'static_cast', 'thread_local', 'throw', 'try',
    'typeid', 'unsigned', 'volatile', 'wchar_t', 'concept', 'requires',
}
RENAME_SUFFIX = '__cxx'

# #include <...> de la Biblioteca Estándar modelados en el shim -> macro MQL5CHECK_INC_*
STD_INCLUDES = {
    'trade/trade.mqh': 'TRADE',
    'trade/positioninfo.mqh': 'POSITIONINFO',
    'trade/orderinfo.mqh': 'ORDERINFO',
    'trade/historyorderinfo.mqh': 'HISTORYORDERINFO',
    'trade/dealinfo.mqh': 'DEALINFO',
    'trade/symbolinfo.mqh': 'SYMBOLINFO',
    'trade/accountinfo.mqh': 'ACCOUNTINFO',
    'object.mqh': 'OBJECT',
    'arrays/array.mqh': 'ARRAYS',
    'arrays/arrayobj.mqh': 'ARRAYS',
    'arrays/arrayint.mqh': 'ARRAYS',
    'arrays/arraylong.mqh': 'ARRAYS',
    'arrays/arraydouble.mqh': 'ARRAYS',
    'arrays/arraystring.mqh': 'ARRAYS',
}

GXX_WARNING_FLAGS = [
    '-Wreturn-type',          # MQL5: "not all control paths return a value" (error en MQL5)
    '-Wshadow',               # MQL5: "declaration of 'x' hides global/local declaration"
    '-Wconversion',           # MQL5: "possible loss of data due to type conversion"
    '-Wno-sign-conversion',
    '-Wsign-compare',         # MQL5: "sign mismatch"
    '-Wempty-body',           # MQL5: "empty controlled statement found"
    '-Wparentheses',
    '-Wuninitialized',        # MQL5: "possible use of uninitialized variable"
]

# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------
TOKEN_RE = re.compile(r'''
 (?P<nl>\n)
|(?P<ws>[ \t\f\v]+)
|(?P<lcomment>//[^\n]*)
|(?P<bcomment>/\*.*?\*/)
|(?P<dlit>\b[DC]'[^'\n]*')
|(?P<str>"(?:\\.|[^"\\\n])*")
|(?P<char>'(?:\\.|[^'\\\n])*')
|(?P<num>(?:0[xX][0-9A-Fa-f]+|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)[A-Za-z]*)
|(?P<id>[^\W\d]\w*)
|(?P<op>>>=|<<=|\.\.\.|->|::|\+\+|--|<<|>>|<=|>=|==|!=|&&|\|\||\+=|-=|\*=|/=|%=|&=|\|=|\^=|[{}()\[\];,.<>+\-*/%&|^!~?:=\#])
|(?P<other>.)
''', re.S | re.X)
DIRECTIVE_RE = re.compile(r'\#(?:\\\n|[^\n])*')

TRIVIA = ('ws', 'nl', 'lcomment', 'bcomment')


class Tok(object):
    __slots__ = ('kind', 'text', 'file', 'line', 'col', 'pre', 'post', 'orig')

    def __init__(self, kind, text, file, line, col):
        self.kind = kind
        self.text = text
        self.orig = text
        self.file = file
        self.line = line
        self.col = col
        self.pre = []    # [(texto, origen|None)] insertado antes
        self.post = []   # [(texto, origen|None)] insertado después

    def full(self):
        return ''.join(s for s, _ in self.pre) + self.text + ''.join(s for s, _ in self.post)

    def blank(self):
        self.text = ''
        self.pre = []
        self.post = []

    def __repr__(self):
        return 'Tok(%s,%r,%s:%d)' % (self.kind, self.text, os.path.basename(self.file), self.line)


def read_source(path):
    with open(path, 'rb') as f:
        data = f.read()
    if data.startswith(b'\xff\xfe') or data.startswith(b'\xfe\xff'):
        text = data.decode('utf-16')
    elif data.startswith(b'\xef\xbb\xbf'):
        text = data[3:].decode('utf-8', errors='replace')
    elif len(data) > 1 and data[1:2] == b'\x00' and data.count(b'\x00') > len(data) // 4:
        text = data.decode('utf-16-le', errors='replace')   # UTF-16 sin BOM (MetaEditor)
    else:
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError:
            text = data.decode('cp1252', errors='replace')
    if text.startswith('\ufeff'):
        text = text[1:]
    return text.replace('\r\n', '\n').replace('\r', '\n')


def tokenize(text, file, diags):
    toks = []
    pos = 0
    line = 1
    line_start = 0
    at_line_start = True
    n = len(text)
    while pos < n:
        col = pos - line_start + 1
        if at_line_start and text[pos] == '#':
            m = DIRECTIVE_RE.match(text, pos)
            kind, s = 'dir', m.group(0)
        else:
            if text.startswith('/*', pos) and text.find('*/', pos + 2) < 0:
                diags.append(('error', file, line, 'comentario /* sin cerrar'))
                s, kind = text[pos:], 'bcomment'
            else:
                m = TOKEN_RE.match(text, pos)
                kind, s = m.lastgroup, m.group(0)
        toks.append(Tok(kind, s, file, line, col))
        nls = s.count('\n')
        if nls:
            line += nls
            line_start = pos + s.rfind('\n') + 1
        pos += len(s)
        if kind == 'nl':
            at_line_start = True
        elif kind != 'ws':
            at_line_start = False
    return toks


# ---------------------------------------------------------------------------
# Traducción MQL5 -> C++
# ---------------------------------------------------------------------------
class Translation(object):
    def __init__(self):
        self.diags = []          # (severidad, archivo, línea, mensaje)
        self.cpp = ''
        self.line_origin = [None]  # índice = línea generada (1-based) -> (archivo, línea) | None
        self.flags = set()
        self.files = set()
        self.enum_types = set()
        self.class_graph = {}
        self.source_lines = {}   # archivo -> [líneas]


def load_file(path, tr, stack, included):
    apath = os.path.abspath(path)
    tr.files.add(apath)
    text = read_source(apath)
    tr.source_lines[apath] = text.split('\n')
    toks = tokenize(text, apath, tr.diags)
    out = []
    for t in toks:
        if t.kind == 'dir':
            m = re.match(r'#\s*include\s*([<"])([^>"]*)[>"]', t.text)
            if m:
                out.append(Tok('ws', '', t.file, t.line, t.col))
                out.extend(handle_include(m.group(1), m.group(2).strip(), t, tr, stack + [apath], included))
                continue
        out.append(t)
    return out


def include_search_dirs(from_file):
    d = os.path.dirname(from_file)
    dirs = [d]
    # Estructura típica: .../MQL5/Experts/X.mq5 -> .../MQL5/Include
    cur = d
    for _ in range(4):
        cand = os.path.join(cur, 'Include')
        if os.path.isdir(cand):
            dirs.append(cand)
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return dirs


def handle_include(delim, name, tok, tr, stack, included):
    norm = name.replace('\\', '/')
    key = norm.lower()
    if delim == '<' and key in STD_INCLUDES:
        tr.flags.add(STD_INCLUDES[key])
        return []
    # Archivo local (o de la carpeta Include del repositorio)
    candidates = []
    if delim == '"':
        candidates.append(os.path.join(os.path.dirname(tok.file), norm))
    for d in include_search_dirs(tok.file):
        candidates.append(os.path.join(d, norm))
    for c in candidates:
        if os.path.isfile(c):
            ac = os.path.abspath(c)
            if ac in included or ac in stack:
                return []   # MQL5 incluye cada archivo una sola vez
            included.add(ac)
            return load_file(ac, tr, stack, included)
    if delim == '<':
        tr.diags.append(('warning', tok.file, tok.line,
                         "#include <%s> no está modelado en mql5_shim.hpp: sus clases/funciones "
                         "aparecerán como no declaradas (no es necesariamente un error de MQL5)" % name))
    else:
        tr.diags.append(('error', tok.file, tok.line, "no se encuentra el archivo de #include \"%s\"" % name))
    return []


CLASS_BASES_RE = re.compile(r'\b(?:class|struct|interface)\s+(\w+)\s*(?:final\s*)?:\s*([^{;]+)\{')


def class_bases(text):
    """{clase: {bases}} a partir de 'class X : public Y, Z {'."""
    graph = {}
    for m in CLASS_BASES_RE.finditer(text):
        bases = set()
        for part in m.group(2).split(','):
            words = [w for w in re.findall(r'\w+', re.sub(r'<.*', '', part))
                     if w not in ('public', 'protected', 'private', 'virtual')]
            if words:
                bases.add(words[-1])
        graph.setdefault(m.group(1), set()).update(bases)
    return graph


def shim_type_names():
    try:
        text = open(SHIM, encoding='utf-8').read()
    except OSError:
        return set(), set(), set()
    types = set(re.findall(r'\b(?:class|struct|enum)\s+(\w+)', text))
    types |= set(re.findall(r'\btypedef\b[^;]*?\b(\w+)\s*;', text))
    enums = set(re.findall(r'\benum\s+(\w+)', text))
    objects = set(n for n in re.findall(r'\b(?:class|struct)\s+(\w+)\s*[:{]', text)
                  if not n.startswith('mql_') and n not in ('string', 'datetime', 'color'))
    objects |= set(re.findall(r'MQL5CHECK_ARRAY_CLASS\((\w+)', text))
    types |= set(re.findall(r'MQL5CHECK_ARRAY_CLASS\((\w+)', text))
    return types, enums, objects


class Translator(object):
    def __init__(self, tr, toks):
        self.tr = tr
        self.toks = toks
        self.shim_types, self.shim_enums, self.shim_objects = shim_type_names()
        self.user_types = set()
        self.user_enums = set()
        self.user_objects = set()

    # --- utilidades -------------------------------------------------------
    def diag(self, sev, tok, msg):
        self.tr.diags.append((sev, tok.file, tok.line, msg))

    def sig(self):
        """Tokens significativos (sin espacios/comentarios) con texto no vacío."""
        return [t for t in self.toks if t.kind not in TRIVIA and (t.text != '' or t.pre or t.post)]

    @staticmethod
    def match(S, i, open_, close_):
        depth = 0
        for k in range(i, len(S)):
            x = S[k].text
            if x == open_:
                depth += 1
            elif x == close_:
                depth -= 1
                if depth == 0:
                    return k
        return len(S) - 1

    @staticmethod
    def match_any(S, i):
        """Cierre del grupo que abre S[i] ((, [, {) respetando anidamiento mixto."""
        pairs = {'(': ')', '[': ']', '{': '}'}
        stack = []
        for k in range(i, len(S)):
            x = S[k].text
            if x in pairs:
                stack.append(pairs[x])
            elif x in (')', ']', '}'):
                if stack and stack[-1] == x:
                    stack.pop()
                if not stack:
                    return k
        return len(S) - 1

    @staticmethod
    def skip_angle(S, i):
        """S[i] es '<' de argumentos de plantilla: devuelve el índice tras el '>' de cierre."""
        depth = 0
        k = i
        while k < len(S):
            x = S[k].text
            if x == '<':
                depth += 1
            elif x == '>':
                depth -= 1
            elif x == '>>':
                depth -= 2
            elif x in (';', '{', '}'):
                return i + 1
            k += 1
            if depth <= 0:
                return k
        return k

    # --- pases --------------------------------------------------------------
    def collect_types(self):
        S = self.sig()
        for i, t in enumerate(S):
            if t.kind != 'id':
                continue
            if t.text in ('struct', 'class', 'enum', 'union', 'interface') and i + 1 < len(S) and S[i + 1].kind == 'id' \
                    and not (i > 0 and S[i - 1].text in ('<', ',')):   # template<class T>: no es una clase
                name = S[i + 1].text
                self.user_types.add(name)
                if t.text == 'enum':
                    self.user_enums.add(name)
                else:
                    self.user_objects.add(name)
            elif t.text == 'typedef':
                k = i + 1
                last = None
                while k < len(S) and S[k].text != ';':
                    if S[k].text == '(' and k + 2 < len(S) and S[k + 1].text == '*' and S[k + 2].kind == 'id':
                        last = S[k + 2].text
                        break
                    if S[k].kind == 'id':
                        last = S[k].text
                    k += 1
                if last:
                    self.user_types.add(last)
            elif t.text == 'template' and i + 1 < len(S) and S[i + 1].text == '<':
                end = self.skip_angle(S, i + 1)
                for k in range(i + 2, end):
                    if S[k].text in ('typename', 'class') and k + 1 < end and S[k + 1].kind == 'id':
                        self.user_types.add(S[k + 1].text)
        graph = class_bases(open(SHIM, encoding='utf-8').read()) if os.path.isfile(SHIM) else {}
        for f in self.tr.files:
            for cls, bases in class_bases('\n'.join(self.tr.source_lines.get(f, []))).items():
                graph.setdefault(cls, set()).update(bases)
        self.tr.class_graph = graph
        self.types = BUILTIN_TYPES | self.shim_types | self.user_types
        self.objects = self.shim_objects | self.user_objects
        self.tr.enum_types = self.shim_enums | self.user_enums

    def pass_input_group(self):
        S = self.sig()
        for i in range(len(S) - 2):
            if S[i].text == 'input' and S[i + 1].text == 'group' and S[i + 2].kind == 'str':
                S[i].blank()
                S[i + 1].blank()
                k = i + 2
                while k < len(S) and S[k].kind == 'str':
                    S[k].blank()
                    k += 1

    def pass_directives_and_tokens(self):
        for t in self.toks:
            if t.kind == 'dir':
                self.rewrite_directive(t)
        S = self.sig()
        n = len(S)
        # '->' no existe en MQL5 (se accede a miembros de punteros con '.')
        for i, t in enumerate(S):
            if t.text == '->':
                self.diag('error', t, "el operador '->' no existe en MQL5: use '.' también con punteros a objetos")
            elif t.kind == 'id' and t.text == 'std' and i + 1 < n and S[i + 1].text == '::':
                self.diag('error', t, "el espacio de nombres 'std' (biblioteca de C++) no existe en MQL5")
            elif t.kind == 'id' and t.text == 'long' and i + 1 < n and S[i + 1].text == 'long':
                self.diag('error', t, "el tipo 'long long' no existe en MQL5 (long ya es de 64 bits)")
            elif t.kind == 'id' and t.text in SCALAR_TYPES and i + 1 < n and S[i + 1].text == '*' \
                    and (i == 0 or S[i - 1].text not in ('.', '::')) \
                    and i + 2 < n and (S[i + 2].kind == 'id' or S[i + 2].text in (')', ',', '>', '&')):
                self.diag('error', t, "en MQL5 no hay punteros a tipos simples ('%s *'): solo a objetos de clases" % t.text)
        # Reescrituras de tokens
        i = 0
        while i < n:
            t = S[i]
            if t.kind == 'str':
                j = i
                while j + 1 < n and S[j + 1].kind == 'str':
                    j += 1
                t.pre.append(('string(', None))
                S[j].post.append((')', None))
                i = j + 1
                continue
            if t.kind == 'dlit':
                t.text = 'datetime(0)' if t.text.startswith('D') else 'color(0)'
            elif t.kind == 'id':
                if t.text in CPP_ONLY_KEYWORDS:
                    t.text = t.text + RENAME_SUFFIX
                elif t.text == 'interface':
                    t.text = 'struct'
                elif t.text == 'this' and i + 1 < n and S[i + 1].text == '.':
                    S[i + 1].text = '->'
                    self.diag('warning', t, "'this.miembro' es sintaxis de MQL5 sin equivalente directo en C++ "
                                            "(se comprueba como 'this->miembro')")
            i += 1

    def rewrite_directive(self, t):
        m = re.match(r'#\s*(\w+)', t.text)
        word = m.group(1) if m else ''
        if word in ('property', 'import', 'resource'):
            t.text = ''
            return
        if word == 'define':
            # Transformar el cuerpo de la macro (literales de cadena, D'..', C'..')
            m2 = re.match(r'(#\s*define\s+\w+(?:\([^)]*\))?)(.*)', t.text, re.S)
            if not m2:
                return
            head, body = m2.group(1), m2.group(2)
            sub = tokenize(body, t.file, [])
            out = []
            k = 0
            while k < len(sub):
                s = sub[k]
                if s.kind == 'str':
                    j = k
                    parts = [s.text]
                    while True:
                        j2 = j + 1
                        while j2 < len(sub) and sub[j2].kind in ('ws',):
                            j2 += 1
                        if j2 < len(sub) and sub[j2].kind == 'str':
                            parts.append(' ' + sub[j2].text)
                            j = j2
                        else:
                            break
                    out.append('string(' + ''.join(parts) + ')')
                    k = j + 1
                    continue
                if s.kind == 'dlit':
                    out.append('datetime(0)' if s.text.startswith('D') else 'color(0)')
                elif s.kind == 'id' and s.text in CPP_ONLY_KEYWORDS:
                    out.append(s.text + RENAME_SUFFIX)
                elif s.kind == 'id' and s.text == 'interface':
                    out.append('struct')
                else:
                    out.append(s.text)
                k += 1
            t.text = head + ''.join(out)
        elif word in ('ifdef', 'ifndef', 'else', 'endif', 'undef', 'if', 'elif'):
            return
        elif word == 'include':
            t.text = ''
        else:
            self.diag('warning', t, "directiva '#%s' desconocida: se ignora" % word)
            t.text = ''

    def pass_input(self):
        """input/sinput globales -> const (en MQL5 son de solo lectura)."""
        S = self.sig()
        depth = 0
        n = len(S)
        i = 0
        while i < n:
            x = S[i].text
            if x == '{':
                depth += 1
            elif x == '}':
                depth -= 1
            elif x in ('input', 'sinput') and S[i].kind == 'id' and depth == 0:
                S[i].text = 'const'
                # Declaradores sin inicializador -> {} (un const de C++ debe inicializarse)
                k = i + 1
                seg_has_init = False
                last = None
                pd = 0
                while k < n:
                    y = S[k].text
                    if y in ('(', '[', '{'):
                        pd += 1
                    elif y in (')', ']', '}'):
                        pd -= 1
                    elif pd == 0 and y in (',', ';'):
                        if not seg_has_init and last is not None:
                            last.post.append(('{}', None))
                        seg_has_init = False
                        if y == ';':
                            break
                    elif pd == 0 and y == '=':
                        seg_has_init = True
                    if y not in (',', ';'):
                        last = S[k]
                    k += 1
                i = k
            i += 1

    def is_type_at(self, S, i):
        t = S[i]
        if t.kind != 'id' or t.text not in self.types:
            return False
        if i > 0 and S[i - 1].text in ('.', '->', '::', 'enum', 'struct', 'class', 'union', 'interface'):
            return False
        return True

    def pass_arrays(self):
        """T x[] -> mql_array<T> x ; T x[N] -> mql_fixed_array<T,N> x ; T &x[] -> mql_array<T> &x."""
        S = self.sig()
        n = len(S)
        stack = []   # pila de ( [ {
        i = 0
        while i < n:
            x = S[i].text
            if x in ('(', '[', '{'):
                stack.append(x)
                i += 1
                continue
            if x in (')', ']', '}'):
                if stack:
                    stack.pop()
                i += 1
                continue
            if not self.is_type_at(S, i):
                i += 1
                continue
            in_parens = bool(stack) and stack[-1] == '('
            type_start = i
            k = i + 1
            if k < n and S[k].text == '<':
                k = self.skip_angle(S, k)
            type_end = k
            if k < n and S[k].kind == 'id' and S[k].text in self.types and \
                    not (k + 1 < n and S[k + 1].text == '::'):
                i += 1   # p. ej. 'long long': no es un declarador
                continue
            decls = self.parse_declarators(S, type_end, in_parens)
            if not decls or not any(d['dims'] for d in decls):
                i += 1
                continue
            self.rewrite_array_decl(S, type_start, type_end, decls, in_parens)
            i = type_end
        return

    def parse_declarators(self, S, k, in_parens):
        n = len(S)
        decls = []
        while k < n:
            d = {'start': k, 'star': None, 'amp': None, 'name': None, 'dims': [], 'comma': None}
            while k < n and S[k].text in ('*', '&'):
                if S[k].text == '*':
                    d['star'] = k
                else:
                    d['amp'] = k
                k += 1
            if k >= n or S[k].kind != 'id' or S[k].text == 'operator':
                break
            # nombre calificado (definición de miembro estático): double CFoo::s_buf[];
            while k + 2 < n and S[k + 1].text == '::' and S[k + 2].kind == 'id':
                k += 2
            if S[k].text in self.types or S[k].text == 'operator':
                break
            d['name'] = k
            k += 1
            while k < n and S[k].text == '[':
                close = self.match(S, k, '[', ']')
                d['dims'].append((k, close))
                k = close + 1
            if k < n and S[k].text == '(':
                if d['dims']:
                    break
                k = self.match(S, k, '(', ')') + 1
            if k < n and S[k].text == '=':
                # saltar el inicializador
                depth = 0
                while k < n:
                    y = S[k].text
                    if y in ('(', '[', '{'):
                        depth += 1
                    elif y in (')', ']', '}'):
                        if depth == 0:
                            break
                        depth -= 1
                    elif depth == 0 and y in (',', ';'):
                        break
                    k += 1
            d['end'] = k
            decls.append(d)
            if in_parens:
                break
            if k < n and S[k].text == ',':
                d['comma'] = k
                k += 1
                continue
            break
        if decls and not in_parens:
            # Debe terminar en ';' para ser una declaración
            last_end = decls[-1]['end']
            if last_end >= n or S[last_end].text != ';':
                return [d for d in decls[:1]] if decls[0]['dims'] and len(decls) == 1 else []
        return decls

    def wrap_type(self, elem, dims_text):
        t = elem
        for d in reversed(dims_text):
            if d.strip() == '':
                t = 'mql_array<%s>' % t
            else:
                t = 'mql_fixed_array<%s, %s>' % (t, d.strip())
        return t

    def rewrite_array_decl(self, S, type_start, type_end, decls, in_parens):
        type_text = ' '.join(S[k].full() for k in range(type_start, type_end))
        # calificadores (const/static/extern) anteriores al tipo
        q = type_start
        while q > 0 and S[q - 1].text in ('const', 'static', 'extern'):
            q -= 1
        qual_text = ' '.join(S[k].text for k in range(q, type_start))
        for idx, d in enumerate(decls):
            dims_text = [' '.join(S[k].full() for k in range(a + 1, b)) for a, b in d['dims']]
            if d['dims'] and len(dims_text) > 1 and any(x.strip() == '' for x in dims_text[1:]):
                self.diag('error', S[d['name']], "solo la primera dimensión de un array puede ser dinámica ([])")
            name_tok = S[d['name']]
            if in_parens and d['dims'] and d['amp'] is None:
                self.diag('error', name_tok, "'%s': en MQL5 los arrays se pasan solo por referencia (use '&%s[]')"
                          % (name_tok.text, name_tok.text))
            elem = type_text + ('*' if (d['star'] is not None and d['dims']) else '')
            new_type = self.wrap_type(elem, dims_text) if d['dims'] else type_text
            # borrar las dimensiones
            for a, b in d['dims']:
                for k in range(a, b + 1):
                    S[k].blank()
            if d['dims'] and d['star'] is not None:
                S[d['star']].blank()
            if idx == 0:
                if d['dims']:
                    # Sustituir todo el tipo por el nuevo texto
                    S[type_start].text = new_type
                    S[type_start].pre = []
                    S[type_start].post = []
                    for k in range(type_start + 1, type_end):
                        S[k].blank()
            else:
                # separar la declaración: ", b[]" -> "; <calif> mql_array<T> b"
                comma = decls[idx - 1]['comma']
                if comma is not None:
                    S[comma].text = ';'
                prefix = (qual_text + ' ' if qual_text else '') + new_type + ' '
                S[d['start']].pre.insert(0, (prefix, None))

    def pass_param_checks(self):
        """Estructuras/objetos pasados por valor (en MQL5 solo por referencia)."""
        S = self.sig()
        n = len(S)
        for p in range(2, n):
            if S[p].text != '(' or S[p - 1].kind != 'id':
                continue
            before = S[p - 2]
            is_ctor = S[p - 1].text in self.objects and before.text in (';', '{', '}', ':')
            if not (is_ctor or (before.kind == 'id' and before.text in self.types) or
                    before.text in ('>', '*', '&', '::', '~')):
                continue
            close = self.match(S, p, '(', ')')
            # separar parámetros
            params = []
            cur = []
            depth = 0
            for k in range(p + 1, close):
                y = S[k].text
                if y in ('(', '[', '{', '<'):
                    depth += 1
                elif y in (')', ']', '}', '>'):
                    depth -= 1
                if depth == 0 and y == ',':
                    params.append(cur)
                    cur = []
                else:
                    cur.append(S[k])
            if cur:
                params.append(cur)
            for prm in params:
                toks = []
                for t in prm:
                    if t.text == '=':
                        break
                    if t.text:
                        toks.append(t)
                while toks and toks[0].text in ('const', 'static'):
                    toks = toks[1:]
                if not toks or toks[0].kind != 'id' or toks[0].text not in self.objects:
                    continue
                rest = toks[1:]
                if rest and rest[0].text == '<':
                    j = self.skip_angle(rest, 0)
                    rest = rest[j:]
                if any(t.text in ('&', '*') for t in rest):
                    continue
                if len(rest) > 1:
                    continue
                name = rest[0].text if rest else '(sin nombre)'
                self.diag('error', toks[0], "'%s': en MQL5 las estructuras y objetos solo se pasan por referencia "
                                            "(use 'const %s &%s' o '%s &%s')" % (name, toks[0].text, name, toks[0].text, name))

    def pass_zero_init(self):
        S = self.sig()
        for i in range(len(S) - 3):
            if S[i].text == '=' and S[i + 1].text == '{' and S[i + 2].text == '0' and S[i + 3].text == '}':
                S[i + 2].blank()

    # --- prototipos (MQL5 permite llamar a funciones definidas más abajo) ------
    def pass_prototypes(self):
        P = self.sig()
        n = len(P)
        items = []
        cond_stack = []
        ns_depth = 0
        i = 0
        while i < n:
            t = P[i]
            if t.kind == 'dir':
                word = re.match(r'#\s*(\w*)', t.text).group(1)
                first_line = t.text.split('\n')[0]
                if word in ('ifdef', 'ifndef', 'if'):
                    cond_stack.append([first_line])
                elif word in ('else', 'elif') and cond_stack:
                    cond_stack[-1].append(first_line)
                elif word == 'endif' and cond_stack:
                    cond_stack.pop()
                it = {'kind': 'dir', 'start': i, 'end': i, 'word': word}
                if word == 'define':
                    m = re.match(r'#\s*define\s+(\w+)', t.text)
                    if m:
                        it['names'] = [m.group(1)]
                items.append(it)
                i += 1
                continue
            start = i
            depth = 0
            first_paren = None
            first_close = None
            kind = None
            body = None
            while i < n:
                t = P[i]
                x = t.text
                if t.kind == 'dir':
                    i += 1
                    continue
                if x in ('(', '['):
                    if x == '(' and depth == 0 and first_paren is None:
                        first_paren = i
                    depth += 1
                elif x in (')', ']'):
                    depth -= 1
                    if depth == 0 and x == ')' and first_paren is not None and first_close is None:
                        first_close = i
                elif x == '{' and depth == 0:
                    head0 = P[start].text
                    if head0 == 'namespace':
                        kind = 'ns_open'
                        i += 1
                        break
                    if self.is_function_head(P, start, i, first_paren, first_close):
                        close = self.match_any(P, i)
                        kind = 'func'
                        body = (i, close)
                        i = close + 1
                        break
                    i = self.match_any(P, i) + 1
                    continue
                elif x == '}' and depth == 0:
                    kind = 'ns_close'
                    i += 1
                    break
                elif x == ';' and depth == 0:
                    kind = 'decl'
                    i += 1
                    break
                i += 1
            if kind is None:
                kind = 'decl'
            it = {'kind': kind, 'start': start, 'end': i - 1, 'fp': first_paren, 'fc': first_close,
                  'body': body, 'cond': [list(f) for f in cond_stack], 'ns': ns_depth}
            if kind == 'ns_open':
                ns_depth += 1
            elif kind == 'ns_close':
                ns_depth = max(0, ns_depth - 1)
            items.append(it)

        # Nombres declarados por cada elemento de nivel superior
        decl_index = {}
        class_def = {}  # clase -> índice del item que la define (para usos como CFoo::TIPO)
        classes = []   # (índice de item, texto de declaración adelantada)

        def declare(name, k):
            if name not in decl_index:
                decl_index[name] = k

        for k, it in enumerate(items):
            if it['kind'] == 'dir':
                for nm in it.get('names', []):
                    declare(nm, k)
                continue
            if it['kind'] not in ('decl',):
                continue
            s, e = it['start'], it['end']
            toks = P[s:e + 1]
            texts = [t.text for t in toks]
            j = 0
            tmpl_header = None
            if texts and texts[0] == 'template' and len(texts) > 1 and texts[1] == '<':
                j = self.skip_angle(toks, 1)
                tmpl_header = ' '.join(t.full() for t in toks[:j])
            if j < len(texts) and texts[j] in ('struct', 'class', 'union', 'enum') and j + 1 < len(texts) \
                    and toks[j + 1].kind == 'id':
                name = texts[j + 1]
                is_def = '{' in texts[j + 2:]
                declare(name, k if (texts[j] == 'enum' or not is_def) else -1)
                if is_def and name not in class_def:
                    class_def[name] = k
                if texts[j] == 'enum':
                    if '{' in texts:
                        b = texts.index('{')
                        depth = 0
                        for q in range(b, len(texts)):
                            if texts[q] in ('{', '(', '['):
                                depth += 1
                            elif texts[q] in ('}', ')', ']'):
                                depth -= 1
                            elif depth == 1 and toks[q].kind == 'id' and q + 1 < len(texts) \
                                    and texts[q + 1] in ('=', ',', '}'):
                                declare(texts[q], k)
                elif is_def and it['ns'] == 0:
                    if tmpl_header is None:
                        classes.append((k, '%s %s;' % (texts[j], name)))
                    elif '=' not in tmpl_header:
                        classes.append((k, '%s %s %s;' % (tmpl_header, texts[j], name)))
                    else:
                        declare(name, k)
                continue
            if texts and texts[0] == 'typedef':
                for q in range(len(toks) - 1, -1, -1):
                    if toks[q].kind == 'id':
                        declare(toks[q].text, k)
                        break
                if '(' in texts:
                    for q in range(len(texts) - 2):
                        if texts[q] == '(' and texts[q + 1] == '*' and toks[q + 2].kind == 'id':
                            declare(texts[q + 2], k)
                continue
            depth = 0
            for q, t in enumerate(toks):
                x = t.text
                if x in ('(', '[', '{'):
                    depth += 1
                elif x in (')', ']', '}'):
                    depth -= 1
                elif depth == 0 and t.kind == 'id' and q + 1 < len(toks) and texts[q + 1] in ('=', ',', ';', '[', '('):
                    declare(x, k)
                elif depth == 0 and t.kind == 'id' and q == len(toks) - 1:
                    declare(x, k)

        # Prototipos de las funciones globales definidas
        inserts = {}   # índice de item (-1 = inicio) -> [(texto, tok_origen)]
        for k, it in enumerate(items):
            if it['kind'] != 'func' or it['ns'] != 0:
                continue
            fp, fc = it['fp'], it['fc']
            if fp is None or fc is None or fp - 1 < it['start']:
                continue
            name_tok = P[fp - 1]
            if name_tok.kind != 'id' or name_tok.text == 'operator':
                continue
            if fp - 2 >= it['start'] and P[fp - 2].text in ('::', '~', 'operator'):
                continue   # método definido fuera de la clase
            head = P[it['start']:fp - 1]
            if not head or not all(t.kind == 'id' or t.text in ('*', '&', '::', '<', '>', '>>', ',') for t in head):
                continue
            if any(t.text in ('=', ';') for t in head):
                continue
            # parámetros: nombres (excluidos de las dependencias) y valores por defecto
            params = []
            cur = []
            depth = 0
            for q in range(fp + 1, fc):
                y = P[q].text
                if y in ('(', '[', '{', '<'):
                    depth += 1
                elif y in (')', ']', '}', '>'):
                    depth -= 1
                if depth == 0 and y == ',':
                    params.append(cur)
                    cur = []
                else:
                    cur.append(q)
            if cur:
                params.append(cur)
            param_names = set()
            default_ranges = []
            for prm in params:
                eq = None
                for q in prm:
                    if P[q].text == '=':
                        eq = q
                        break
                decl_part = [q for q in prm if eq is None or q < eq]
                ids = [q for q in decl_part if P[q].kind == 'id']
                if len(decl_part) >= 2 and ids and ids[-1] == decl_part[-1] and P[ids[-1]].text not in self.types:
                    param_names.add(P[ids[-1]].text)
                if eq is not None:
                    default_ranges.append((eq, prm[-1]))
            proto = ' '.join(P[q].full() for q in range(it['start'], fc + 1) if P[q].full()) + ';'
            deps = set()
            for q in range(it['start'], fc + 1):
                if q == fp - 1:
                    continue
                for ident in re.findall(r'[^\W\d]\w*', P[q].full()):
                    if ident not in param_names:
                        deps.add(ident)
            pos = -1
            for d in deps:
                dk = decl_index.get(d)
                if dk is not None and dk < k:
                    pos = max(pos, dk)
            for d in re.findall(r'([^\W\d]\w*)\s*::', proto):   # tipo anidado: la clase debe estar completa
                dk = class_def.get(d)
                if dk is not None and dk < k:
                    pos = max(pos, dk)
            # quitar los valores por defecto de la definición (quedan en el prototipo)
            for a, b in default_ranges:
                for q in range(a, b + 1):
                    P[q].blank()
            wrapped = []
            for frame in it['cond']:
                wrapped.extend(frame)
            text = '\n'.join(wrapped + [proto] + ['#endif'] * len(it['cond']))
            inserts.setdefault(pos, []).append((text, name_tok))

        # Declaraciones adelantadas de clases/estructuras + prototipos sin dependencias
        head_parts = []
        for k, decl in classes:
            head_parts.append((decl, P[items[k]['start']]))
        head_parts.extend(inserts.pop(-1, []))
        self.head_inserts = head_parts
        for k, lst in inserts.items():
            last_tok = P[items[k]['end']]
            for text, origin_tok in lst:
                last_tok.post.append(('\n' + text, (origin_tok.file, origin_tok.line)))

    def is_function_head(self, P, start, brace, fp, fc):
        if fp is None or fc is None or fc > brace:
            return False
        texts = [P[q].text for q in range(start, brace)]
        j = 0
        if texts and texts[0] == 'template' and len(texts) > 1 and texts[1] == '<':
            j = self.skip_angle(P[start:brace], 1)
        if j < len(texts) and texts[j] in ('struct', 'class', 'enum', 'union', 'typedef', 'namespace'):
            return False
        if P[brace - 1].text == '=':
            return False
        return True

    def run(self):
        self.collect_types()
        self.pass_input_group()
        self.pass_directives_and_tokens()
        self.pass_input()
        self.pass_arrays()
        self.pass_param_checks()
        self.pass_zero_init()
        self.pass_prototypes()


def build_output(tr, toks, head_inserts):
    lines = []
    origins = []
    cur = []
    cur_origin = [None]
    state = {'origin': None}

    def add_piece(text, origin):
        parts = text.split('\n')
        for idx, part in enumerate(parts):
            if idx > 0:
                lines.append(''.join(cur))
                origins.append(cur_origin[0] if cur_origin[0] is not None else state['origin'])
                cur[:] = []
                cur_origin[0] = None
            if part:
                cur.append(part)
                if cur_origin[0] is None and part.strip() and origin is not None:
                    cur_origin[0] = origin(idx) if callable(origin) else origin

    header = ['// Generado por mql5check.py - NO editar. Origen: %s' % ', '.join(sorted(tr.files))]
    for flag in sorted(tr.flags):
        header.append('#define MQL5CHECK_INC_%s 1' % flag)
    header.append('#include "%s"' % SHIM)
    for h in header:
        add_piece(h + '\n', None)
    for text, tok in head_inserts:
        add_piece(text + '\n', (tok.file, tok.line))
    for t in toks:
        for s, o in t.pre:
            add_piece(s, o if o is not None else (t.file, t.line))
        if t.text:
            f, l0 = t.file, t.line
            add_piece(t.text, (lambda k, f=f, l0=l0: (f, l0 + k)))
        if t.kind == 'nl':
            state['origin'] = (t.file, t.line + 1)
        for s, o in t.post:
            add_piece(s, o if o is not None else (t.file, t.line))
    lines.append(''.join(cur))
    origins.append(cur_origin[0])
    tr.cpp = '\n'.join(lines) + '\n'
    tr.line_origin = [None] + origins


def translate(path):
    tr = Translation()
    toks = load_file(path, tr, [], {os.path.abspath(path)})
    tl = Translator(tr, toks)
    tl.run()
    build_output(tr, toks, tl.head_inserts)
    tr.translator = tl
    return tr


# ---------------------------------------------------------------------------
# Compilación y diagnósticos
# ---------------------------------------------------------------------------
DIAG_RE = re.compile(r'^(?P<file>.*?):(?P<line>\d+):(?P<col>\d+): (?P<sev>error|warning|note|fatal error): (?P<msg>.*)$')
CTX_RE = re.compile(r'^(?P<file>.*?):(?P<line>\d+):(?P<col>\d+):\s+(?P<msg>required from .*|required by .*|in .*expansion.*)$')

INT_TYPES = r"(?:bool|char|signed char|unsigned char|uchar|short(?: int)?|short unsigned int|ushort|int|unsigned int|uint|long(?: int)?|long unsigned int|ulong|long long(?: int)?|long long unsigned int)"
NUM_TYPES = r"(?:%s|float|double|long double|datetime|color)" % INT_TYPES


class Diagnostic(object):
    def __init__(self, sev, file, line, col, msg):
        self.sev = sev
        self.file = file
        self.line = line
        self.col = col
        self.msg = msg
        self.notes = []
        self.context = []
        self.hint = None


def run_gxx(cxx, cpp_path, syntax_only):
    cmd = [cxx, '-std=c++17', '-x', 'c++', '-fno-operator-names', '-fdiagnostics-plain-output',
           '-fno-diagnostics-show-caret', '-fdiagnostics-color=never', '-fmax-errors=200',
           '-ftemplate-backtrace-limit=3', '-Wno-builtin-declaration-mismatch', '-Wno-c++20-compat',
           '-Wno-builtin-macro-redefined', '-Wno-attributes'] + GXX_WARNING_FLAGS
    if syntax_only:
        cmd += ['-fsyntax-only']
    else:
        cmd += ['-S', '-o', os.devnull]   # como -fsyntax-only + análisis de flujo (-Wreturn-type)
    cmd.append(cpp_path)
    env = dict(os.environ, LC_ALL='C', LANG='C', LANGUAGE='C')   # mensajes en inglés con comillas ASCII
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, env=env)
    return p.returncode, p.stderr


def parse_gxx(output):
    diags = []
    pending_ctx = []
    for raw in output.splitlines():
        m = DIAG_RE.match(raw)
        if m:
            sev = m.group('sev')
            d = (m.group('file'), int(m.group('line')), int(m.group('col')), m.group('msg'))
            if sev == 'note':
                if diags:
                    diags[-1].notes.append(d)
                continue
            dg = Diagnostic('error' if sev.startswith('fatal') else sev, *d)
            dg.context = pending_ctx
            pending_ctx = []
            diags.append(dg)
            continue
        m = CTX_RE.match(raw)
        if m:
            pending_ctx.append((m.group('file'), int(m.group('line')), int(m.group('col')), m.group('msg')))
    return diags


def pretty(msg):
    s = msg
    s = re.sub(r'mql_fixed_array<(.+?), (\d+|[A-Za-z_]\w*)>', r'\1[\2]', s)
    for _ in range(3):
        s = re.sub(r'mql_array<([^<>]*(?:<[^<>]*>[^<>]*)*)>', r'\1[]', s)
    s = re.sub(r'mql_enum_param<(\w+)>', r'\1', s)
    s = re.sub(r"'(mql_\w+)' \{aka '[^']*'\}", r"'\1'", s)
    for alias, real in (('mql_tf', 'ENUM_TIMEFRAMES'), ('mql_price', 'ENUM_APPLIED_PRICE'),
                        ('mql_ma', 'ENUM_MA_METHOD'), ('mql_vol', 'ENUM_APPLIED_VOLUME'),
                        ('mql_order_type', 'ENUM_ORDER_TYPE'), ('mql_objprop_i', 'ENUM_OBJECT_PROPERTY_INTEGER'),
                        ('mql_objprop_d', 'ENUM_OBJECT_PROPERTY_DOUBLE'), ('mql_objprop_s', 'ENUM_OBJECT_PROPERTY_STRING')):
        s = re.sub(r'\b%s\b' % alias, real, s)
    s = s.replace(' [-fpermissive]', '')
    s = re.sub(r' \[-W[\w=+-]+\]', '', s)
    s = s.replace('mql_null_t', 'NULL').replace('mql_null', 'NULL')
    s = s.replace('mql_wrong_value_t', 'WRONG_VALUE').replace('mql_wrong_value', 'WRONG_VALUE')
    s = re.sub(r'mql_(?:arith|numlike|notstr)_r<T, (\w+)>', r'\1', s)
    s = re.sub(r'(\w+)' + RENAME_SUFFIX, r'\1', s)
    s = s.replace('long unsigned int', 'ulong').replace('short unsigned int', 'ushort')
    s = s.replace('unsigned char', 'uchar').replace('unsigned int', 'uint')
    s = s.replace('long int', 'long').replace('short int', 'short')
    s = re.sub(r"string\((\"(?:\\.|[^\"\\])*\")\)", r'\1', s)
    s = re.sub(r"'([^']*)' \{aka '\1'\}", r"'\1'", s)
    s = re.sub(r' \[with [^\]]*\]', '', s)
    s = re.sub(r'typename std::enable_if<[^>]*>::type', '', s)
    return s


HINTS = [
    (r'was not declared in this scope', 'identificador no declarado: ¿errata, variable/función inexistente o falta un #include?'),
    (r'no matching function for call', 'ninguna versión de la función acepta estos argumentos: revise el número y los tipos'),
    (r'too (many|few) arguments', 'número de argumentos incorrecto'),
    (r"expected '[;,)]'", "falta un ';', ',' o ')' (o sobra algo) justo antes de este punto"),
    (r'expected .* before', 'error de sintaxis: revise la línea indicada y la anterior (¿falta un ;?)'),
    (r'(cannot|could not) convert|invalid conversion|no match for .operator', 'tipos incompatibles'),
    (r'assignment of read-only|read-only (variable|location)', 'no se puede modificar: es una constante o un parámetro input'),
    (r'has no member named', 'ese miembro/método no existe en esa estructura o clase'),
    (r'does not name a type', 'tipo desconocido: ¿errata o falta un #include?'),
    (r'redeclaration|redefinition|conflicting declaration', 'nombre declarado dos veces'),
    (r'use of deleted function .*operator[-*/%]', 'en MQL5 las cadenas solo admiten +'),
]


def classify(dg, tr, cpp_lines):
    """Ajusta la severidad a la de MQL5 y traduce el mensaje. Devuelve (sev, msg) o None para descartar."""
    msg = dg.msg
    enums = tr.enum_types
    m = re.match(r"invalid conversion from '(%s)' to '(\w+)' \[-fpermissive\]" % INT_TYPES, msg)
    if m and m.group(2) in enums:
        return 'warning', "conversión implícita de entero a enum '%s' (MQL5 la acepta; revise que el valor sea válido)" % m.group(2)
    m = re.match(r"invalid conversion from '(?:const )?(\w+)\*' to '(?:const )?(\w+)\*' \[-fpermissive\]", msg)
    if m and is_derived(tr.class_graph, m.group(2), m.group(1)):
        return None   # conversión implícita base -> derivada: MQL5 la acepta (se verifica al ejecutar)
    if re.search(r"cannot convert 'string' to '%s'" % NUM_TYPES, msg) or \
            re.search(r"conversion from 'string' to non-scalar type '(datetime|color)' requested", msg):
        return 'warning', "MQL5: implicit conversion from 'string' to 'number' (conversión implícita de cadena a número)"
    m = re.search(r"conversion from '(\w+)' to non-scalar type 'string' requested", msg)
    if m and m.group(1) in enums:
        return 'warning', "MQL5: implicit conversion from 'number' to 'string' (enum convertido a cadena)"
    if dg.sev == 'warning':
        m = re.search(r"is deprecated: (MQL5: .*?) \[-Wdeprecated-declarations\]", msg)
        if m:
            return 'warning', m.group(1)
        if '-Wreturn-type' in msg:
            return 'error', "no todos los caminos devuelven un valor (MQL5: 'not all control paths return a value')"
        if '-Wshadow' in msg:
            return 'warning', pretty(msg) + ' (MQL5 avisa: la declaración oculta otra)'
        if '-Wfloat-conversion' in msg or '-Wconversion' in msg:
            return 'warning', pretty(msg) + ' (MQL5: possible loss of data due to type conversion)'
        if '-Wsign-compare' in msg:
            return 'warning', pretty(msg) + " (MQL5: 'sign mismatch')"
        return 'warning', pretty(msg)
    m = re.search(r"'(\w+)%s'" % RENAME_SUFFIX, msg)
    if m and dg.sev == 'error':
        return 'error', "'%s' es una palabra clave de C++, no de MQL5" % m.group(1)
    if dg.sev == 'error' and 'no return statement in function returning non-void' in msg:
        return 'error', "la función no devuelve ningún valor (MQL5: 'not all control paths return a value')"
    return dg.sev, pretty(msg)


def is_derived(graph, derived, base):
    seen = set()
    todo = [derived]
    while todo:
        c = todo.pop()
        if c in seen:
            continue
        seen.add(c)
        for b in graph.get(c, ()):
            if b == base:
                return True
            todo.append(b)
    return False


def map_location(dg, tr, cpp_path):
    """(archivo, línea) original del diagnóstico, o None."""
    cands = [(dg.file, dg.line)]
    cands += [(f, l) for f, l, c, m in reversed(dg.context)]
    cands += [(f, l) for f, l, c, m in dg.notes]
    for f, l in cands:
        if os.path.abspath(f) == os.path.abspath(cpp_path) and 0 < l < len(tr.line_origin):
            o = tr.line_origin[l]
            if o is not None:
                return o
    return None


def pointer_dot_fixes(diags, cpp_path, cpp_lines):
    """Errores 'request for member ... which is of pointer type' -> reescribir '.' como '->'."""
    fixes = []
    for dg in diags:
        if dg.sev != 'error':
            continue
        m = re.match(r"request for member '(.+?)' in '(.+?)', which is of pointer type '(.+?)'", dg.msg)
        if not m or os.path.abspath(dg.file) != os.path.abspath(cpp_path):
            continue
        line = cpp_lines[dg.line - 1]
        k = dg.col - 2
        while k >= 0 and line[k] in ' \t':
            k -= 1
        if k >= 0 and line[k] == '.':
            fixes.append((dg.line, k, m.group(2), m.group(3)))
    return fixes


def pointer_ref_fixes(diags, cpp_path, cpp_lines, graph):
    """'invalid initialization of reference of type X& from expression of type Y*': MQL5 convierte
    automáticamente el puntero en referencia al pasar argumentos -> reescribir como *ptr."""
    fixes = []
    for dg in diags:
        if dg.sev != 'error' or os.path.abspath(dg.file) != os.path.abspath(cpp_path):
            continue
        m = re.match(r"invalid initialization of (?:non-const )?reference of type '(?:const )?(\w+)&' "
                     r"from expression of type '(?:const )?(\w+)\*'", dg.msg)
        if not m or not (m.group(1) == m.group(2) or is_derived(graph, m.group(2), m.group(1))):
            continue
        line = cpp_lines[dg.line - 1]
        k = dg.col - 1
        mm = re.match(r'[^\W\d]\w*(?:\s*(?:\.|->)\s*[^\W\d]\w*)*(?:\s*\[[^\]]*\])?\s*[,)]', line[k:])
        if mm:
            fixes.append((dg.line, k, line[k:k + mm.end()].rstrip(',) \t'), m.group(2) + '*'))
    return fixes


def check_file(path, args, out):
    try:
        tr = translate(path)
    except OSError as e:
        out.append('%s: error: no se puede leer el archivo (%s)' % (path, e))
        return 1, 0, True
    workdir = tempfile.mkdtemp(prefix='mql5check-')
    base = os.path.splitext(os.path.basename(path))[0]
    cpp_path = os.path.join(workdir, base + '.cpp')
    cpp_lines = tr.cpp.split('\n')
    results = []   # (sev, file, line, msg, hint)
    for sev, f, l, msg in tr.diags:
        results.append((sev, f, l, msg, None))

    gxx_diags = []
    seen_fix = set()
    for _ in range(10):
        with open(cpp_path, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(cpp_lines))
        rc, output = run_gxx(args.cxx, cpp_path, args.syntax_only)
        if args.debug:
            sys.stderr.write(output)
        gxx_diags = parse_gxx(output)
        fixes = [('dot',) + fx for fx in pointer_dot_fixes(gxx_diags, cpp_path, cpp_lines)]
        fixes += [('ref',) + fx for fx in pointer_ref_fixes(gxx_diags, cpp_path, cpp_lines, tr.class_graph)]
        fixes = [fx for fx in fixes if (fx[1], fx[2]) not in seen_fix]
        if not fixes:
            break
        for kind, gl, k, expr, ptype in sorted(fixes, key=lambda x: (x[1], -x[2])):
            seen_fix.add((gl, k))
            line = cpp_lines[gl - 1]
            o = tr.line_origin[gl] if gl < len(tr.line_origin) else None
            if kind == 'dot':
                cpp_lines[gl - 1] = line[:k] + '->' + line[k + 1:]
                msg = ("acceso con '.' al puntero '%s' (%s): válido en MQL5, sin equivalente en C++; "
                       "se comprueba como '->'" % (pretty(expr), pretty(ptype)))
            else:
                cpp_lines[gl - 1] = line[:k] + '*' + line[k:]
                msg = ("se pasa el puntero '%s' (%s) a un parámetro por referencia: MQL5 lo convierte "
                       "automáticamente (en C++ sería '*%s')" % (pretty(expr), pretty(ptype), pretty(expr)))
            if o:
                results.append(('warning', o[0], o[1], msg, None))

    for dg in gxx_diags:
        loc = map_location(dg, tr, cpp_path)
        cl = classify(dg, tr, cpp_lines)
        if cl is None:
            continue
        sev, msg = cl
        # Error dentro de una macro: informar en el punto de uso (la expansión más externa)
        uses = [(l, re.search(r"in expansion of macro '(\w+)'", m).group(1)) for f, l, c, m in dg.notes
                if 'in expansion of macro' in m and os.path.abspath(f) == os.path.abspath(cpp_path)]
        if uses and loc is not None:
            use_line, macro = uses[-1]
            o = tr.line_origin[use_line] if use_line < len(tr.line_origin) else None
            if o is not None and o != loc:
                msg += ' (en la expansión de la macro %s, definida en %s:%d)' % (macro, display(loc[0], path), loc[1])
                loc = o
        hint = None
        if sev == 'error':
            for pat, h in HINTS:
                if re.search(pat, dg.msg):
                    hint = h
                    break
        notes = []
        for f, l, c, nmsg in dg.notes[:6]:
            if os.path.abspath(f) == os.path.abspath(cpp_path):
                o = tr.line_origin[l] if l < len(tr.line_origin) else None
                where = '%s:%d' % (display(o[0], path), o[1]) if o else 'código generado:%d' % l
            elif os.path.abspath(f) == SHIM:
                where = 'mql5_shim.hpp:%d' % l
            else:
                where = '%s:%d' % (os.path.basename(f), l)
            notes.append('%s: %s' % (where, pretty(nmsg)))
        if loc is None:
            where_file, where_line = path, 0
            msg = msg + ' [ubicación no mapeada: %s:%d]' % (os.path.basename(dg.file), dg.line)
        else:
            where_file, where_line = loc
        results.append((sev, where_file, where_line, msg, (hint, notes)))

    # Salida ordenada y sin duplicados
    uniq = []
    seen = set()
    for r in results:
        key = (r[0], r[1], r[2], r[3])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)
    if args.no_warnings:
        uniq = [r for r in uniq if r[0] == 'error']
    uniq.sort(key=lambda r: (r[1] != os.path.abspath(path), r[1], r[2], r[0] != 'error'))
    n_err = sum(1 for r in uniq if r[0] == 'error')
    n_warn = sum(1 for r in uniq if r[0] == 'warning')
    for sev, f, l, msg, extra in uniq:
        out.append('%s:%d: %s: %s' % (display(f, path), l, 'error' if sev == 'error' else 'advertencia', msg))
        if not args.no_source:
            src = tr.source_lines.get(f)
            if src and 0 < l <= len(src):
                out.append('    %5d | %s' % (l, src[l - 1].rstrip()))
        if extra:
            hint, notes = extra
            if hint:
                out.append('          pista: %s' % hint)
            if args.notes:
                for nt in notes:
                    out.append('          nota: %s' % nt)
    out.append('%s: %d error(es), %d advertencia(s)' % (path, n_err, n_warn))
    if args.keep:
        out.append('  C++ generado: %s' % cpp_path)
    else:
        shutil.rmtree(workdir, ignore_errors=True)
    return n_err, n_warn, False


def display(f, main_path):
    try:
        rel = os.path.relpath(f)
    except ValueError:
        rel = f
    return rel if not rel.startswith('..') else f


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='Comprobador estático de MQL5: traduce a C++ y compila con g++ contra un shim de la API. '
                    'No sustituye a MetaEditor.')
    ap.add_argument('files', nargs='+', help='archivos .mq5/.mqh')
    ap.add_argument('--keep', action='store_true', help='conservar el .cpp generado (se muestra la ruta)')
    ap.add_argument('--strict', action='store_true', help='las advertencias también cuentan como fallo (código 1)')
    ap.add_argument('--no-warnings', action='store_true', help='no mostrar advertencias')
    ap.add_argument('--no-source', action='store_true', help='no mostrar la línea de código de cada diagnóstico')
    ap.add_argument('--notes', action='store_true', help='mostrar las notas de g++ (candidatos, etc.)')
    ap.add_argument('--syntax-only', action='store_true',
                    help='usar g++ -fsyntax-only (más rápido, pero no detecta "no todos los caminos devuelven valor")')
    ap.add_argument('--cxx', default=os.environ.get('MQL5CHECK_CXX', 'g++'), help='compilador (por defecto g++)')
    ap.add_argument('--debug', action='store_true', help='mostrar la salida cruda de g++')
    args = ap.parse_args(argv)

    if shutil.which(args.cxx) is None:
        sys.stderr.write('mql5check: no se encuentra el compilador "%s" (instale g++)\n' % args.cxx)
        return 2
    total_err = 0
    total_warn = 0
    tool_fail = False
    for f in args.files:
        out = []
        if not os.path.isfile(f):
            print('%s: error: el archivo no existe' % f)
            tool_fail = True
            continue
        e, w, fail = check_file(f, args, out)
        print('\n'.join(out))
        total_err += e
        total_warn += w
        tool_fail = tool_fail or fail
    if len(args.files) > 1:
        print('TOTAL: %d error(es), %d advertencia(s) en %d archivo(s)' % (total_err, total_warn, len(args.files)))
    if tool_fail:
        return 2
    if total_err or (args.strict and total_warn):
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
