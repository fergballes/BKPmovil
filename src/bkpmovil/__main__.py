"""Punto de entrada: sin argumentos abre la ventana; con argumentos, la CLI."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] not in ("--gui", "-g"):
        from .cli import main as cli_main

        return cli_main(argv)

    from .ui.app import run

    return run()


if __name__ == "__main__":
    raise SystemExit(main())
