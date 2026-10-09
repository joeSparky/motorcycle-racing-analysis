import tempfile
from pathlib import Path
import unittest
from PIL import Image
from point_images import image_data_url, decode_picture
from interesting_points import InterestingPoints
from test_interesting_points import InterestingPointTests

class PointImageTests(unittest.TestCase):
    def test_convert_resize_and_portable_round_trip(self):
        fixture=InterestingPointTests();fixture.setUp()
        model=InterestingPoints(fixture.geometry)
        marker=model.add([20,30]);marker['type']='marker'
        with tempfile.TemporaryDirectory() as directory:
            image=Path(directory)/'tree.jpg'
            Image.new('RGB',(2000,1000),'green').save(image)
            value=image_data_url(image)
            self.assertEqual(decode_picture(value).size,(1600,800))
            marker['image_data_url']=value
            points=Path(directory)/'points.json';model.save(points);image.unlink()
            loaded=InterestingPoints(fixture.geometry);loaded.load(points)
            self.assertEqual(loaded.markers[0]['image_data_url'],value)
            loaded.markers[0].pop('image_data_url');loaded.cancel()
            self.assertEqual(loaded.markers[0]['image_data_url'],value)

    def test_invalid_image_rejected(self):
        for value in ['https://example.com/image.png','data:image/png;base64,bad',None]:
            with self.assertRaises(ValueError):decode_picture(value)
