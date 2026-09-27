import json
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from db.product_database import ProductDatabase


class ProductDatabaseTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'products.json'

    def test_missing_database_is_created_on_first_save(self):
        db = ProductDatabase(self.path)
        self.assertEqual(db.seen_products, {})
        db.add_product({'id': 123, 'title': 'CPU'})
        loaded = ProductDatabase(self.path)
        self.assertTrue(loaded.is_product_seen('123'))
        self.assertEqual(loaded.seen_products['123']['data']['title'], 'CPU')
        self.assertEqual(list(self.path.parent.glob('*.tmp')), [])

    def test_successful_save_preserves_permissions(self):
        self.path.write_text('{}')
        self.path.chmod(0o640)
        db = ProductDatabase(self.path)
        db.add_product({'id': 123})
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o640)
        self.assertTrue(ProductDatabase(self.path).is_product_seen('123'))

    def test_partial_serialization_leaves_previous_file_untouched(self):
        original = '{"123": {"data": {"id": 123}}}'
        self.path.write_text(original)
        db = ProductDatabase(self.path)

        def partial_dump(data, file, **kwargs):
            file.write('{"456":')
            raise OSError('disk full')

        with patch('db.product_database.json.dump', side_effect=partial_dump):
            with self.assertLogs('db.product_database', level='ERROR'):
                db.save_database()
        self.assertEqual(self.path.read_text(), original)
        self.assertEqual(list(self.path.parent.glob('*.tmp')), [])

    def test_failed_replace_leaves_previous_file_untouched(self):
        self.path.write_text('{}')
        db = ProductDatabase(self.path)
        with patch('db.product_database.os.replace', side_effect=OSError('replace failed')):
            with self.assertLogs('db.product_database', level='ERROR'):
                db.add_product({'id': 123})
        self.assertEqual(json.loads(self.path.read_text()), {})
        self.assertEqual(list(self.path.parent.glob('*.tmp')), [])

    def test_failed_flush_leaves_previous_file_untouched(self):
        self.path.write_text('{}')
        db = ProductDatabase(self.path)
        with patch('db.product_database.os.fsync', side_effect=OSError('flush failed')):
            with self.assertLogs('db.product_database', level='ERROR'):
                db.add_product({'id': 123})
        self.assertEqual(json.loads(self.path.read_text()), {})
        self.assertEqual(list(self.path.parent.glob('*.tmp')), [])

    def test_force_kill_during_write_preserves_database(self):
        original = '{"123": {"data": {"id": 123}}}'
        self.path.write_text(original)
        script = '''
import os
import signal
import sys
from unittest.mock import patch
from db.product_database import ProductDatabase

def interrupted_dump(data, file, **kwargs):
    file.write('{"456":')
    file.flush()
    os.kill(os.getpid(), signal.SIGKILL)

db = ProductDatabase(sys.argv[1])
with patch('db.product_database.json.dump', side_effect=interrupted_dump):
    db.add_product({'id': 456})
'''
        result = subprocess.run(
            [sys.executable, '-c', script, str(self.path)],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True, timeout=10,
        )
        self.assertEqual(result.returncode, -signal.SIGKILL, result.stderr)
        self.assertEqual(self.path.read_text(), original)
        # A killed process can leave a temp file; startup must ignore it.
        self.assertEqual(len(list(self.path.parent.glob('*.tmp'))), 1)
        loaded = ProductDatabase(self.path)
        self.assertTrue(loaded.is_product_seen('123'))
        self.assertFalse(loaded.is_product_seen('456'))
        loaded.add_product({'id': 789})
        self.assertTrue(ProductDatabase(self.path).is_product_seen('789'))


if __name__ == '__main__':
    unittest.main()
