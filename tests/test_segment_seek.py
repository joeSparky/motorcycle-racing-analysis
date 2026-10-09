import unittest
from unittest.mock import Mock
from dashboard import Dashboard

class SegmentSeekTests(unittest.TestCase):
    def test_segment_pauses_before_seek_and_stays_paused(self):
        app=Dashboard.__new__(Dashboard)
        app.slope=2;app.offset=3;app.sync_adjustment=.5
        app.mpv=Mock();app.mpv.get_property.return_value=1000;app.mpv.command.return_value=True
        self.assertTrue(app.seek_lap_start(dict(start=10,end=20,pause_on_arrival=True)))
        self.assertEqual([call.args for call in app.mpv.command.call_args_list],
                         [('set_property','pause',True),('seek',23.5,'absolute+exact')])

    def test_normal_lap_still_plays(self):
        app=Dashboard.__new__(Dashboard)
        app.slope=1;app.offset=0;app.sync_adjustment=0
        app.mpv=Mock();app.mpv.get_property.return_value=1000;app.mpv.command.return_value=True
        self.assertTrue(app.seek_lap_start(dict(start=10,end=20)))
        self.assertEqual(app.mpv.command.call_args.args,('set_property','pause',False))
