"""
i18n locale loader — reads JSON locale files and provides t() translation function.
Supports en | fr | ar with RTL detection.
"""
import json
from functools import lru_cache
from pathlib import Path

_LOCALES_PATH = Path(__file__).parent.parent / "locales"
_SUPPORTED = frozenset({"en", "fr", "ar"})
_DEFAULT = "en"


@lru_cache(maxsize=3)
def _load(lang: str) -> dict:
    path = _LOCALES_PATH / f"{lang}.json"
    if not path.exists():
        path = _LOCALES_PATH / f"{_DEFAULT}.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def t(key: str, lang: str = "en", **kwargs) -> str:
    """Translate key into lang. Falls back to English, then to the key itself."""
    lang = lang if lang in _SUPPORTED else _DEFAULT
    value = _load(lang).get(key) or _load(_DEFAULT).get(key, key)
    if kwargs:
        try:
            return value.format(**kwargs)
        except (KeyError, IndexError):
            return value
    return value


def get_locale_data(lang: str = "en") -> dict:
    """Return full translation dict for the given language."""
    return _load(lang if lang in _SUPPORTED else _DEFAULT)


def get_dir(lang: str = "en") -> str:
    """Return text direction (ltr | rtl) for the given language."""
    return _load(lang if lang in _SUPPORTED else _DEFAULT).get("dir", "ltr")
