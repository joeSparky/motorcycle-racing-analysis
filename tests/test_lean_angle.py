import unittest

from expressions import ExpressionEvaluator
from expression_editor import available_expressions
from race_statistics import Session
from test_statistics import CSV
import tempfile
from pathlib import Path


class LeanAngleTests(unittest.TestCase):
    def test_known_angles_and_magnitude(self):
        e = ExpressionEvaluator(['GPS LatAcc'])
        for acceleration, angle in [(0, 0), (0.5, 26.565051177), (1, 45), (-1, -45), (1.2, 50.194428908)]:
            row = {'GPS LatAcc': acceleration}
            self.assertAlmostEqual(e.evaluate('degrees(atan([GPS LatAcc]))', row), angle, places=7)
            self.assertAlmostEqual(e.evaluate('abs(degrees(atan([GPS LatAcc])))', row), abs(angle), places=7)
        for value in ['nan', 'inf', '-inf', 'bad', '']:
            self.assertIsNone(e.evaluate('degrees(atan([GPS LatAcc]))', {'GPS LatAcc': value}))

    def test_function_whitelist(self):
        e = ExpressionEvaluator(['GPS LatAcc', 'atan'])
        self.assertEqual(e.evaluate('[atan]', {'atan': 42}), 42)
        for formula in ['atan', 'degrees + 1', 'abs()', 'atan(1, 2)', 'atan(x=1)',
                        'math.atan(1)', 'atan.__call__(1)', '__import__(1)', 'abs(*[1])', 'sin(1)']:
            with self.subTest(formula=formula), self.assertRaises(ValueError):
                e.compile(formula)

    def test_preset_respects_saved_expressions_and_missing_channel(self):
        preset = available_expressions(['GPS LatAcc'], {})['Estimated lean angle']
        self.assertEqual(preset['units'], 'deg')
        self.assertEqual(preset['bin_width'], 5)
        saved = {'Estimated lean angle': {'expression': '42'}}
        self.assertEqual(available_expressions(['GPS LatAcc'], saved), saved)
        self.assertEqual(available_expressions(['RPM'], {}), {})

    def test_statistics_use_derived_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'race.csv'
            path.write_text(CSV)
            session = Session(path)
            result = session.calculate('degrees(atan((Throttle-50)/50))', session.select('Entire recording'), 5)
            self.assertEqual(result['minimum'], -45)
            self.assertEqual(result['maximum'], 45)
            self.assertEqual(result['median'], 0)
            self.assertEqual(sum(result['histogram_counts']), 5)


if __name__ == '__main__':
    unittest.main()
