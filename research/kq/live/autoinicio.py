"""Arranque automático del bot de Topstep en Windows, sin tener que usar el PC.

Una vez, desde la carpeta ``research``::

    python -m kq.live.autoinicio --instalar

Qué hace:
* guarda tu usuario en ``usuario_topstepx.txt`` y tu API key en ``clave_topstepx.txt`` (solo en tu PC;
  no se suben a git), para que el bot arranque sin preguntar;
* crea ``iniciar_bot.cmd`` (doble clic = arrancar el bot) con las configuraciones que tengas;
* lo añade a la carpeta de Inicio de Windows: al iniciar sesión, el bot arranca solo en modo ``--auto``
  (si pierde internet o falla, vuelve a intentarlo cada 60 s);
* quita la suspensión y la hibernación con el PC enchufado.

El PC tiene que estar encendido: Topstep prohíbe usar la API desde un VPS o un servidor remoto.
Para quitarlo:  python -m kq.live.autoinicio --quitar
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from .topstep_bot import KEY_FILE, USER_FILE

CONFIGS = ["topstep.json", "topstep_oro_noche.json", "topstep_mnq.json"]
LAUNCHER = "iniciar_bot.cmd"
STARTUP_NAME = "KatheBot.cmd"


def startup_dir() -> Path:
    return Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def write_launcher(workdir: Path, configs: list[str], python: str = sys.executable) -> Path:
    """Archivo .cmd (solo ASCII: cmd.exe no lee bien otros caracteres) que arranca el bot en modo --auto."""
    cfg_args = " ".join(f'--config "{c}"' for c in configs)
    lines = ["@echo off",
             "rem Arranca KatheBot en modo desatendido (creado por python -m kq.live.autoinicio --instalar)",
             f'cd /d "{workdir}"',
             "title KatheBot - no cierres esta ventana",
             f'"{python}" -m kq.live.topstep_bot {cfg_args} --auto',
             "pause"]
    path = workdir / LAUNCHER
    path.write_text("\r\n".join(lines) + "\r\n", encoding="ascii", errors="replace")
    return path


def ensure_credentials(workdir: Path, input_fn=input, getpass_fn=None) -> None:
    import getpass
    getpass_fn = getpass_fn or getpass.getpass
    user_path, key_path = workdir / USER_FILE, workdir / KEY_FILE
    if not user_path.exists():
        user = input_fn("Usuario de TopstepX (el del correo de Topstep; en tu caso, tu email): ").strip()
        user_path.write_text(user + "\n", encoding="utf-8")
    if not key_path.exists():
        key = getpass_fn("API key de TopstepX (no se verá; pégala con clic derecho y pulsa Enter): ").strip()
        key_path.write_text(key + "\n", encoding="utf-8")
    print(f"Credenciales guardadas solo en este PC: {user_path.name} y {key_path.name}. No los compartas.")


def install(workdir: Path | None = None, configs: list[str] | None = None, input_fn=input, getpass_fn=None,
            run=subprocess.run, startup: Path | None = None, python: str = sys.executable) -> int:
    workdir = (workdir or Path.cwd()).resolve()
    configs = [c for c in (configs or CONFIGS) if (workdir / c).exists()]
    if not configs:
        print(f"No encuentro ninguna configuración ({', '.join(CONFIGS)}) en {workdir}. "
              "Ejecuta esto desde la carpeta research.")
        return 1
    ensure_credentials(workdir, input_fn, getpass_fn)
    launcher = write_launcher(workdir, configs, python)
    startup = startup or startup_dir()
    startup.mkdir(parents=True, exist_ok=True)
    entry = startup / STARTUP_NAME
    entry.write_text(f'@echo off\r\ncall "{launcher}"\r\n', encoding="ascii", errors="replace")
    for arg in ("standby-timeout-ac", "hibernate-timeout-ac"):
        try:
            run(["powercfg", "/change", arg, "0"], check=False, capture_output=True)
        except OSError:
            print(f"(no se pudo ajustar {arg}: hazlo en Configuración > Sistema > Energía)")
    print(f"Listo.\n- Arranque manual: doble clic en {launcher}\n- Arranque automático al iniciar sesión: {entry}\n"
          f"- Mercados: {', '.join(configs)}\n- Suspensión y hibernación con el PC enchufado: desactivadas.\n"
          "Si Windows se reinicia, el bot arranca en cuanto inicies sesión.")
    return 0


def remove(startup: Path | None = None) -> int:
    entry = (startup or startup_dir()) / STARTUP_NAME
    if entry.exists():
        entry.unlink()
        print("Arranque automático quitado. El bot ya no arrancará solo al iniciar sesión.")
    else:
        print("No había arranque automático instalado.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Arranque automático del bot de Topstep en Windows")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--instalar", action="store_true")
    g.add_argument("--quitar", action="store_true")
    a = ap.parse_args(argv)
    return install() if a.instalar else remove()


if __name__ == "__main__":
    sys.exit(main())
