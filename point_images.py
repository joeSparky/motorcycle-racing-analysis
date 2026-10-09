"""Portable point reference pictures, stored as PNG data URLs."""
import base64
import io
from PIL import Image, ImageOps

MAX_BYTES=10*1024*1024


def image_data_url(path):
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('Choose a picture smaller than 10 MB.')
    with Image.open(path) as source:
        source.load()
        picture=ImageOps.exif_transpose(source).convert('RGB')
        picture.thumbnail((1600,1600))
        output=io.BytesIO();picture.save(output,format='PNG')
    if output.tell() > MAX_BYTES: raise ValueError('Picture is too large after conversion.')
    return 'data:image/png;base64,'+base64.b64encode(output.getvalue()).decode('ascii')


def decode_picture(value):
    if not isinstance(value,str) or not value.startswith('data:image/png;base64,') or len(value)>MAX_BYTES*4/3+100:
        raise ValueError('Invalid embedded reference picture.')
    try:
        raw=base64.b64decode(value.split(',',1)[1],validate=True)
        with Image.open(io.BytesIO(raw)) as source:
            if source.format != 'PNG' or max(source.size)>1600: raise ValueError('Invalid embedded reference picture.')
            source.load();return source.copy()
    except (OSError,ValueError) as exc:
        raise ValueError('Invalid embedded reference picture.') from exc
