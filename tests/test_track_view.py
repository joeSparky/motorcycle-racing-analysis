import unittest
import numpy as np
from trackView import recorded_position

class TrackViewTests(unittest.TestCase):
    def test_actual_position_in_local_track_coordinates(self):
        g={'origin':np.array([-88,40]),'scale':np.array([85000,111000])}
        x,y=recorded_position({'GPS Latitude':'40.001','GPS Longitude':'-87.999'},g)
        self.assertAlmostEqual(x,85); self.assertAlmostEqual(y,111)

    def test_unavailable_invalid_gps(self):
        g={'origin':np.array([-88,40]),'scale':np.array([85000,111000])}
        for row in [{},{'GPS Latitude':'nan','GPS Longitude':'-88'},{'GPS Latitude':'91','GPS Longitude':'0'},{'GPS Latitude':'0','GPS Longitude':'0'}]:
            self.assertIsNone(recorded_position(row,g))

if __name__=='__main__': unittest.main()
