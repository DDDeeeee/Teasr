from pathlib import Path

_pkg_dir = Path(__file__).resolve().parent
_src_pkg_dir = _pkg_dir.parent / 'src' / 'asr_app'

if not _src_pkg_dir.exists():
    raise ModuleNotFoundError(f'Missing source package: {_src_pkg_dir}')

__path__ = [str(_src_pkg_dir)]
