import sys

from .gui_main import main as gui_main
from .main import main as cli_main


def main() -> int:
    args = sys.argv[1:]
    if "--cli" in args:
        cli_main()
        return 0

    start_minimized = "--minimized" in args or "--tray" in args
    return gui_main(start_minimized=start_minimized)


if __name__ == "__main__":
    raise SystemExit(main())
