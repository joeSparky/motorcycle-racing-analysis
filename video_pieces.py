"""Create an mpv virtual timeline from ordered local video pieces."""
import hashlib
from pathlib import Path
import re

def natural_key(path):
    return [int(x) if x.isdigit() else x.casefold() for x in re.split(r'(\d+)',Path(path).name)]

def ordered_pieces(paths):
    pieces=sorted((Path(p).resolve() for p in paths), key=natural_key)
    if len(set(pieces)) != len(pieces):
        raise ValueError('A video piece was selected more than once.')
    if not pieces or any(not p.is_file() for p in pieces):
        raise ValueError('Select existing video files.')
    if len({p.parent for p in pieces}) != 1:
        raise ValueError('Put all pieces for this recording in the same folder first.')
    numbers=[]
    for p in pieces:
        m=re.search(r'_(\d+)\.[^.]+$',p.name)
        if m: numbers.append(int(m.group(1)))
    if len(numbers)==len(pieces) and any(b != a+1 for a,b in zip(numbers,numbers[1:])):
        raise ValueError('A numbered video piece is missing. Select a consecutive set of pieces.')
    return pieces

def create_timeline(pieces):
    pieces=ordered_pieces(pieces)
    digest=hashlib.sha256('\n'.join(p.name for p in pieces).encode('utf-8')).hexdigest()[:12]
    output=pieces[0].parent/('race-video-'+digest+'.edl')
    lines=['# mpv EDL v0']
    for p in pieces:
        name=p.name
        lines.append('%'+str(len(name.encode('utf-8')))+'%'+name)
    output.write_bytes(('\n'.join(lines)+'\n').encode('utf-8'))
    return output
