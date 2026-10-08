import io
import math
from pathlib import Path
import tempfile
import unittest

from expressions import ExpressionEvaluator
from race_statistics import Session

CSV = '''"Format","AiM CSV File"
"Track","Test"
"Beacon Markers",0,2,4
"Time","RPM","Speed","Throttle"
"s","rpm","mph","%"
0,0,0,0
1,1000,10,100
2,2000,20,50
3,0,0,0
4,4000,20,100
'''


class StatisticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        path = Path(self.temp.name)/'race.csv'; path.write_text(CSV)
        self.session = Session(path)

    def tearDown(self): self.temp.cleanup()

    def test_all_statistics_and_tied_mode(self):
        s=self.session; r=s.calculate('RPM',s.select('Entire recording'))
        self.assertEqual(r['mean'],1400); self.assertEqual(r['median'],1000)
        self.assertEqual(r['modes'],[0]); self.assertEqual(r['mode_count'],2)
        self.assertEqual(r['weighted_mean'],1250); self.assertEqual(r['weighted_duration'],4)
        r=s.calculate('RPM/Speed',s.select('Entire recording'))
        self.assertEqual((r['valid'],r['omitted']),(3,2)); self.assertEqual(r['median'],100)

    def test_engine_gaps_not_bridged(self):
        s=self.session; mask=s.select('Engine running',rpm=0)
        self.assertEqual(mask,[False,True,True,False,True])
        r=s.calculate('RPM',mask)
        self.assertEqual(r['weighted_duration'],1); self.assertEqual(r['weighted_mean'],1500)
        self.assertIsNone(r['values'][3])

    def test_race_time_and_lap_boundaries(self):
        s=self.session
        self.assertEqual(s.select('Time interval',start=1,end=2),[False,True,True,False,False])
        self.assertEqual(s.select('Race running',start=1,end=3),[False,True,True,True,False])
        self.assertEqual(s.select('Lap',lap=2),[False,False,True,True,False])
        with self.assertRaises(ValueError): s.select('Lap',lap=3)
        with self.assertRaises(ValueError): s.select('Race running',start=3,end=1)

    def test_segment_wrap_and_offtrack(self):
        s=self.session; s.geometry={'config':{'divisions':10000}}
        for row,p in zip(s.rows,[9900,100,500,2000,4000]):
            row.update(TrackPosition=str(p),OffTrack='false')
        s.rows[1]['OffTrack']='true'
        self.assertEqual(s.select('Segment of lap',lap=1,position_start=9800,position_end=200),[True,False,False,False,False])
        self.assertEqual(s.select('Segment of lap',lap=2,position_start=0,position_end=10000),[False,False,True,True,False])

    def test_binned_ties_and_negative_bins(self):
        s=self.session; r=s.calculate('RPM-1500',s.select('Entire recording'),1000)
        self.assertEqual(r['modes'],[-2]); self.assertEqual(r['mode_count'],2)
        r=s.calculate('Speed',s.select('Entire recording'))
        self.assertEqual(r['modes'],[0,20])

    def test_comparison_and_single_sample(self):
        s=self.session; r=s.calculate('Throttle > 90',s.select('Entire recording'))
        self.assertAlmostEqual(r['mean'],.4)
        r=s.calculate('RPM',s.select('Time interval',start=3.5,end=4))
        self.assertIsNone(r['weighted_mean']); self.assertEqual(r['valid'],1)

    def test_expression_validation_and_invalid_values(self):
        e=ExpressionEvaluator(['RPM','GPS Speed'])
        self.assertEqual(e.evaluate('RPM/[GPS Speed]',{'RPM':1000,'GPS Speed':10}),100)
        self.assertIsNone(e.evaluate('(RPM / 0) + 1',{'RPM':1000}))
        self.assertIsNone(e.evaluate('RPM % 0',{'RPM':1000}))
        self.assertIsNone(e.evaluate('RPM > 0',{'RPM':'nan'}))
        for formula in ['__import__("os")','RPM.real','[missing]','2 ** (2 ** 1000)','foo','RPM[0]']:
            if formula == '2 ** (2 ** 1000)': self.assertIsNone(e.evaluate(formula,{}))
            else:
                with self.assertRaises(ValueError): e.compile(formula)
        self.assertIsNone(e.evaluate('(-1)**0.5',{}))
        with self.assertRaises(ValueError): self.session.calculate('RPM',[False]*5)
        with self.assertRaises(ValueError): self.session.calculate('RPM',[True]*5,-1)

    def test_real_track_enrichment(self):
        import json
        path=Path(self.temp.name)/'gps.csv'
        path.write_text(CSV.replace('"Throttle"','"Throttle","GPS Latitude","GPS Longitude"')
            .replace('"%"','"%","deg","deg"')
            .replace('0,0,0,0','0,0,0,0,40,-88')
            .replace('1,1000,10,100','1,1000,10,100,40,-87.9999')
            .replace('2,2000,20,50','2,2000,20,50,40.0001,-87.9999')
            .replace('3,0,0,0','3,0,0,0,40.0001,-88')
            .replace('4,4000,20,100','4,4000,20,100,40,-88'))
        track_path=Path(self.temp.name)/'track.json'
        track_path.write_text(json.dumps(dict(format='track-editor-master-v1',divisions=10000,
            origin=dict(latitude=40,longitude=-88),nodes=[dict(position=p,reference=xy)
            for p,xy in zip([0,2500,5000,7500,10000],[[0,0],[8.52,0],[8.52,11.12],[0,11.12],[0,0]])])))
        session=Session(path); session.load_track(track_path)
        self.assertIn('TrackPosition',session.rows[0])
        self.assertEqual(len(session.select('Segment of lap',lap=1,position_start=0,position_end=10000)),5)
        self.assertEqual(len(session.rows),5)

    def test_nonincreasing_time_rejected(self):
        path=Path(self.temp.name)/'bad.csv'; path.write_text(CSV.replace('2,2000','1,2000'))
        with self.assertRaises(ValueError): Session(path)

    def test_long_gaps_not_time_weighted(self):
        self.session.times=[0,1,2,10,11]
        r=self.session.calculate('RPM',[True]*5)
        self.assertEqual(r['weighted_duration'],3)


if __name__=='__main__': unittest.main()
