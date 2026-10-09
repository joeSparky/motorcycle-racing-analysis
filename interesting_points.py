"""Interesting point files shared with interestingPoints.html."""
import copy
import json
import math
import uuid
import numpy as np
import track


POINT_COLORS = {'entry':'#16a085','apex':'#b33ed2','exit':'#d14b39','marker':'#b7791f'}

def identity(geometry):
    config=geometry['config']
    if config.get('format') != 'track-editor-master-v1':
        raise ValueError('Interesting points require a prepared track JSON.')
    return dict(track=config['track'],divisions=config['divisions'],origin=config['origin'],
                reference=[[n['position'],*n['reference'][:2]] for n in config['nodes']])


def validate_identity(saved, current):
    if not isinstance(saved,dict): raise ValueError('Points file has no track identity.')
    if saved.get('divisions') != current['divisions']:
        raise ValueError('Points file uses a different track position scale.')
    try:
        a=saved['origin'];b=current['origin']
        same_origin=np.allclose([a['latitude'],a['longitude']],[b['latitude'],b['longitude']],rtol=0,atol=1e-9)
        first=np.asarray(saved['reference'],dtype=float);second=np.asarray(current['reference'],dtype=float)
        same_reference=first.shape==second.shape and np.allclose(first,second,rtol=0,atol=1e-6)
    except (KeyError,TypeError,ValueError):
        raise ValueError('Points file has an invalid track reference.')
    if not same_origin: raise ValueError('Points file uses a different track origin. Select the track project used to create these points.')
    if not same_reference: raise ValueError('Points file uses a different track shape or node positions. Select the original track project used to create these points.')
    # Names may change; coordinates and position scale determine compatibility.


class InterestingPoints:
    def __init__(self, geometry):
        self.geometry=geometry; self.markers=[]; self.saved=[]; self.path=None

    @property
    def dirty(self): return self.markers != self.saved

    def load(self,path):
        data=json.loads(path.read_text(encoding='utf-8-sig'))
        if data.get('format') != 'track-interesting-points-v1':
            raise ValueError('Choose an interesting-points JSON, not a track project or session file.')
        validate_identity(data.get('track_identity'),identity(self.geometry))
        markers=data.get('markers'); ids=set()
        if not isinstance(markers,list): raise ValueError('Invalid points file.')
        for m in markers:
            if (not isinstance(m,dict) or not isinstance(m.get('id'),str) or m['id'] in ids
                    or m.get('type') not in ('entry','apex','exit','marker')
                    or not isinstance(m.get('label'),str) or not isinstance(m.get('notes'),str)
                    or any(type(m.get(k)) not in (int,float) or not math.isfinite(m[k]) for k in ('x_m','y_m'))):
                raise ValueError('Invalid interesting point.')
            ids.add(m['id'])
        self.markers=copy.deepcopy(markers); self.saved=copy.deepcopy(markers); self.path=path

    def move(self,marker,point):
        x,y=map(float,point)
        if not math.isfinite(x) or not math.isfinite(y): raise ValueError('Invalid point location.')
        lon,lat=np.array([x,y])/self.geometry['scale']+self.geometry['origin']
        position=track.classify(lon,lat,self.geometry)[0]
        marker.update(x_m=x,y_m=y,longitude_deg=float(lon),latitude_deg=float(lat),track_position=position)

    def add(self,point):
        marker=dict(id=str(uuid.uuid4()),type='apex',label='New point',notes='')
        self.move(marker,point); self.markers.append(marker); return marker

    def cancel(self): self.markers=copy.deepcopy(self.saved)

    def save(self,path):
        data=dict(format='track-interesting-points-v1',track_identity=identity(self.geometry),
                  coordinate_system='local metres: x east, y north, relative to track origin',markers=self.markers)
        temporary=path.with_name(path.name+'.tmp')
        temporary.write_text(json.dumps(data,indent=2,allow_nan=False),encoding='utf-8')
        temporary.replace(path)
        self.saved=copy.deepcopy(self.markers); self.path=path
