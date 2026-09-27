"""Read-only target diagnosis; export only the reviewed diff and photo counts."""
from contextlib import closing
import difflib
import sqlite3
from photo_visibility import visible_names


def inspect_target(root, preview):
    with closing(sqlite3.connect((root/'crm.db').as_uri()+'?mode=ro', uri=True)) as con:
        con.row_factory = sqlite3.Row
        row = dict(con.execute('SELECT * FROM cars WHERE auto_number=?', ('UA-0023',)).fetchone())
    if row['id'] != 33 or row['vin'] != 'KNAG541BNA169806':
        raise ValueError('TARGET_IDENTITY')
    folder = root/'video/foto/UA-0023'
    names = sorted(p.name for p in folder.iterdir() if p.suffix.lower() in {'.jpg','.jpeg','.png','.webp'})
    visible = visible_names(row, names, root)
    if len(names) != 38 or len(visible) != 37 or set(names)-set(visible) != {'001.jpg'}:
        raise ValueError('TARGET_PHOTO_DRIFT')
    patches = {}
    for path in sorted((preview/'before').iterdir()):
        before = path.read_text()
        after = (preview/'after'/path.name).read_text()
        patches[path.name] = ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                                        fromfile=path.name, tofile=path.name))
    return {'code':'UA-0023', 'source_photos':len(names), 'visible_photos':len(visible),
            'excluded_filenames':['001.jpg'], 'cover_before':row.get('cover_photo'),
            'diff':patches, 'crm_changed':False, 'production_changed':False}
