import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from video_link import VideoLink

class VideoLinkTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.path=Path(self.temp.name)/'link.json'
        self.path.write_text(json.dumps(dict(slope=2,offset=10,adjustment=.5)))
        self.link=VideoLink('fake',self.path); self.link.mpv=Mock()

    def tearDown(self): self.temp.cleanup()

    def test_both_directions_and_pause_preserved(self):
        self.link.mpv.get_property.return_value=30.5
        self.assertEqual(self.link.current(),10)
        self.link.mpv.get_property.return_value=100
        self.link.mpv.command.return_value=True
        self.assertTrue(self.link.seek(10))
        self.link.mpv.command.assert_called_once_with('seek',30.5,'absolute+exact')

    def test_adjustment_updated_without_reopening(self):
        self.link.mpv.get_property.return_value=30.5
        self.path.write_text(json.dumps(dict(slope=2,offset=10,adjustment=2.5)))
        self.assertEqual(self.link.current(),9)

    def test_invalid_mapping_and_unreachable_time(self):
        self.link.mpv.get_property.return_value=20
        with self.assertRaises(ValueError): self.link.seek(10)
        with self.assertRaises(ValueError): self.link.seek(-10)
        self.link.mpv.command.assert_not_called()
        self.path.write_text(json.dumps(dict(slope=0,offset=0)))
        with self.assertRaises(ValueError): self.link.current()

if __name__=='__main__': unittest.main()
