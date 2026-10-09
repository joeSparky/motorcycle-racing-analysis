import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from interesting_points import InterestingPoints, identity


class InterestingPointTests(unittest.TestCase):
    def setUp(self):
        self.geometry=dict(config=dict(format='track-editor-master-v1',track='Test',divisions=10000,
            origin=dict(latitude=40,longitude=-88),nodes=[dict(position=0,reference=[0,0]),dict(position=10000,reference=[100,0])]),
            origin=np.array([-88,40]),scale=np.array([85000,111000]),starts=np.array([[0,0]]),
            vectors=np.array([[100,0]]),lengths=np.array([100]),positions=np.array([0]),spans=np.array([10000]),threshold=20)

    def test_add_move_save_load_cancel_delete(self):
        model=InterestingPoints(self.geometry)
        marker=model.add([50,10]); self.assertTrue(model.dirty)
        self.assertAlmostEqual(marker['track_position'],5000,places=6)
        self.assertAlmostEqual(marker['latitude_deg'],40+10/111000)
        marker.update(label='Turn 1 apex',notes='Keep this note')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'points.json'; model.save(path); self.assertFalse(model.dirty)
            data=json.loads(path.read_text()); self.assertEqual(data['track_identity'],identity(self.geometry))
            other=InterestingPoints(self.geometry); other.load(path)
            self.assertEqual(other.markers,model.markers)
            other.move(other.markers[0],[90,20]); self.assertTrue(other.dirty)
            other.cancel(); self.assertEqual(other.markers,model.markers)
            other.markers.clear(); other.save(path)
            model.load(path); self.assertEqual(model.markers,[])

    def test_invalid_file_leaves_current_points(self):
        model=InterestingPoints(self.geometry); original=model.add([10,20]).copy()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'points.json'; model.save(path)
            data=json.loads(path.read_text())
            data['track_identity']['track']='Other'; path.write_text(json.dumps(data))
            with self.assertRaises(ValueError): model.load(path)
            self.assertEqual(model.markers,[original])
            data['track_identity']=identity(self.geometry); data['markers'][0]['x_m']='bad'
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError): model.load(path)
            self.assertEqual(model.markers,[original])

class PausedEditingTests(unittest.TestCase):
    def test_editing_requires_enabled_mode_and_confirmed_pause(self):
        from trackView import TrackView
        from unittest.mock import Mock
        view=TrackView.__new__(TrackView)
        view.edit_points=Mock(); view.status=Mock()
        for enabled,paused,expected in [(False,True,False),(True,False,False),(True,None,False),(True,True,True)]:
            view.edit_points.get.return_value=enabled
            view.is_paused=lambda:paused
            self.assertEqual(view.can_edit(),expected)
        view.is_paused=Mock(side_effect=ConnectionError)
        self.assertFalse(view.can_edit())

class LandmarkTests(InterestingPointTests):
    def test_landmark_round_trip(self):
        model=InterestingPoints(self.geometry)
        point=model.add([300,150]);point.update(type='marker',label='Tree',notes='Aim left of tree')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'points.json';model.save(path)
            loaded=InterestingPoints(self.geometry);loaded.load(path)
            self.assertEqual(loaded.markers[0]['type'],'marker')
            self.assertEqual(loaded.markers[0]['label'],'Tree')
            self.assertEqual(loaded.markers[0]['x_m'],300)

    def test_section_editor_point_click_does_not_split(self):
        from sectionEditor import App
        from unittest.mock import Mock
        editor=App.__new__(App);editor.ax=object()
        editor.point_at_pixel=Mock(return_value=True)
        editor.boundary_at_pixel=Mock()
        event=Mock(inaxes=editor.ax,xdata=50)
        editor.press(event)
        editor.boundary_at_pixel.assert_not_called()
