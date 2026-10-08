"""Calibrated video navigation for the statistics screen."""
import json
import math
from pathlib import Path
from mpv_ipc import MpvConnection

class VideoLink:
    def __init__(self, socket, state):
        self.mpv = MpvConnection(socket)
        self.state = Path(state)

    def mapping(self):
        data = json.loads(self.state.read_text(encoding='utf-8'))
        slope, offset = float(data['slope']), float(data['offset']) + float(data.get('adjustment',0))
        if not math.isfinite(slope) or slope <= 0 or not math.isfinite(offset):
            raise ValueError('Invalid calibration')
        return slope, offset

    def current(self):
        slope,offset = self.mapping()
        value = self.mpv.get_property('time-pos')
        return None if value is None else (float(value)-offset)/slope

    def seek(self, recording_time):
        slope,offset = self.mapping()
        target = slope*recording_time+offset
        duration = self.mpv.get_property('duration')
        if not math.isfinite(target) or target < 0 or (duration is not None and target > float(duration)):
            raise ValueError('That recording time is outside the video.')
        return self.mpv.command('seek',target,'absolute+exact')

    def close(self): self.mpv.close()
