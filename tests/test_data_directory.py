"""Data folder workflow without opening Tk windows."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import launcher

class Value:
    def __init__(self,value=''): self.value=value
    def get(self): return self.value
    def set(self,value): self.value=value

class DataDirectoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.base=Path(self.temp.name)
        self.app=launcher.Launcher.__new__(launcher.Launcher)
        self.app.root=Mock(); self.app.status=Mock(); self.app.running=Mock(return_value=False)
        self.app.data_root=Value(str(self.base/'racingData')); self.app.track_directory=Value()
        for field in ('race','video','track','points'): setattr(self.app,field,Value('old-file'))
    def tearDown(self): self.temp.cleanup()
    def test_new_track_creates_root_clears_files_and_remembers_directory(self):
        with patch.object(launcher.simpledialog,'askstring',return_value='Barber'), patch.object(launcher,'BASE',self.base):
            self.app.create_track_directory()
        folder=self.base/'racingData'/'Barber'
        self.assertTrue(folder.is_dir())
        self.assertEqual(self.app.initial_directory(),str(folder))
        saved=json.loads((self.base/'last-race.json').read_text())
        self.assertEqual(saved['track_directory'],str(folder))
        self.assertEqual(saved['data_root'],str(folder.parent))
        for field in ('race','video','track','points'): self.assertEqual(saved[field],'')
    def test_invalid_name_cannot_escape_data_root(self):
        with patch.object(launcher.simpledialog,'askstring',return_value='../elsewhere'), patch.object(launcher.messagebox,'showerror') as error:
            self.app.create_track_directory()
        error.assert_called_once()
        self.assertFalse((self.base/'elsewhere').exists())
    def test_file_picker_defaults_to_selected_track(self):
        self.app.track_directory.set(str(self.base))
        self.app.save=Mock()
        with patch.object(launcher.filedialog,'askopenfilename',return_value='new.csv') as picker:
            self.app.choose(self.app.race)
        self.assertEqual(picker.call_args.kwargs['initialdir'],str(self.base))
        self.assertEqual(self.app.race.get(),'new.csv')
