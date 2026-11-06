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
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError("Source non autorisée")
    if mode not in {"html", "rss"}:
        raise ValueError("Type de source non reconnu")
    req = Request(url, headers={
        "User-Agent": "TerriNormesVeille/1.3 (veille-documentaire; identification logicielle)",
        "Accept": "application/rss+xml,application/atom+xml,application/xml,text/xml" if mode == "rss" else "text/html,application/xhtml+xml",
    })
    with urlopen(req, timeout=25) as response:
        final = urlparse(response.url)
        if final.scheme != "https" or final.hostname not in ALLOWED_HOSTS:
            raise ValueError("Redirection vers un domaine non autorisé")
        ctype = response.headers.get("Content-Type", "").lower()
        allowed_types = ("xml", "rss", "atom") if mode == "rss" else ("html",)
        if not any(x in ctype for x in allowed_types):
            raise ValueError("Format de réponse inattendu pour cette source")
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("Source trop volumineuse pour cette surveillance")
        charset = response.headers.get_content_charset() or "utf-8"
    if mode == "rss":
        return rss_digest(raw)
    parser = MainText()
    parser.feed(raw.decode(charset, errors="replace"))
    content = parser.result()
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def main():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    old_data = json.loads(DEST.read_text(encoding="utf-8")) if DEST.exists() else {}
    previous = {s.get("id"): s for s in old_data.get("sources", [])}
    at = now()
    records = []
    for cfg in config:
        old = previous.get(cfg["id"], {})
        mode = cfg.get("mode", "html")
        rec = {
            "id": cfg["id"], "nom": cfg["nom"], "url": cfg["url"],
            "mode": mode, "page_url": cfg.get("page_url"),
            "source_ids": cfg["source_ids"],
            "last_attempt_at": old.get("last_attempt_at") if mode == "manuel" else at,
            "last_success_at": old.get("last_success_at"),
            "baseline_at": old.get("baseline_at"),
            "last_change_at": old.get("last_change_at"),
            "digest": old.get("digest"),
            "history": old.get("history", [])[-40:],
        }
        if mode == "manuel":
            # Le portail reste consultable, sans simuler une vérification automatique.
            rec["status"] = "verification_manuelle"
            rec["last_error"] = None
            rec["last_success_at"] = None
            rec["digest"] = None
            rec["last_change_at"] = None
            records.append(rec)
            continue
        try:
            digest = fetch_digest(cfg["url"], mode)
            rec["last_success_at"] = at
            rec["digest"] = digest
            rec["last_error"] = None
            if not old.get("digest"):
                rec["status"] = "initialisation"
                rec["baseline_at"] = at
                rec["history"].append({"date": at, "evenement": "premiere_empreinte"})
            elif old["digest"] != digest:
                rec["status"] = "page_modifiee"
                rec["last_change_at"] = at
                rec["history"].append({"date": at, "evenement": "page_modifiee"})
            else:
                rec["status"] = "sans_nouveau_changement"
        except Exception as exc:
            # Une erreur HTTP, un blocage anti-bot ou une panne ne prouve pas un changement de droit.
            rec["status"] = "controle_impossible"
            rec["last_error"] = f"{type(exc).__name__}: {str(exc)[:180]}"
            print(f"AVERTISSEMENT {cfg['id']}: {rec['last_error']}", file=sys.stderr)
        rec["history"] = rec["history"][-40:]
        records.append(rec)
    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text(json.dumps({"schema": 1, "last_run_at": at, "sources": records}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"TerriNormes : {len(records)} pages traitées, journal écrit dans {DEST}")


if __name__ == "__main__":
    main()
