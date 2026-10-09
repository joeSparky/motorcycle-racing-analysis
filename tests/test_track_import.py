import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile
from track_import import members, project
from track import load_track

class TrackImportTests(unittest.TestCase):
    def test_archive_to_usable_closed_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'tracks.ztracks'
            coords=[(410000000,-880000000,0),(410001000,-880000000,0),(410001000,-879999000,0)]
            payload=b''.join(struct.pack('<iii',*p) for p in coords)
            binary=b'<hpts\x00'+struct.pack('<I',len(payload))+b'\x00>'+payload+b'<pts\x00\x00\x00>'
            with zipfile.ZipFile(source,'w') as z:
                z.writestr('one.tkk',binary);z.writestr('two.tkk',binary)
            self.assertEqual(members(source),['one.tkk','two.tkk'])
            data=project(source,'two.tkk','Test track')
            self.assertEqual(data['nodes'][0]['position'],0)
            self.assertEqual(data['nodes'][-1]['position'],10000)
            self.assertEqual(data['nodes'][0]['reference'],data['nodes'][-1]['reference'])
            output=Path(tmp)/'project.json';output.write_text(json.dumps(data))
            geometry=load_track(output)
            self.assertEqual(len(geometry['lengths']),3)
            self.assertGreater(data['reference_length_m'],20)
    def test_missing_tracks_and_unsupported_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'tracks.ztracks'
            with zipfile.ZipFile(source,'w') as z:z.writestr('readme.txt','empty')
            with self.assertRaises(ValueError):members(source)
            with zipfile.ZipFile(source,'w') as z:z.writestr('bad.tkk',b'unknown layout')
            with self.assertRaises(ValueError):project(source,'bad.tkk','Bad')
