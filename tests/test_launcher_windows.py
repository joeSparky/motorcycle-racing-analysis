"""Verify independent child lifetimes without a graphical display."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import launcher


class LauncherWindowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.base=Path(self.temp.name)
        self.base_patch=patch.object(launcher,'BASE',self.base); self.base_patch.start()
        self.app=launcher.Launcher.__new__(launcher.Launcher)
        a=self.app; a.video_socket='test-pipe'; a.sync_state=self.base/'link.json'; a.root=Mock(); a.child=None; a.log=None; a.csv_children={}; a.status=Mock()
        a.buttons=[Mock(),Mock()]; a.csv_buttons={'statisticsScreen.py':Mock(),'sessionInfo.py':Mock()}; a.file_controls=[Mock()]
        race=self.base/'race.csv'; video=self.base/'video.mp4'; mpv=self.base/'mpv.exe'
        for path in (race,video,mpv): path.touch()
        race.with_suffix('.calibration').write_text(json.dumps(dict(slope=1,offset=0)))
        (self.base/'setup-settings.json').write_text(json.dumps(dict(mpv=str(mpv))))
        a.race=Mock(); a.race.get.return_value=str(race)
        a.video=Mock(); a.video.get.return_value=str(video)
        a.track=Mock(); a.track.get.return_value=''
        a.points=Mock(); a.points.get.return_value=''
        a.data_root=Mock();a.data_root.get.return_value=str(self.base)
        a.track_directory=Mock();a.track_directory.get.return_value=''

    def tearDown(self):
        if self.app.log: self.app.log.close()
        for process,log,path in self.app.csv_children.values(): log.close()
        self.base_patch.stop(); self.temp.cleanup()

    def process(self):
        p=Mock(); p.poll.return_value=None; return p

    def test_statistics_then_video_and_independent_close(self):
        stats,video=self.process(),self.process()
        with patch.object(launcher.subprocess,'Popen',side_effect=[stats,video]) as spawn:
            self.app.open_statistics(); self.app.launch('dashboard.py')
        self.assertEqual(spawn.call_count,2)
        self.assertIs(self.app.child,video)
        self.assertIs(self.app.csv_children['statisticsScreen.py'][0],stats)
        stats.poll.return_value=0; self.app.poll_csv('statisticsScreen.py')
        self.assertIs(self.app.child,video); self.assertTrue(self.app.running())
        self.app.csv_buttons['statisticsScreen.py'].state.assert_called_with(['!disabled'])
        self.app.file_controls[0].state.assert_called_with(['disabled'])
        video.poll.return_value=0; self.app.poll()
        self.assertFalse(self.app.running()); self.app.file_controls[0].state.assert_called_with(['!disabled'])

    def test_video_then_statistics_and_video_closes_first(self):
        video,stats=self.process(),self.process()
        with patch.object(launcher.subprocess,'Popen',side_effect=[video,stats]):
            self.app.launch('dashboard.py'); self.app.open_statistics()
        video.poll.return_value=0; self.app.poll()
        self.assertIsNone(self.app.child); self.assertTrue(self.app.running())
        self.app.buttons[0].state.assert_called_with(['!disabled'])
        self.assertIs(self.app.csv_children['statisticsScreen.py'][0],stats)

    def test_duplicate_and_video_exclusivity(self):
        stats,video=self.process(),self.process()
        with patch.object(launcher.subprocess,'Popen',side_effect=[stats,video]) as spawn:
            self.app.open_statistics(); self.app.open_statistics()
            self.app.launch('dashboard.py'); self.app.launch('videoCalibration.py')
        self.assertEqual(spawn.call_count,2)

    def test_separate_csv_logs_and_close_guard(self):
        with patch.object(launcher.subprocess,'Popen',side_effect=[self.process(),self.process()]):
            self.app.open_statistics(); self.app.open_csv_screen('sessionInfo.py')
        first=self.app.csv_children['statisticsScreen.py'][1]
        second=self.app.csv_children['sessionInfo.py'][1]
        self.assertNotEqual(first.name,second.name)
        with patch.object(launcher.messagebox,'showinfo') as notice: self.app.close()
        notice.assert_called_once(); self.app.root.destroy.assert_not_called()


if __name__=='__main__': unittest.main()
