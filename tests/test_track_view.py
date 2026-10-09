import unittest
import numpy as np
from trackView import recorded_position, segment_markers, MapViewport

class TrackViewTests(unittest.TestCase):
    def test_actual_position_in_local_track_coordinates(self):
        g={'origin':np.array([-88,40]),'scale':np.array([85000,111000])}
        x,y=recorded_position({'GPS Latitude':'40.001','GPS Longitude':'-87.999'},g)
        self.assertAlmostEqual(x,85); self.assertAlmostEqual(y,111)

    def test_unavailable_invalid_gps(self):
        g={'origin':np.array([-88,40]),'scale':np.array([85000,111000])}
        for row in [{},{'GPS Latitude':'nan','GPS Longitude':'-88'},{'GPS Latitude':'91','GPS Longitude':'0'},{'GPS Latitude':'0','GPS Longitude':'0'}]:
            self.assertIsNone(recorded_position(row,g))

class SegmentMarkerTests(unittest.TestCase):
    def test_start_order_and_interpolated_boundary(self):
        g={'config':{'divisions':10000,'sections':[{'start':7500},{'start':0},{'start':2500}]},
           'positions':np.array([0,5000]),'spans':np.array([5000,5000]),
           'starts':np.array([[0,0],[100,0]]),'vectors':np.array([[100,0],[-100,0]])}
        markers=segment_markers(g)
        self.assertEqual([(n,p) for n,p,xy in markers],[(1,0),(2,2500),(3,7500)])
        np.testing.assert_allclose(markers[1][2],[50,0]); np.testing.assert_allclose(markers[2][2],[50,0])
        g['config']['sections']=[]; self.assertEqual(segment_markers(g),[])

if __name__=='__main__': unittest.main()


class ViewportTests(unittest.TestCase):
    def test_zoom_preserves_pointer_location_and_equal_scale(self):
        view=MapViewport(); view.fit([[0,0],[100,200]],620,500)
        before=view.world(125,240,620,500)
        original_scale=view.meters_per_pixel
        view.zoom(1.25,125,240,620,500)
        np.testing.assert_allclose(view.world(125,240,620,500),before)
        self.assertAlmostEqual(view.meters_per_pixel,original_scale/1.25)
        np.testing.assert_allclose(view.screen(before,620,500),[125,240])

    def test_pan_and_zoom_limits(self):
        view=MapViewport(); before=view.screen([0,0],620,500)
        view.pan(70,-20)
        np.testing.assert_allclose(np.array(view.screen([0,0],620,500))-before,[70,-20])
        view.zoom(1e20,10,10,620,500); self.assertEqual(view.meters_per_pixel,.01)
        view.zoom(1e-20,10,10,620,500); self.assertEqual(view.meters_per_pixel,1e7)

    def test_fit_includes_distant_actual_position(self):
        view=MapViewport(); points=[[0,0],[100,200],[5000,-4000]]
        view.fit(points,620,500)
        for point in points:
            x,y=view.screen(point,620,500)
            self.assertTrue(25 <= x <= 595)
            self.assertTrue(25 <= y <= 475)
        view.fit([[0,0]],1,1)
        self.assertTrue(np.isfinite(view.meters_per_pixel))
