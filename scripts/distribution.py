#!/usr/bin/env python3
"""Build a source-only archive or install selected standalone skills locally.

Never downloads packages, changes Codex config, replaces an installed skill,
or copies credentials/model weights. --dest is explicit; --dry-run is available.
"""
import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

EXTENSIONS={'.md','.py','.json','.yaml','.yml','.toml','.txt','.sh'}
BLOCKED={'.git','.venv','venv','__pycache__','.pytest_cache','.superpowers','artifacts','models','dist','node_modules'}
ROOT_FILES={'README.md','LICENSE','NOTICE.md','.gitignore','requirements-dev.txt'}
DOC_FILES={'installation.md','security.md','usage-history.md','verification.md','migration.md','architecture.md'}
PRIVATE=re.compile(r'/(?:Users|home)/[^\s/]+/|[A-Za-z]:\\Users\\|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bsk-[A-Za-z0-9_-]{20,}|\bocid1\.[A-Za-z0-9._-]+|https?://(?:\d{1,3}\.){3}\d{1,3}')


def allowed(rel):
    if any(p in BLOCKED or p.startswith('local.') or p.startswith('.env') for p in rel.parts):return False
    if rel.name in ROOT_FILES:return True
    return rel.suffix in EXTENSIONS


def scan(path):
    if path.stat().st_size>2_000_000:raise ValueError('Oversized distributable: '+path.name)
    data=path.read_bytes()
    try:content=data.decode('utf-8')
    except UnicodeDecodeError:raise ValueError('Binary file not allowed: '+path.name)
    if PRIVATE.search(content):raise ValueError('Possible private content: '+path.name)
    return data


def skill_files(root,name):
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',name):raise ValueError('Invalid skill name')
    base=root/'skills'/name
    if base.is_symlink() or not (base/'SKILL.md').is_file():raise ValueError('Unknown or symlinked skill')
    selected=[]
    for p in sorted(base.rglob('*')):
        rel=p.relative_to(base)
        if not allowed(rel):continue
        if p.is_symlink():raise ValueError('Symlinks are not distributable: '+str(rel))
        if p.is_file():scan(p);selected.append((p,rel))
    return selected


def install(root,destination,names=None,dry_run=False):
    root,destination=Path(root).resolve(),Path(destination).expanduser().resolve()
    names=names or sorted(p.name for p in (root/'skills').iterdir() if p.is_dir())
    if len(names)!=len(set(names)):raise ValueError('Duplicate selected skill')
    jobs=[]
    for name in names:
        files=skill_files(root,name);target=destination/name
        if target.exists() or target.is_symlink():raise FileExistsError('Installed skill already exists: '+name)
        jobs.append((name,files,target))
    if dry_run:return {'skills':names,'dry_run':True}
    destination.mkdir(parents=True,exist_ok=True)
    for name,files,target in jobs:
        with tempfile.TemporaryDirectory(prefix='.skill-install-',dir=destination) as temp:
            stage=Path(temp)/name;stage.mkdir()
            for source,rel in files:
                out=stage/rel;out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,out)
            if target.exists():raise FileExistsError(target)
            stage.rename(target)
    return {'skills':names,'dry_run':False}


def source_files(root):
    root=Path(root);found=[]
    for p in sorted(root.rglob('*')):
        rel=p.relative_to(root)
        if not allowed(rel):continue
        scope=(len(rel.parts)==1 and rel.name in ROOT_FILES) or rel.parts[0] in {'skills','scripts','tests','.codex-plugin'} or (rel.parts[0]=='docs' and rel.name in DOC_FILES)
        if not scope:continue
        if p.is_symlink():raise ValueError('Symlink in release: '+str(rel))
        if p.is_file():found.append((rel,scan(p)))
    return found


def publish_file(source,output):
    """Exclusive publication; unsupported hardlinks fall back to non-atomic copy."""
    try:os.link(source,output)
    except OSError as exc:
        if exc.errno not in {errno.ENOTSUP,errno.EOPNOTSUPP,errno.ENOSYS,errno.EXDEV,errno.EPERM}:raise
        created=False
        try:
            fd=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as dest:
                created=True
                with Path(source).open('rb') as src:shutil.copyfileobj(src,dest)
                dest.flush();os.fsync(dest.fileno())
        except BaseException:
            if created:Path(output).unlink(missing_ok=True)
            raise


def archive(root,output):
    root,output=Path(root).resolve(),Path(output)
    if output.exists():raise FileExistsError(output)
    files=source_files(root);output.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.release-',suffix='.zip',dir=output.parent);os.close(fd)
    try:
        with zipfile.ZipFile(tmp,'w',compression=zipfile.ZIP_DEFLATED) as z:
            for rel,data in files:
                info=zipfile.ZipInfo('workplace-toolkit/'+rel.as_posix(),date_time=(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
                z.writestr(info,data)
        publish_file(tmp,output)
    finally:Path(tmp).unlink(missing_ok=True)
    return {'files':len(files),'sha256':hashlib.sha256(output.read_bytes()).hexdigest()}


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    i=sub.add_parser('install');i.add_argument('--dest',required=True);i.add_argument('--skill',action='append');i.add_argument('--dry-run',action='store_true')
    a=sub.add_parser('archive');a.add_argument('output')
    sub.add_parser('scan')
    args=p.parse_args();root=Path(__file__).resolve().parents[1]
    if args.command=='install':result=install(root,args.dest,args.skill,args.dry_run)
    elif args.command=='archive':result=archive(root,args.output)
    else:result={'files':len(source_files(root)),'scan':'passed'}
    print(json.dumps(result))

if __name__=='__main__':main()
