from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from console import galaxy_bridge as galaxy


class GalaxyBridgeTests(unittest.TestCase):
    def test_uses_local_reader_and_invalid_command_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(galaxy, 'query_local', return_value=b'[]') as local:
                self.assertEqual(galaxy.read(root, 'search', ['Context Gate']), b'[]')
                local.assert_called_once_with(root, 'search', ['Context Gate'])
                with self.assertRaises(ValueError):
                    galaxy.read(root, 'unknown', [])
                self.assertEqual(local.call_count, 1)

    def test_missing_optional_component_reports_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict('os.environ', {'MEMORY_OS_GALAXY_DIR': ''}):
                with self.assertRaisesRegex(ValueError, 'MemoryOS'):
                    galaxy.resources(Path(tmp))


if __name__ == '__main__':
    unittest.main()
