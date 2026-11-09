import json
from pathlib import Path
import tempfile
import unittest

from maj_fiches_daj import BASE, SECTIONS, make_id, parse_index, safe_url, update


def html_section(title='Les marchés publics à procédure adaptée', doc='https://www.economie.gouv.fr/files/files/daj/ft-mapa.pdf'):
    return f'''<!doctype html><html><head><title>DAJ</title></head><body><main>
    <h2>Les procédures</h2><h3><span>{title}</span></h3>
    <div><ul><li><a href="{doc}">Ouvrir</a></li><li><a href="{doc}">Télécharger (PDF)</a></li></ul></div>
    </main><footer><h3>Suivez-nous</h3><a href="/daj">Contact</a></footer></body></html>'''.encode()


class DajTests(unittest.TestCase):
    def test_parser_extrait_titre_url_et_categorie(self):
        page=BASE+'/les-modalites-de-passation'
        out=parse_index(html_section(), 'Passation', page)
        self.assertEqual(len(out),1)
        self.assertEqual(out[0]['title'],'Les marchés publics à procédure adaptée')
        self.assertEqual(out[0]['subcategory'],'Les procédures')
        self.assertEqual(out[0]['url'],'https://www.economie.gouv.fr/files/files/daj/ft-mapa.pdf')
        self.assertEqual(out[0]['id'], make_id('Passation','Les marchés publics à procédure adaptée'))

    def test_official_url_restriction(self):
        self.assertFalse(safe_url('javascript:alert(1)',BASE))
        self.assertFalse(safe_url('https://www.economie.gouv.fr.evil.example/evil.pdf',BASE))
        self.assertFalse(safe_url('http://www.economie.gouv.fr/ft.pdf',BASE))
        self.assertEqual(safe_url('/documents/fiche.pdf',BASE),'https://www.economie.gouv.fr/documents/fiche.pdf')

    def test_update_add_change_remove_partial_and_error(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'daj_fiches.json'
            def fetch_initial(url):
                return html_section(doc='https://www.economie.gouv.fr/premiere-version.pdf')
            initial=update(path, fetch=fetch_initial)
            self.assertEqual(initial['status'],'ok')
            self.assertEqual(initial['checked_sections'],7)
            self.assertEqual(len(initial['items']),7)
            self.assertEqual(len(initial['changes']),7)
            self.assertEqual(initial['changes'][0]['kind'],'new')
            old_bytes=path.read_bytes()
            def fetch_bad(url):
                raise TimeoutError('Hors connexion')
            with self.assertRaises(RuntimeError):update(path,fetch=fetch_bad)
            self.assertEqual(path.read_bytes(),old_bytes)
            def fetch_partial(url):
                if url.endswith(SECTIONS[0][1]):
                    return html_section(doc='https://www.economie.gouv.fr/fiche-modifiee.pdf')
                raise TimeoutError('Réseau indisponible')
            partial=update(path,fetch=fetch_partial)
            self.assertEqual(partial['status'],'partial')
            self.assertEqual(partial['checked_sections'],1)
            self.assertGreaterEqual(len(partial['warnings']),1)
            self.assertTrue(any(ch['kind']=='updated' for ch in partial['changes']))
            self.assertEqual(partial['last_success'],initial['last_success'])

    def test_head_modification_same_link(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'daj_fiches.json'
            update(path,fetch=lambda url: html_section(),head=lambda url:{'etag':'"v1"'})
            new=update(path,fetch=lambda url: html_section(),head=lambda url:{'etag':'"v2"'})
            self.assertTrue(any(ch['kind']=='updated' for ch in new['changes']))

    def test_initial_seed_is_not_reported_as_new_norm(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'daj_fiches.json'
            path.write_text(json.dumps({'schema':1,'status':'initialisation_requise','items':[], 'changes':[]}),encoding='utf8')
            new=update(path,fetch=lambda url: html_section())
            self.assertTrue(all(c['kind']=='indexed' for c in new['changes']))

if __name__=='__main__':unittest.main()
