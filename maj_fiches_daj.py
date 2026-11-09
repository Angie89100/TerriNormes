#!/usr/bin/env python3
"""Synchronisation des index officiels des fiches techniques DAJ (sans recopier les PDF).

Met à jour un catalogue documentaire autonome `daj_fiches.json`. Le logiciel ouvre
les PDF directement sur economie.gouv.fr. Les modifications détectables comprennent
les ajouts, suppressions, déplacements d'URL et changements d'ETag/Last-Modified
lorsque l'administration les expose. Aucun contenu juridique n'est consolidé ici.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import hashlib
import html
from html.parser import HTMLParser
import json
import logging
from pathlib import Path
import re
import unicodedata
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

BASE = 'https://www.economie.gouv.fr/daj/commande-publique/conseils-aux-acheteurs/fiches-techniques'
SECTIONS = [
    ('Champ d’application', 'le-champ-dapplication'),
    ('Préparation', 'la-preparation'),
    ('Passation', 'les-modalites-de-passation'),
    ('Exécution', 'lexecution'),
    ('Transparence', 'la-transparence'),
    ('Recours', 'les-recours'),
    ('Dispositifs exceptionnels', 'les-dispositifs-exceptionnels'),
]
USER_AGENT = 'TerriNormes/3.0 (index public DAJ, contact depuis GitHub Pages)'
DATE_FORMAT = '%Y-%m-%dT%H:%M:%S%z'
PDF_PATH = re.compile(r'\.pdf(?:$|[?#])', re.I)


def safe_url(url: str, base: str) -> str:
    full = urljoin(base, html.unescape(url.strip()))
    parsed = urlparse(full)
    if parsed.scheme != 'https' or parsed.hostname not in ('economie.gouv.fr', 'www.economie.gouv.fr'):
        return ''
    return full


def collapse(value: str) -> str:
    return re.sub(r'\s+', ' ', html.unescape(value or '')).strip()


def make_id(section: str, title: str) -> str:
    value = unicodedata.normalize('NFKD', section + '|' + title.casefold())
    value = ''.join(c for c in value if not unicodedata.combining(c))
    return 'daj-' + hashlib.sha256(value.encode('utf8')).hexdigest()[:16]


class DajIndexParser(HTMLParser):
    """Lit les H2/H3 et le premier lien PDF suivant chaque H3.

    Structure attendue: H2 sous-rubrique, H3 titre de fiche, puis un lien PDF.
    Le HTML réel peut contenir plusieurs conteneurs entre le titre et le lien.
    """
    def __init__(self, section: str, page_url: str):
        super().__init__(convert_charrefs=True)
        self.section, self.page_url = section, page_url
        self.heading_level = None
        self.heading_parts = []
        self.subcategory = ''
        self.current = None
        self.items: list[dict] = []
        self.ignore_depth = 0
        self.capture_headings = False

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript'):
            self.ignore_depth += 1
            return
        if self.ignore_depth:
            return
        if tag in ('h2', 'h3'):
            self._finish_heading()
            self._finish_item()
            self.heading_level = tag
            self.heading_parts = []
        elif tag == 'a' and self.current and not self.current.get('url'):
            href = dict(attrs).get('href', '')
            pdf_url = safe_url(href, self.page_url)
            if pdf_url and PDF_PATH.search(pdf_url):
                self.current['url'] = pdf_url
        elif tag == 'meta':
            pass

    def handle_data(self, data):
        if self.heading_level and not self.ignore_depth:
            self.heading_parts.append(data)

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript') and self.ignore_depth:
            self.ignore_depth -= 1
            return
        if tag == self.heading_level:
            self._finish_heading()

    def _finish_heading(self):
        if not self.heading_level:
            return
        title = collapse(''.join(self.heading_parts))
        if self.heading_level == 'h2':
            self.subcategory = title
        elif self.heading_level == 'h3' and 4 < len(title) < 220:
            self.current = {
                'id': make_id(self.section, title),
                'title': title,
                'section': self.section,
                'subcategory': self.subcategory,
                'page_url': self.page_url,
                'url': '',
                'publisher': 'Direction des affaires juridiques — ministère de l’Économie',
            }
        self.heading_level, self.heading_parts = None, []

    def _finish_item(self):
        if self.current and self.current['url']:
            self.items.append(self.current)
        self.current = None

    def finish(self):
        self._finish_heading()
        self._finish_item()
        unique = {x['id']: x for x in self.items}
        return list(unique.values())


def parse_index(data: bytes, section: str, page_url: str) -> list[dict]:
    parser = DajIndexParser(section, page_url)
    parser.feed(data.decode('utf-8', 'replace'))
    return parser.finish()


def fetch_page(url: str, *, timeout: int = 23) -> bytes:
    request = Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'text/html'})
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f'Réponse HTTP {response.status}')
        content_type = response.headers.get('Content-Type', '')
        if content_type and 'html' not in content_type:
            raise ValueError(f'Type inattendu : {content_type}')
        content = response.read(2_000_001)
        if len(content) > 2_000_000:
            raise ValueError('Page trop volumineuse')
        return content


def fetch_doc_headers(url: str) -> dict:
    """Métadonnées sans télécharger le PDF ; serveur parfois sans ETag/date.

    On ne déduit jamais de modification de l'absence de ces métadonnées.
    """
    req = Request(url, method='HEAD', headers={'User-Agent': USER_AGENT})
    with urlopen(req, timeout=12) as response:
        if response.status != 200:
            raise RuntimeError(f'HTTP {response.status}')
        final = safe_url(response.geturl(), url)
        if not final:
            raise ValueError('Redirection hors domaine officiel')
        return {
            'etag': response.headers.get('ETag', '')[:250],
            'last_modified': response.headers.get('Last-Modified', '')[:160],
            'content_length': response.headers.get('Content-Length', '')[:35],
        }


def update(output: Path, *, fetch=fetch_page, head=None) -> dict:
    """`head` est facultatif car les en-têtes ne sont pas toujours accessibles.

    Échec d'une rubrique -> conservation de cette rubrique et alerte.
    Aucune rubrique reçue -> le fichier reste intact et la tâche échoue.
    """
    try:
        previous = json.loads(output.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        previous = {}
    old_items = {r['id']: r for r in previous.get('items', []) if isinstance(r, dict) and isinstance(r.get('id'), str)}
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    sections_result = []
    warnings = []
    changes = []
    updated_items = dict(old_items)
    successful = 0
    for section, slug in SECTIONS:
        url = BASE + '/' + slug
        try:
            fresh = parse_index(fetch(url), section, url)
            if not fresh:
                raise ValueError('Aucune fiche PDF détectée : site modifié ou blocage réseau')
            successful += 1
            known_in_section = {k: v for k, v in old_items.items() if v.get('section') == section}
            header_map = {}
            if head:
                # Requêtes bornées en parallèle pour ne pas ralentir excessivement
                # le workflow lorsque la DAJ répond lentement à HEAD.
                def get_headers(record):
                    try:
                        return head(record['url'])
                    except Exception:
                        return {}
                with ThreadPoolExecutor(max_workers=6) as executor:
                    values = list(executor.map(get_headers, fresh))
                header_map = {record['id']: result for record, result in zip(fresh, values)}
            fresh_ids = {x['id'] for x in fresh}
            for rec in fresh:
                old = old_items.get(rec['id'])
                # Garder un suivi des versions pour lesquelles la source fournit un signal.
                headers = header_map.get(rec['id'], {})
                rec['etag'] = headers.get('etag', old.get('etag', '') if old and old.get('url') == rec['url'] else '')
                rec['last_modified'] = headers.get('last_modified', old.get('last_modified', '') if old and old.get('url') == rec['url'] else '')
                rec['content_length'] = headers.get('content_length', old.get('content_length', '') if old and old.get('url') == rec['url'] else '')
                rec['first_seen'] = old.get('first_seen', now) if old else now
                rec['last_seen'] = now
                rec['removed'] = False
                rec['catalogue_initial'] = False
                if not old or old.get('removed'):
                    changes.append({'kind': 'indexed' if previous.get('status') == 'initialisation_requise' else 'new', 'id': rec['id'], 'title': rec['title'], 'section': section, 'detected_at': now})
                elif (old.get('url') and old.get('url') != rec['url']) or (headers.get('etag') and old.get('etag') and headers['etag'] != old['etag']) or (headers.get('last_modified') and old.get('last_modified') and headers['last_modified'] != old['last_modified']):
                    changes.append({'kind': 'updated', 'id': rec['id'], 'title': rec['title'], 'section': section, 'detected_at': now})
                updated_items[rec['id']] = rec
            for old_id in set(known_in_section) - fresh_ids:
                if not known_in_section[old_id].get('removed') and not known_in_section[old_id].get('catalogue_initial'):
                    changes.append({'kind': 'removed', 'id': old_id, 'title': known_in_section[old_id].get('title', ''), 'section': section, 'detected_at': now})
                updated_items[old_id] = {**known_in_section[old_id], 'removed': True}
            sections_result.append({'name': section, 'url': url, 'status': 'ok', 'count': len(fresh), 'checked_at': now})
        except Exception as ex:
            warnings.append(f'{section} : {str(ex)[:220]}')
            sections_result.append({'name': section, 'url': url, 'status': 'error', 'count': sum(v.get('section') == section and not v.get('removed') for v in old_items.values()), 'checked_at': None})
            logging.warning('Impossible de synchroniser %s : %s', section, ex)
    if not successful:
        raise RuntimeError('Synchronisation DAJ impossible ; conservation du catalogue précédent : ' + '; '.join(warnings[:2]))
    # On garde un historique court de modifications et 90 jours de documents supprimés.
    old_changes = [x for x in previous.get('changes', []) if isinstance(x, dict)]
    all_changes = (changes + old_changes)[:150]
    new_data = {
        'schema': 1,
        'source': 'Direction des affaires juridiques (DAJ) — economie.gouv.fr',
        'source_url': BASE,
        'status': 'ok' if successful == len(SECTIONS) else 'partial',
        'generated_at': now,
        'last_success': now if successful == len(SECTIONS) else previous.get('last_success'),
        'last_checked': now,
        'checked_sections': successful,
        'total_sections': len(SECTIONS),
        'sections': sections_result,
        'items': sorted(updated_items.values(), key=lambda x: (x.get('section',''), x.get('title',''))),
        'changes': all_changes,
        'warnings': warnings,
        'caveat': 'Référencement des fiches et liens PDF DAJ ; les contenus et droits applicables ne sont pas automatiquement consolidés. Le contenu d’un PDF modifié sans changement de lien ni en-têtes de version peut ne pas être détecté.',
    }
    temp = output.with_suffix('.json.tmp')
    temp.write_text(json.dumps(new_data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(output)
    return new_data


def main():
    parser = argparse.ArgumentParser(description='Actualiser les fiches techniques DAJ depuis economie.gouv.fr')
    parser.add_argument('--output', default='daj_fiches.json')
    parser.add_argument('--check-headers', action='store_true', help='Tenter des requêtes HEAD sur les PDF pour leurs signaux de version')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    try:
        result = update(Path(args.output), head=fetch_doc_headers if args.check_headers else None)
        print(f"DAJ : {len(result['items'])} fiches indexées, {result['checked_sections']}/{result['total_sections']} rubriques contrôlées, {len(result['changes'])} changements enregistrés")
        if result['status'] == 'partial':
            logging.warning('DAJ synchronisation partielle, voir les alertes de daj_fiches.json')
    except Exception as exc:
        logging.error('DAJ non actualisée : %s', exc)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
