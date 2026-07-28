"""Entry point del CLI de aia-jobs."""

import os
import sys

from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    """Punto de entrada del paquete aia-jobs.

    Subcomandos:
      listen   Arranca el listener de correo Yahoo (default).
    """
    args = sys.argv[1:]
    cmd = args[0] if args else "listen"

    if cmd in ("listen", "listener"):
        from listener.listener import main as _listen_main
        _listen_main()
    elif cmd in ("--version", "-v"):
        try:
            import tomllib
            with open(os.path.join(os.path.dirname(__file__), "..", "pyproject.toml"), "rb") as f:
                print(tomllib.load(f)["tool"]["poetry"]["version"])
        except Exception:
            print("?")
    else:
        print(f"Subcomando desconocido: {cmd}")
        print("Uso: aia-jobs [listen]")
        sys.exit(1)


if __name__ == "__main__":
    main()
