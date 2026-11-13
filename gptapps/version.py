"""Public release and immutable standalone-export build identification."""
import hashlib
import json
from pathlib import Path
import time

VERSION = '0.1.2'


def build_info():
    package=Path(__file__).parent
    metadata=package/'build-info.json'
    if metadata.is_file():
        return json.loads(metadata.read_text())
    digest=hashlib.sha256()
    for path in sorted(package.iterdir()):
        if path.is_file() and path.suffix in ('.py','.js','.html','.css'):
            digest.update(path.name.encode());digest.update(path.read_bytes())
    return {'version':VERSION,'build':str(int(digest.hexdigest()[:12],16))}


def stamp_build(package):
    info={'version':VERSION,'build':str(time.time_ns())}
    (Path(package)/'build-info.json').write_text(json.dumps(info)+'\n')
    return info
