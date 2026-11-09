import datetime as dt
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from maj_veille import available_archives, decode_document, domains_for_title, parse_archive, update

DOC = b'''<?xml version="1.0" encoding="utf-8"?>
<TEXTE><META><META_COMMUN><ID>JORFTEXT000050012345</ID><NATURE>DECRET</NATURE></META_COMMUN>
<META_SPEC><TITREFULL>Decret relatif aux agents de la fonction publique territoriale</TITREFULL>
<DATE_PUBLI>20261104</DATE_PUBLI><NOR>EXAM260001D</NOR></META_SPEC></META></TEXTE>'''
OTHER = b'''<TEXTE><META><META_COMMUN><ID>JORFTEXT000050012346</ID></META_COMMUN>
<TITREFULL>Arrete relatif aux poissons marins</TITREFULL></META></TEXTE>'''

def make_tar():
    memory = io.BytesIO()
    with tarfile.open(fileobj=memory,mode='w:gz') as t:
        for name,doc in [('texte1.xml',DOC),('texte2.xml',OTHER)]:
            info=tarfile.TarInfo(name)
            info.size=len(doc)
            t.addfile(info,io.BytesIO(doc))
    return memory.getvalue()

class TestVeille(unittest.TestCase):
    def test_filtres(self):
        self.assertIn('Statut & carrière',domains_for_title('statut des agents de la fonction publique territoriale'))
        self.assertFalse(domains_for_title('Arrete relatif aux poissons marins'))
    def test_select_daily(self):
        html='''<a href="JORFSIMPLE_20261104-002300.tar.gz">a</a><a href="JORFSIMPLE_20261104-212000.tar.gz">b</a><a href="JORFSIMPLE_20261103-001000.tar.gz">c</a>'''
        self.assertEqual(len(available_archives(html,dt.date(2026,11,4))),2)
        self.assertIn('212000',available_archives(html,dt.date(2026,11,4))[0][1])
    def test_decode(self):
        item=decode_document(DOC,dt.date(2026,11,4))
        self.assertEqual(item['id'],'JORFTEXT000050012345')
        self.assertEqual(item['date'],'2026-11-04')
        self.assertIn('Statut & carrière',item['domains'])
        self.assertIsNone(decode_document(OTHER,dt.date(2026,11,4)))
    def test_archive(self):
        self.assertEqual(len(parse_archive(make_tar(),dt.date(2026,11,4))),1)
    def test_pipeline_and_idempotence(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td)/'veille.json'
            archive=make_tar()
            calls=[]
            def fetch(url, max_bytes=None):
                calls.append(url)
                if url.endswith('JORFSIMPLE/'):
                    return b'<a href="JORFSIMPLE_20261104-002300.tar.gz">download</a>'
                return archive
            v=update(target,today=dt.date(2026,11,4),fetch=fetch)
            self.assertEqual(v['status'],'ok')
            self.assertEqual(len(v['items']),1)
            self.assertEqual(v['latest_archive_date'],'2026-11-04')
            self.assertEqual(json.loads(target.read_text())['items'][0]['id'],'JORFTEXT000050012345')
            v2=update(target,today=dt.date(2026,11,4),fetch=fetch)
            self.assertEqual(len(v2['items']),1)
            self.assertEqual(len(calls),3) # 2 index fetches + 1 archive
    def test_failure_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td)/'veille.json'
            target.write_text('CONSERVER')
            def fail(url,**kw): raise OSError('Hors ligne')
            with self.assertRaises(OSError):
                update(target,today=dt.date(2026,11,4),fetch=fail)
            self.assertEqual(target.read_text(),'CONSERVER')

if __name__=='__main__':unittest.main()
