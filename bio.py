import mmap
import contextlib
import os
import subprocess
import tempfile
from datetime import datetime
from operator import attrgetter

import config


root = config.DEFAULT['root']
with contextlib.suppress(FileExistsError):
    os.makedirs(root)


class BioFile:
    def __init__(self, path):
        self.path = path
        self.meta = os.stat(path)
        self.content = None

        if self.meta.st_size == 0:
            return

        with open(path, 'r+b') as f:
            with contextlib.closing(mmap.mmap(f.fileno(), 0)) as mm:
                self.content = mm.read()

    def __repr__(self):
        return f'<{self.path}, {datetime.fromtimestamp(self.meta.st_mtime)}>'


def get_meta(root_dir: str) -> list:
    meta = []
    for dirpath, _, files in os.walk(root_dir):
        for filename in files:
            path = f'{dirpath}/{filename}'
            meta.append(BioFile(path))
    return sorted(meta, key=attrgetter('meta.st_mtime'), reverse=True)


def temp(category: str = 'md') -> tuple:
    suffix = config.CATEGORY.get(category, category)
    template = config.TEMPLATE.get(category)
    if template:
        with open(template) as f:
            template_string = f.read()
    else:
        template_string = ''

    with tempfile.NamedTemporaryFile(suffix=f'.{suffix}', dir=root,
                                     delete=False) as tf:
        filename = tf.name
        tf.write(template_string.encode())
        tf.flush()

        subprocess.call([config.DEFAULT['editor'], filename])
        edited = tf.read()

    return filename, edited
