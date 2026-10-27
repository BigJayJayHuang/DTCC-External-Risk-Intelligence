from pathlib import Path
import gzip,hashlib,json,sqlite3,sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from query_store import query

class QueryStoreTests(unittest.TestCase):
    def test_compressed_snapshot_restores_and_query_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);p=folder/'synthetic_scenarios.sqlite3';c=sqlite3.connect(p)
            c.execute('CREATE TABLE toy(value REAL)');c.execute('INSERT INTO toy VALUES(7)');c.commit();c.close()
            body=p.read_bytes();packed=gzip.compress(body);(folder/'synthetic_scenarios.sqlite3.gz').write_bytes(packed)
            (folder/'snapshot_manifest.json').write_text(json.dumps({'database_sha256':hashlib.sha256(body).hexdigest(),'compressed_sha256':hashlib.sha256(packed).hexdigest()}));p.unlink()
            self.assertEqual(query('SELECT value FROM toy',folder),[{'value':7.0}])
            with self.assertRaises(sqlite3.OperationalError):query('DELETE FROM toy',folder)
    def test_bad_snapshot_checksum_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);(folder/'synthetic_scenarios.sqlite3.gz').write_bytes(b'bad')
            (folder/'snapshot_manifest.json').write_text(json.dumps({'compressed_sha256':'wrong','database_sha256':'wrong'}))
            with self.assertRaisesRegex(ValueError,'checksum'):query('SELECT 1',folder)
