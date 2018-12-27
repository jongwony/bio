import base64
import binascii
import os
from io import BytesIO, BufferedIOBase

from PIL import Image

is_screen = os.environ.get('TERM').startswith('screen')
osc = b'\033Ptmux;\033\033]' if is_screen else b'\033]'
st = b'\a\033\\' if is_screen else b'\a'


def get_content(content) -> bytes:
    # bytes
    if isinstance(content, bytes):
        return content

    # file-like object
    if isinstance(content, BufferedIOBase):
        return content.read()

    # str
    try:
        # base64 string
        return base64.b64decode(content, validate=True)
    except binascii.Error:
        # filename
        with open(content, 'rb') as f:
            raw_content = f.read()
        return raw_content


def buffer_resize(raw_content, resize) -> bytes:
    with Image.open(BytesIO(get_content(raw_content))) as origin:
        fmt = origin.format
        resized = origin.resize(resize)

    with BytesIO() as buf:
        resized.save(buf, format=fmt)
        resized_content = buf.getvalue()

    return resized_content


def iterm2_img_format(content, inline):
    raw_content = get_content(content)
    size = len(raw_content)
    b64content = base64.b64encode(raw_content)

    result = osc
    result += b'1337;File='
    result += b'size=%s;' % bytes(str(size).encode())
    result += b'inline=%s' % bytes(str(inline).encode())
    result += b':'
    result += b'%s' % b64content
    result += st
    result += b'\n'

    return result


def print_image(content, inline=1, resize=None):
    if resize is not None:
        content = buffer_resize(content, resize)
    print(iterm2_img_format(content, inline).decode())
