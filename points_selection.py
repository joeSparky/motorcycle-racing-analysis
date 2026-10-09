"""Share the launcher's points selection with its analysis windows."""
import json
from pathlib import Path
from expression_editor import save_json

SETTINGS=Path(__file__).resolve().parent/'last-race.json'

def settings():
    try:return json.loads(SETTINGS.read_text(encoding='utf-8-sig'))
    except (OSError,ValueError):return {}

def selected_points(track_path):
    saved=settings()
    if not saved.get('track') or Path(saved['track']).resolve()!=Path(track_path).resolve():return None
    return saved.get('points') or None

def remember_points(track_path,points_path):
    saved=settings()
    if not saved.get('track') or Path(saved['track']).resolve()!=Path(track_path).resolve():return
    saved['points']=str(Path(points_path).resolve())
    save_json(SETTINGS,saved)
