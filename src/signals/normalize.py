"""Names and domains in a comparable form. Identifiers decide, names propose: a domain is an identifier."""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse

LEGAL = {"gmbh", "ag", "se", "kg", "ug", "ohg", "gbr", "mbh", "co", "inc", "ltd", "llc", "sas", "sa", "sarl", "bv",
         "nv", "ab", "sl", "srl", "spa", "plc", "corp", "limited", "haftungsbeschränkt", "haftungsbeschraenkt"}
UMLAUT = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "é": "e", "è": "e", "à": "a", "ç": "c", "ø": "o", "å": "a"}


def transliterate(s: str) -> str:
    s = s.lower()
    for a, b in UMLAUT.items():
        s = s.replace(a, b)
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def name_key(name: str | None, transliterate_umlauts: bool = True) -> str:
    """Lowercase, umlauts transliterated, punctuation and legal forms removed: 'Grünfeld Robotics GmbH' ->
    'gruenfeld robotics'."""
    if not name:
        return ""
    s = transliterate(name) if transliterate_umlauts else name.lower()
    s = re.sub(r"[.,&/()'\"]", " ", s)
    s = s.replace("b v", "bv").replace("s l", "sl")
    tokens = [t for t in s.split() if t and t not in LEGAL and "".join(sorted(t)) not in _LEGAL_LETTERS]
    return " ".join(tokens)


_LEGAL_LETTERS = {"".join(sorted(x)) for x in LEGAL if len(x) >= 4}   # "GbmH" is a typed "GmbH"


def compact_key(name: str | None, transliterate_umlauts: bool = True) -> str:
    """The name run together with a trailing legal form removed: 'Lixft Pa yAG' -> 'lixftpay'."""
    c = name_key(name, transliterate_umlauts).replace(" ", "")
    for suffix in sorted(LEGAL, key=len, reverse=True):
        if c.endswith(suffix) and len(c) > len(suffix) + 3:
            return c[: -len(suffix)]
    return c


def domain_key(domain: str | None) -> str:
    """'https://www.Nova-Robotics.de/en/about' -> 'nova-robotics.de'."""
    if not domain:
        return ""
    d = domain.strip().lower()
    if "://" not in d:
        d = "http://" + d
    host = urlparse(d).hostname or ""
    return host[4:] if host.startswith("www.") else host
