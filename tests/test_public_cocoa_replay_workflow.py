from pathlib import Path
import unittest


class PublicCocoaWorkflow(unittest.TestCase):
    def test_default_off_main_only_and_owner_phases_are_distinct(self):
        text = (Path(__file__).resolve().parents[1] / '.github/workflows/public-cocoa-contracts.yml').read_text()
        self.assertNotIn('  push:', text)
        self.assertIn('options: [off, collect-owner, replay]', text)
        self.assertIn('default: off', text)
        self.assertIn("github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'", text)
        self.assertIn("(data.get('ownerProofText') is None) != (os.environ['PHASE'] == 'collect-owner')", text)
        self.assertNotIn('id-token:', text)
        for suffix in ('json', 'log', 'png', 'rgba'):
            self.assertIn('public-cocoa-contracts/**/*.' + suffix, text)
