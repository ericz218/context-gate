import re
import unittest
from console.app import PAGE

class StyleBoundaries(unittest.TestCase):
    def test_quota_styles_remain_top_level_after_router_styles(self):
        css = PAGE.split('<style>', 1)[1].split('</style>', 1)[0]
        prefix = css.split('.quota-grid{', 1)[0]
        prefix = re.sub(r'/\*.*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', '', prefix, flags=re.S)
        self.assertEqual(prefix.count('{'), prefix.count('}'), 'Previous page CSS swallowed quota layout')

if __name__ == '__main__':
    unittest.main()
