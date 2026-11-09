#!/usr/bin/env python3
"""Veille JORF ouverte (DILA), filtrage documentaire sans qualification juridique.

Ce programme ne modifie PAS les fiches du référentiel. Il produit veille.json,
qui présente des titres publiés au Journal officiel à vérifier sur Légifrance.
Dépend uniquement de la bibliothèque standard Python.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import logging
import re
import tarfile
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = 'https://echanges.dila.gouv.fr/OPENDATA/JORFSIMPLE/'
PATTERN = re.compile(r'(JORFSIMPLE_(\d{8})-(\d{6})\.tar\.gz)', re.I)
ID_RE = re.compile(r'JORFTEXT\d{12,17}')
LIMIT_BYTES = 18_000_000
MAX_MEMBER_BYTES = 2_500_000
MAX_MEMBERS = 3500
RETENTION_DAYS = 45

DOMAINS = [
    ('Statut & carrière', r'fonction publiqu|fonctionnaire|agent territorial|emploi public|recrutement|concours|mobilit[eé]|traitement indiciaire|grille indiciaire|indemnit[eé] de fonction|cong[eé] de maladie|protection sociale compl[eé]mentaire'),
    ('Institutions & actes locaux', r'collectivit[eé] territorial|commune\b|communal|intercommunal|m[eé]tropole\b|conseil municipal|maire\b|d[eé]partemental|r[eé]gional|contr[oô]le de l[eé]galit[eé]|pr[eé]fecture'),
    ('Commande publique', r'commande publique|march[eé] public|concession|achat public|pouvoir adjudicateur|march[eé]s de travaux'),
    ('Finances, budget & comptabilité', r'finances locales|dotation globale|fiscalit[eé] locale|budget communal|budget des collectivit[eé]s|m57\b|comptabilit[eé] publiqu|d[eé]pense publiqu|taxe fonci[eè]re'),
    ('Usagers & procédures', r'service public local|usagers|d[eé]marches administratives|relation entre le public|simplification administrative|acc[eè]s aux documents administratifs'),
    ('Enfance & éducation', r'petite enfance|accueil de loisirs|p[eé]riscolaire|restauration scolaire|cantine scolaire|[eé]cole maternelle|[eé]cole [eé]l[eé]mentaire|scolaris'),
    ('Sécurité & police', r'police municipale|vid[eé]oprotection|s[eé]curit[eé] civile|pr[eé]vention de la d[eé]linquance|tranquillit[eé] publique'),
    ('Numérique & données', r'protection des donn[eé]es|accessibilit[eé] num[eé]rique|cybers[eé]curit[eé]|syst[eè]me d.information public|rgaa\b|rgpd\b'),
    ('Urbanisme & patrimoine', r'urbanisme|permis de construire|domaine public|am[eé]nagement du territoire|propri[eé]t[eé] des personnes publiques'),
    ('Environnement & développement durable', r'gestion des d[eé]chets|assainissement|distribution d.eau|biodiversit[eé]|transition [eé]cologique|d[eé]chets m[eé]nagers'),
]
COMPILED = [(name, re.compile(expr, re.IGNORECASE)) for name, expr in DOMAINS]

def normalized(value: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', value.lower()) if not unicodedata.combining(c))

# Apply patterns to both original (accented) and normalized text (for mixed patterns).
PATTERNS = [(name, re.compile(normalized(expr), re.IGNORECASE)) for name, expr in DOMAINS]

def domains_for_title(title: str) -> list[str]:
    candidate = normalized(title)
    return [name for name, pattern in PATTERNS if pattern.search(candidate)]

def download(url: str, max_bytes: int = LIMIT_BYTES) -> bytes:
    req = urllib.request.Request(url, headers={'User-Agent': 'TerriNormes/2.0 (veille juridique ouverte, adresse: GitHub Pages)', 'Accept': '*/*'})
    with urllib.request.urlopen(req, timeout=35) as response:
        if response.status != 200:
            raise RuntimeError(f'HTTP {response.status} sur {url}')
        result = response.read(max_bytes + 1)
        if len(result) > max_bytes:
            raise ValueError('Téléchargement trop volumineux')
        return result

def available_archives(directory_html: str, today: dt.date, lookback: int = 8) -> list[tuple[dt.date, str]]:
    matches: dict[dt.date, tuple[str, str]] = {}
    for filename, ymd, hms in PATTERN.findall(directory_html):
        try:
            day = dt.datetime.strptime(ymd, '%Y%m%d').date()
        except ValueError:
            continue
        # Les lots publiés autour de minuit correspondent principalement à l'édition quotidienne.
        # Les gros lots du soir sont souvent des corrections ; ils ne sont pas indexés ici.
        if day > today or (today - day).days > lookback or int(hms[:2]) >= 7:
            continue
        if day not in matches or hms > matches[day][0]:
            matches[day] = (hms, filename)
    return sorted(((day, fn) for day, (_, fn) in matches.items()), reverse=True)

def local_text(node: ET.Element, tag: str) -> str:
    for el in node.iter():
        if el.tag.rsplit('}', 1)[-1].upper() == tag:
            text = ''.join(el.itertext()).strip()
            if text:
                return re.sub(r'\s+', ' ', text)
    return ''

def decode_document(xml_bytes: bytes, archive_date: dt.date) -> dict | None:
    root = ET.fromstring(xml_bytes)
    full = local_text(root, 'TITREFULL') or local_text(root, 'TITRE')
    if not full:
        return None
    full = full[:800]
    domains = domains_for_title(full)
    if not domains:
        return None
    text_id = local_text(root, 'ID')
    if not ID_RE.fullmatch(text_id):
        found = ID_RE.search(xml_bytes.decode('utf-8', 'replace')[:50000])
        text_id = found.group() if found else ''
    if not ID_RE.fullmatch(text_id):
        return None  # Ne pas inventer de lien juridique.
    date_text = local_text(root, 'DATE_PUBLI') or local_text(root, 'DATE_PARUTION')
    try:
        day = dt.datetime.strptime(date_text[:8], '%Y%m%d').date().isoformat() if re.fullmatch(r'\d{8}', date_text[:8]) else archive_date.isoformat()
    except ValueError:
        day = archive_date.isoformat()
    return {
        'id': text_id,
        'title': full,
        'date': day,
        'nature': local_text(root, 'NATURE')[:60],
        'nor': local_text(root, 'NOR')[:45],
        'domains': domains,
        'url': 'https://www.legifrance.gouv.fr/jorf/id/' + text_id,
        'source': 'DILA — JORFSIMPLE',
        'archive_date': archive_date.isoformat(),
    }

def parse_archive(archive_bytes: bytes, day: dt.date) -> list[dict]:
    result: dict[str, dict] = {}
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode='r:gz') as tf:
        for count, member in enumerate(tf):
            if count > MAX_MEMBERS:
                raise ValueError('Archive inattendue : trop de fichiers')
            if not member.isfile() or not member.name.lower().endswith('.xml') or member.size > MAX_MEMBER_BYTES:
                continue
            file = tf.extractfile(member)
            if file is None:
                continue
            raw = file.read(MAX_MEMBER_BYTES + 1)
            if len(raw) > MAX_MEMBER_BYTES:
                continue
            try:
                item = decode_document(raw, day)
            except (ET.ParseError, UnicodeError, ValueError):
                continue
            if item:
                result[item['id']] = item
    return list(result.values())

def update(output: Path, today: dt.date | None = None, fetch=download) -> dict:
    today = today or dt.datetime.now(dt.timezone.utc).date()
    try:
        existing = json.loads(output.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        existing = {}
    old_items = {x['id']: x for x in existing.get('items', []) if isinstance(x, dict) and isinstance(x.get('id'), str)}
    processed = set(existing.get('processed_archives', []))
    directory = fetch(ROOT, max_bytes=2_000_000).decode('utf-8', 'replace')
    recent = available_archives(directory, today)
    if not recent:
        raise RuntimeError('Aucune archive JORFSIMPLE nocturne détectée sur la période : ancienne base conservée')
    processed_new = []
    errors = []
    for day, filename in reversed(recent):
        if filename in processed:
            continue
        try:
            payload = fetch(urllib.parse.urljoin(ROOT, filename))
            for item in parse_archive(payload, day):
                old_items[item['id']] = item
            processed_new.append(filename)
        except (OSError, ValueError, RuntimeError, tarfile.TarError) as error:
            errors.append(f'{filename}: {error}')
            logging.warning('Échec traitement %s: %s', filename, error)
    # Ne jamais annoncer une synchronisation réussie si aucune archive n'a été traitée.
    if not processed_new and not processed:
        raise RuntimeError('Aucune archive exploitable : ' + '; '.join(errors[:3]))
    cutoff = (today - dt.timedelta(days=RETENTION_DAYS)).isoformat()
    stored = sorted((x for x in old_items.values() if x.get('archive_date', x.get('date', '')) >= cutoff), key=lambda x: (x.get('date', ''), x.get('id', '')), reverse=True)[:450]
    current_processed = sorted((processed | set(processed_new)))
    current_processed = [name for name in current_processed if name[11:19] >= (today - dt.timedelta(days=RETENTION_DAYS)).strftime('%Y%m%d')]
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    data = {
        'schema': 1,
        'status': 'ok' if not errors else 'partial',
        'source_name': 'Journal officiel — DILA JORFSIMPLE',
        'source_url': ROOT,
        'generated_at': now,
        'last_success': now if processed_new else existing.get('last_success'),
        'latest_archive_date': max((x[0].isoformat() for x in recent), default=None),
        'processed_archives': current_processed,
        'items': stored,
        'warnings': errors[:10],
        'caveat': "Index des publications sélectionnées selon le titre. Non exhaustif : ne modifie ni n'atteste la version consolidée des fiches.",
    }
    tmp = output.with_suffix(output.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(output)
    return data

def main():
    p = argparse.ArgumentParser(description='Alimente la veille réglementaire TerriNormes depuis JORFSIMPLE')
    p.add_argument('--output', default='veille.json')
    ns = p.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    try:
        result = update(Path(ns.output))
        print(f"Statut {result['status']}; {len(result['items'])} publications conservées; source datée du {result['latest_archive_date']}")
    except Exception as e:
        logging.error('%s — veille.json non modifié ; alerte GitHub Actions', e)
        raise SystemExit(1)

if __name__ == '__main__':
    main()
