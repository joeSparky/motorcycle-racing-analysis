import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import yaml
from expression_editor import save_dashboard_config

class GaugeSaveTests(unittest.TestCase):
    def test_save_keeps_video_settings_and_list_order(self):
        with tempfile.TemporaryDirectory() as folder:
            dashboard=Mock(); dashboard.config={'video':{'flip':True},'display':[{'label':'Old'}]}
            dashboard.config_path=Path(folder)/'dashboard.yaml'
            dashboard.display_frame.winfo_children.return_value=[]
            items=[{'label':'Second','type':'bar'},{'label':'First','type':'number'}]
            save_dashboard_config(dashboard,items)
            saved=yaml.safe_load(dashboard.config_path.read_text())
            self.assertEqual(saved['display'],items); self.assertTrue(saved['video']['flip'])
            self.assertEqual(dashboard.config,saved); dashboard.build_display.assert_called_once()

    def test_failed_save_keeps_live_dashboard(self):
        with tempfile.TemporaryDirectory() as folder:
            dashboard=Mock(); original={'display':[{'label':'Old'}]}; dashboard.config=original
            dashboard.config_path=Path(folder)/'dashboard.yaml'
            with patch.object(Path,'replace',side_effect=OSError('cannot replace')):
                with self.assertRaises(OSError): save_dashboard_config(dashboard,[])
            self.assertIs(dashboard.config,original); dashboard.build_display.assert_not_called()

if __name__=='__main__': unittest.main()
