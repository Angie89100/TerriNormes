
#!/usr/bin/env python3
"""Veille technique de pages publiques : ne constitue pas une validation juridique."""
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "veille" / "sources.json"
DEST = ROOT / "data" / "veille.json"
MAX_BYTES = 3_000_000
ALLOWED_HOSTS = {
    "www.economie.gouv.fr",
    "www.collectivites-locales.gouv.fr",
    "www.cnil.fr",
}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class MainText(HTMLParser):
    OMIT = {"script", "style", "svg", "nav", "footer", "noscript"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.all_text = []
        self.main_text = []
        self.main_depth = 0

    def handle_starttag(self, tag, attrs):
        self.stack.append(tag)
        if tag == "main":
            self.main_depth += 1

    def handle_endtag(self, tag):
        if tag == "main" and self.main_depth:
            self.main_depth -= 1
        if tag in self.stack:
            pos = len(self.stack) - 1 - self.stack[::-1].index(tag)
            self.stack = self.stack[:pos]

    def handle_data(self, data):
        if any(t in self.OMIT for t in self.stack):
            return
        t = " ".join(data.split())
        if not t:
            return
        self.all_text.append(t)
        if self.main_depth:
            self.main_text.append(t)

    def result(self):
        main = " ".join(self.main_text)
        text = main if len(main) > 250 else " ".join(self.all_text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 300:
            raise ValueError("Contenu trop court ou inaccessible ; aucun changement juridique conclu")
        return text


def rss_digest(raw):
    """Empreinte des éléments d'un flux de publications (pas du droit en vigueur)."""
    root = ET.fromstring(raw)
    is_rss = root.tag in ("rss", "RDF") or root.tag.endswith("}RDF")
    is_atom = root.tag == "{http://www.w3.org/2005/Atom}feed"
    if not (is_rss or is_atom):
        raise ValueError("Flux RSS/Atom invalide : format inattendu")
    # Ne pas utiliser les horodatages globaux du flux, souvent modifiés à chaque lecture.
    if is_atom:
        ns = "{http://www.w3.org/2005/Atom}"
        elements = root.findall(f"{ns}entry")
        entries = []
        for e in elements:
            link = next((a.get("href", "") for a in e.findall(f"{ns}link") if a.get("href")), "")
            entries.append([e.findtext(f"{ns}id") or "", e.findtext(f"{ns}title") or "", link, e.findtext(f"{ns}updated") or ""])
    else:
        elements = root.findall(".//item")
        entries = [[e.findtext("guid") or "", e.findtext("title") or "", e.findtext("link") or "", e.findtext("pubDate") or ""] for e in elements]
    # L'absence d'articles ne doit pas devenir silencieusement un contrôle réussi.
    if not entries:
        raise ValueError("Flux RSS/Atom vide ou illisible")
    normalized = [[" ".join(str(field).split()) for field in entry] for entry in entries[:30]]
    return hashlib.sha256(json.dumps(normalized, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def fetch_digest(url, mode="html"):
    parsed = urlparse(url)
