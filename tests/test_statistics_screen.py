import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from race_statistics import Session
from statisticsScreen import StatisticsScreen
from test_statistics import CSV


class StatisticsScreenTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        path = Path(self.temp.name)/'race.csv'
        path.write_text(CSV)
        self.root = tk.Tk(); self.root.withdraw()
        self.screen = StatisticsScreen(self.root, Session(path))

    def tearDown(self):
        self.root.destroy(); self.temp.cleanup()

    def test_three_graphs_preserve_formulas_share_time_and_select_extrema(self):
        s = self.screen
        s.editor.expression.set('RPM')
        s.graph_count.set('3'); s.change_graph_count()
        s.graph_choice.current(1); s.choose_graph()
        s.editor.expression.set('Speed'); s.editor.units.set('mph')
        s.graph_choice.current(2); s.choose_graph()
        s.editor.expression.set('Throttle'); s.evaluate()
        self.assertEqual(len(s.figure.axes), 3)
        self.assertEqual([r['mean'] for r in s.results], [1400, 10, 50])
        s.plot_axes[0].set_xlim(1, 3)
        self.assertEqual(s.plot_axes[2].get_xlim(), (1, 3))
        s.seek = Mock()
        s.graph_click(SimpleNamespace(button=1, inaxes=s.plot_axes[2], xdata=2))
        s.seek.assert_called_with(2)
        s.graph_choice.current(1); s.choose_graph()
        self.assertEqual(s.editor.expression.get(), 'Speed')
        s.go_extreme('maximum_time'); s.seek.assert_called_with(2)
        s.graph_count.set('1'); s.change_graph_count()
        self.assertEqual(len(s.figure.axes), 1)
        s.graph_count.set('3'); s.change_graph_count()
        self.assertEqual(s.results[1]['mean'], 10)

    def test_invalid_graph_clears_results_and_does_not_seek_stale_extrema(self):
        s = self.screen
        s.graph_count.set('2'); s.change_graph_count()
        s.graph_choice.current(1); s.choose_graph()
        s.editor.expression.set('1/0')
        with patch('statisticsScreen.messagebox.showerror') as error:
            s.evaluate(); error.assert_called_once()
        self.assertEqual(s.results, [])
        self.assertIsNone(s.result)
        s.seek = Mock(); s.go_extreme('minimum_time'); s.seek.assert_not_called()

    def test_video_cursor_on_every_graph(self):
        s = self.screen
        s.graph_count.set('3'); s.change_graph_count()
        s.link = Mock(); s.link.current.return_value = 2
        s.follow_video()
        self.assertEqual(len(s.cursors), 3)
        self.assertTrue(all(c.get_xdata() == [2, 2] for c in s.cursors))
        s.link = None
