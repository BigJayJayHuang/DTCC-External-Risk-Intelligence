from pathlib import Path
import gzip,hashlib,json,sqlite3,sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from query_store import query,restore

class QueryTests(unittest.TestCase):
    def fixture(self,path):
        db=path/'synthetic_scenarios.sqlite3';c=sqlite3.connect(db)
        c.execute('create table toy(value integer)');c.execute('insert into toy values(7)');c.commit();c.close()
        raw=db.read_bytes();packed=gzip.compress(raw,mtime=0)
        (path/'synthetic_scenarios.sqlite3.gz').write_bytes(packed)
        (path/'snapshot_manifest.json').write_text(json.dumps({'source_type':'synthetic','database_sha256':hashlib.sha256(raw).hexdigest(),'compressed_sha256':hashlib.sha256(packed).hexdigest()}))
        db.unlink()
    def test_restore_and_read_only(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);self.fixture(p)
            self.assertEqual(query('select * from toy',p),[{'value':7}])
            with self.assertRaises(sqlite3.OperationalError):query('delete from toy',p)
    def test_corrupt_archive_and_existing_database_are_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);self.fixture(p)
            (p/'synthetic_scenarios.sqlite3.gz').write_bytes(b'bad')
            with self.assertRaisesRegex(ValueError,'Compressed'):restore(p)
            (p/'synthetic_scenarios.sqlite3').write_bytes(b'bad')
            with self.assertRaisesRegex(ValueError,'Existing'):restore(p)

if __name__=='__main__':unittest.main()
