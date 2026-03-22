from pathlib import Path
import sys

from win32com.propsys import propsys, pscon
from win32com.shell import shellcon


def main() -> int:
    if len(sys.argv) != 3:
        print('usage: set_shortcut_app_id.py <shortcut-path> <app-id>')
        return 1

    shortcut_path = Path(sys.argv[1]).resolve()
    app_id = sys.argv[2]
    store = propsys.SHGetPropertyStoreFromParsingName(
        str(shortcut_path),
        None,
        shellcon.GPS_READWRITE,
        propsys.IID_IPropertyStore,
    )
    store.SetValue(pscon.PKEY_AppUserModel_ID, propsys.PROPVARIANTType(app_id))
    store.Commit()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
