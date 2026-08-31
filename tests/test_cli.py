import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pedald.cli import _resolve_config  # noqa: E402


def test_config_default_is_app_support_absolute():
    p = _resolve_config(None)
    assert p.is_absolute()
    assert p == Path("~/Library/Application Support/pedald/config.yaml").expanduser()


def test_relative_config_is_honoured_verbatim():
    assert _resolve_config("config.yaml") == Path("config.yaml")
    assert not _resolve_config("config.yaml").is_absolute()


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            n += 1
            print(f"ok  {name}")
    print(f"\n{n} passed")
