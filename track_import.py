"""Create a prepared track project from an offline AiM track export."""
import math
from pathlib import Path
import zipfile
from trackcsv import decode

LIMIT = 32 * 1024 * 1024

def members(source):
    with zipfile.ZipFile(source) as archive:
        names=[i.filename for i in archive.infolist() if not i.is_dir() and i.filename.lower().endswith('.tkk')]
    if not names: raise ValueError('This archive contains no .tkk tracks.')
    if len(set(names)) != len(names): raise ValueError('Archive contains duplicate track names.')
    return names

def project(source, member, name):
    source=Path(source)
    with zipfile.ZipFile(source) as archive:
        info=archive.getinfo(member)
        if info.file_size>LIMIT: raise ValueError('Track member exceeds 32 MiB.')
        rows=decode(archive.read(info))
    coords=[]
    for row in rows:
        coord=(float(row[1]),float(row[2]))
        if not coords or coord!=coords[-1]: coords.append(coord)
    if len(coords)<3: raise ValueError('Track needs at least three distinct consecutive points.')
    if coords[-1]!=coords[0]: coords.append(coords[0])
    lat,lon=coords[0]
    scale=math.pi/180*6371000
    if abs(math.cos(math.radians(lat)))<1e-6: raise ValueError('Track origin is too close to a pole.')
    xy=[[(xlon-lon)*scale*math.cos(math.radians(lat)),(xlat-lat)*scale] for xlat,xlon in coords]
    distances=[0.0]
    for a,b in zip(xy,xy[1:]): distances.append(distances[-1]+math.dist(a,b))
    if distances[-1]<=0: raise ValueError('Track has zero length.')
    return dict(format='track-editor-master-v1',track=name,divisions=10000,
                origin=dict(latitude=lat,longitude=lon),reference_length_m=distances[-1],
                source_archive=source.name,source_member=member,preparation_version=1,
                nodes=[dict(position=d/distances[-1]*10000,reference=p) for d,p in zip(distances,xy)],
                aerial_patches=[])
