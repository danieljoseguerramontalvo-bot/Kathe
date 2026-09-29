"""Comprueba que cada preset .set tiene exactamente los inputs del EA, en su orden y con valores
del tipo correcto.

    python3 tools/mql5check/check_presets.py MQL5/Experts/KatheQuant_v5.mq5 MQL5/Presets/v5/*.set
"""
import re
import sys

INPUT_RE = re.compile(r'^\s*(?:sinput|input)\s+([A-Za-z_][A-Za-z0-9_]*)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^;]+);')


def ea_inputs(path):
    out = []
    for line in open(path, encoding="utf-8", errors="replace"):
        m = INPUT_RE.match(line)
        if m:
            out.append((m.group(2), m.group(1)))
    return out


def check_value(typ, val):
    if typ == "bool":
        return val in ("true", "false")
    if typ in ("int", "long", "uint", "ulong"):
        return re.fullmatch(r"-?\d+", val) is not None
    if typ == "double":
        return re.fullmatch(r"-?\d+(\.\d+)?", val) is not None
    if typ == "string":
        return True
    return re.fullmatch(r"-?\d+", val) is not None        # enums are written as integers


def main(argv):
    ea, sets = argv[1], argv[2:]
    inputs = ea_inputs(ea)
    names = [n for n, _ in inputs]
    types = dict(inputs)
    bad = 0
    for f in sets:
        raw = open(f, "rb").read()
        text = raw.decode("utf-8")
        problems = []
        if b"\n" in raw.replace(b"\r\n", b""):
            problems.append("finales de línea que no son CRLF")
        kv = [ln.split("=", 1) for ln in text.split("\r\n") if ln and not ln.startswith(";")]
        got = [k for k, _ in kv]
        if got != names:
            missing = [n for n in names if n not in got]
            extra = [k for k in got if k not in names]
            problems.append(f"inputs distintos del EA (faltan {missing}, sobran {extra}, orden {'igual' if not missing and not extra else '-'})")
        for k, v in kv:
            if k in types and not check_value(types[k], v):
                problems.append(f"{k}={v} no es un {types[k]}")
        if problems:
            bad += 1
            print(f"{f}: " + "; ".join(problems))
    print(f"{len(sets)} presets, {len(names)} inputs en el EA, {bad} con problemas")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
