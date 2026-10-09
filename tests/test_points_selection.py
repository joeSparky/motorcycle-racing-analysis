import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import points_selection as selection

class PointsSelectionTests(unittest.TestCase):
    def test_remember_preserves_settings_and_only_matches_track(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); settings=root/'last-race.json'; track=root/'track.json'; points=root/'points.json'
            settings.write_text(json.dumps(dict(track=str(track),points='',data_root='racingData',race='race.csv')))
            with patch.object(selection,'SETTINGS',settings):
                selection.remember_points(track,points)
                self.assertEqual(selection.selected_points(track),str(points.resolve()))
                self.assertIsNone(selection.selected_points(root/'other.json'))
                selection.remember_points(root/'other.json',root/'wrong.json')
            saved=json.loads(settings.read_text())
            self.assertEqual(saved['data_root'],'racingData')
            self.assertEqual(saved['race'],'race.csv')
            self.assertEqual(saved['points'],str(points.resolve()))
    def test_no_settings_means_no_default(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(selection,'SETTINGS',Path(tmp)/'missing.json'):
            self.assertIsNone(selection.selected_points('track.json'))
