#!/usr/bin/env python3
"""Link this project's SC extension and local connection descriptor; never overwrite another installation."""
import argparse,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def install(support):
    support=Path(support).expanduser();extension=support/'Extensions/ESP32Studio';connection=support/'ESP32Studio/connection.json'
    for path,target in ((extension,ROOT/'supercollider'),(connection,ROOT/'build/host/private/studio-client.json')):
        if path.is_symlink():
            if path.resolve()!=target.resolve():raise RuntimeError('Existing link points elsewhere: '+str(path))
        elif path.exists():raise RuntimeError('Existing installation left untouched: '+str(path))
        else:path.parent.mkdir(parents=True,exist_ok=True);path.symlink_to(target,target_is_directory=target.is_dir())
    print('Installed:',extension);print('In SuperCollider choose Language → Recompile Class Library once.')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    default=Path.home()/'Library/Application Support/SuperCollider' if sys.platform=='darwin' else Path(os.environ.get('APPDATA',Path.home()/'.local/share'))/'SuperCollider'
    p.add_argument('--support-dir',type=Path,default=default);install(p.parse_args().support_dir)
