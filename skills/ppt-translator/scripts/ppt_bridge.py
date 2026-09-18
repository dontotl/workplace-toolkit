#!/usr/bin/env python3
"""Local-only OOXML bridge. The calling Codex session supplies translations.

No model clients, credentials, network calls or font resizing live here.
Requires lxml. Tests/fixture generation additionally require python-pptx.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import copy
import errno
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import shutil
import subprocess
import tempfile
import zipfile

from lxml import etree as ET

NS = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
      'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
URL = re.compile(r'https?://[^\s<>]+')
NUMBER = re.compile(r'[+\-−]?[\$€£¥₩]?\s*\d+(?:[.,]\d+)*%?')
UNIT = re.compile(r'(?<![A-Za-z])(?:KB|MB|GB|TB|GHz|MHz|ms|Mbps|Gbps|kWh|MW)(?![A-Za-z])')


def xml(data):
    if b'<!DOCTYPE' in data or b'<!ENTITY' in data:
        raise ValueError('DTD/entity declarations are not supported')
    return ET.fromstring(data, ET.XMLParser(resolve_entities=False, no_network=True))


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def ordered_parts(z):
    names = z.namelist()
    if len(names) != len(set(names)):
        raise ValueError('Duplicate ZIP members')
    rels = xml(z.read('ppt/_rels/presentation.xml.rels'))
    targets = {}
    for r in rels:
        if r.get('TargetMode') == 'External': continue
        target = r.get('Target', '')
        targets[r.get('Id')] = posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join('ppt', target))
    parts = []
    for n in xml(z.read('ppt/presentation.xml')).findall('p:sldIdLst/p:sldId', NS):
        part = targets[n.get('{'+NS['r']+'}id')]
        if not part.startswith('ppt/slides/') or part not in names: raise ValueError('Invalid slide relationship')
        parts.append(part)
    return parts


def text_nodes(root):
    # Skip dynamic fields; translating their cached value would be overwritten by Office.
    return root.xpath('.//a:t[not(ancestor::a:fld)]', namespaces=NS)


def manifest_digest(manifest):
    data={k:v for k,v in manifest.items() if k!='manifest_sha256'}
    return hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()


def extract(source, protected_terms=()):
    if not isinstance(protected_terms,(list,tuple)) or any(not isinstance(t,str) or not t for t in protected_terms):
        raise ValueError('protected_terms must contain nonempty strings')
    source = Path(source)
    if source.suffix.lower() != '.pptx': raise ValueError('Convert legacy .ppt first with convert-legacy')
    segments, warnings = [], []
    with zipfile.ZipFile(source) as z:
        parts = ordered_parts(z)
        for slide, part in enumerate(parts, 1):
            root = xml(z.read(part))
            for idx, n in enumerate(text_nodes(root)):
                if not (n.text or '').strip(): continue
                parents = list(n.iterancestors())
                para = next((a for a in parents if a.tag == '{'+NS['a']+'}p'), n)
                shape = next((a for a in parents if a.tag in ['{'+NS['p']+'}sp','{'+NS['p']+'}graphicFrame']), None)
                ids = [] if shape is None else shape.xpath('.//p:cNvPr/@id', namespaces=NS)
                segments.append({'id': f'{part}#t{idx}', 'part': part, 'node': idx,
                                 'slide': slide, 'shape': ids[0] if ids else None,
                                 'source': n.text, 'context': ''.join(para.itertext())})
            for kind, xp in [('image-not-ocr-reviewed','.//p:pic'), ('chart-not-translated','.//*[local-name()="chart"]'),
                             ('smartart-not-translated','.//*[local-name()="relIds"]'),('dynamic-field-preserved','.//a:fld'),
                             ('animation-preserved-not-translated','.//p:timing')]:
                if root.xpath(xp,namespaces=NS): warnings.append({'slide':slide,'kind':kind})
        for part in sorted(z.namelist()):
            if part.startswith(('ppt/slideMasters/','ppt/slideLayouts/')) and part.endswith('.xml'):
                if any((n.text or '').strip() for n in xml(z.read(part)).findall('.//a:t',NS)):
                    warnings.append({'part':part,'kind':'master-layout-text-not-translated'})
    manifest={'version':2, 'source_sha256':sha(source), 'slide_count':len(parts),
            'segments':segments,'protected_terms':list(protected_terms), 'warnings':warnings,
            'notes':'preserved, not translated'}
    manifest['manifest_sha256']=manifest_digest(manifest)
    return manifest


def protected(text, terms):
    return {'numbers':tuple(n.replace(' ','').strip() for n in NUMBER.findall(text)), 'urls':Counter(URL.findall(text)),
            'units':Counter(UNIT.findall(text)), 'terms':Counter({t:text.count(t) for t in terms if t})}


def validate(source, manifest, translated):
    fresh=extract(source,manifest.get('protected_terms',[]))
    if manifest!=fresh:raise ValueError('Manifest does not match source or extraction policy; re-extract')
    if translated.get('source_sha256') != fresh['source_sha256']: raise ValueError('Translation source hash mismatch')
    if translated.get('manifest_sha256') != fresh['manifest_sha256']: raise ValueError('Translation manifest hash mismatch')
    entries=translated.get('translations')
    if not isinstance(entries,list): raise ValueError('translations must be a list')
    ids=[s['id'] for s in fresh['segments']]
    if any(not isinstance(e,dict) or not isinstance(e.get('id'),str) or not isinstance(e.get('text'),str) or not e['text'].strip() for e in entries):
        raise ValueError('Every translation needs id and nonempty text')
    if Counter(e['id'] for e in entries)!=Counter(ids): raise ValueError('Missing, duplicate or unknown segment IDs')
    mapping={e['id']:e['text'] for e in entries}
    # Per paragraph: preserve numeric order and formatting; human review still checks meaning.
    groups=defaultdict(list)
    with zipfile.ZipFile(source) as z:
        roots={p:xml(z.read(p)) for p in ordered_parts(z)}
        for s in fresh['segments']:
            n=text_nodes(roots[s['part']])[s['node']]
            if n.getparent().xpath('./a:rPr/a:hlinkClick|./a:rPr/a:hlinkMouseOver',namespaces=NS):
                if Counter(URL.findall(s['source']))!=Counter(URL.findall(mapping[s['id']])):
                    raise ValueError('A URL moved out of its hyperlinked text run')
            para=next((a for a in n.iterancestors() if a.tag=='{'+NS['a']+'}p'),n)
            groups[(s['part'], roots[s['part']].getroottree().getpath(para))].append(s)
    terms=manifest.get('protected_terms',[])
    if not isinstance(terms,list) or any(not isinstance(t,str) for t in terms):raise ValueError('protected_terms must contain strings')
    for group in groups.values():
        before=''.join(s['source'] for s in group);after=''.join(mapping[s['id']] for s in group)
        if protected(before,terms)!=protected(after,terms):raise ValueError('Protected numbers/URLs/units/terms changed on slide '+str(group[0]['slide']))
    return mapping


def patch_members(source, manifest, mapping):
    members={}
    with zipfile.ZipFile(source) as z:
        for s in manifest['segments']:
            if s['part'] not in members:members[s['part']]=xml(z.read(s['part']))
            text_nodes(members[s['part']])[s['node']].text=mapping[s['id']]
    return {p:ET.tostring(root,encoding='UTF-8',xml_declaration=True,standalone=True) for p,root in members.items()}


def publish_file(source, output):
    """No clobber, with exclusive-copy fallback on filesystems without hardlinks.

    Fallback visibility is not atomic. Failed copies remove only the file created here.
    """
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


def publish_bytes(data, output):
    output=Path(output)
    if output.exists():raise FileExistsError(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.ppt-bridge-',dir=output.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        publish_file(name,output)
    finally:Path(name).unlink(missing_ok=True)


def apply(source, manifest, translated, output):
    source,output=Path(source),Path(output)
    if source.resolve()==output.resolve():raise ValueError('Original cannot be output')
    if output.exists():raise FileExistsError(output)
    mapping=validate(source,manifest,translated)
    members=patch_members(source,manifest,mapping)
    output.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.ppt-bridge-',suffix='.pptx',dir=output.parent);os.close(fd)
    try:
        with zipfile.ZipFile(source) as src,zipfile.ZipFile(name,'w') as dest:
            dest.comment=src.comment
            for info in src.infolist():
                if info.filename in members:dest.writestr(copy(info),members[info.filename])
                else:
                    with src.open(info) as stream,dest.open(copy(info),'w',force_zip64=info.file_size>zipfile.ZIP64_LIMIT) as target:
                        shutil.copyfileobj(stream,target,1024*1024)
        report=verify(source,name,manifest,translated)
        if not report['passed']:raise ValueError('Output validation failed')
        publish_file(name,output)
    finally:Path(name).unlink(missing_ok=True)
    return report


def members_equal(source,dest,name):
    with source.open(name) as left,dest.open(name) as right:
        while True:
            a=left.read(1024*1024);b=right.read(1024*1024)
            if a!=b:return False
            if not a:return True


def verify(source, output, manifest, translated):
    mapping=validate(source,manifest,translated);expected=patch_members(source,manifest,mapping);issues=[]
    with zipfile.ZipFile(source) as src,zipfile.ZipFile(output) as dest:
        if Counter(src.namelist())!=Counter(dest.namelist()):issues.append('Package members differ')
        for name in src.namelist():
            if name not in dest.namelist():continue
            equal=dest.read(name)==expected[name] if name in expected else members_equal(src,dest,name)
            if not equal:issues.append('Unexpected content: '+name)
        if dest.testzip():issues.append('Corrupt ZIP member')
    return {'passed':not issues,'issues':issues,'segments':len(mapping),'slides':manifest['slide_count'],
            'source_sha256':sha(source),'output_sha256':sha(output),'visual_qa':'not performed by structural verifier',
            'unsupported':extract(source,manifest['protected_terms'])['warnings']}


def convert_legacy(source, output):
    source,output=Path(source).resolve(),Path(output)
    if source.suffix.lower()!='.ppt' or output.suffix.lower()!='.pptx':raise ValueError('Expected .ppt input and .pptx output')
    if output.exists():raise FileExistsError(output)
    office=shutil.which('soffice')
    if not office:raise RuntimeError('LibreOffice is required for legacy .ppt; install locally or convert with PowerPoint')
    with tempfile.TemporaryDirectory(prefix='ppt-convert-') as d:
        profile=(Path(d)/'profile').as_uri()
        try:
            subprocess.run([office,'-env:UserInstallation='+profile,'--headless','--convert-to','pptx','--outdir',d,str(source)],check=True,capture_output=True,timeout=180)
        except (subprocess.CalledProcessError,subprocess.TimeoutExpired):
            raise RuntimeError('Local legacy conversion failed or timed out') from None
        converted=Path(d)/(source.stem+'.pptx')
        extract(converted)
        publish_bytes(converted.read_bytes(),output)


def main():
    p=argparse.ArgumentParser(description=__doc__);subs=p.add_subparsers(dest='cmd',required=True)
    e=subs.add_parser('extract');e.add_argument('source');e.add_argument('output');e.add_argument('--protect',action='append',default=[])
    for name in ['apply','verify']:
        s=subs.add_parser(name);s.add_argument('source');s.add_argument('manifest');s.add_argument('translations');s.add_argument('output');s.add_argument('--report')
    c=subs.add_parser('convert-legacy');c.add_argument('source');c.add_argument('output')
    args=p.parse_args()
    try:
        if args.cmd=='extract':
            m=extract(args.source,args.protect)
            publish_bytes(json.dumps(m,ensure_ascii=False,indent=2).encode(),args.output)
            print(json.dumps({'slides':m['slide_count'],'segments':len(m['segments']),'warnings':len(m['warnings'])}))
        elif args.cmd=='convert-legacy':convert_legacy(args.source,args.output);print('Converted locally')
        else:
            m=json.loads(Path(args.manifest).read_text(encoding='utf-8'));t=json.loads(Path(args.translations).read_text(encoding='utf-8'))
            report=globals()[args.cmd](args.source,m,t,args.output) if args.cmd=='apply' else verify(args.source,args.output,m,t)
            if args.report:publish_bytes(json.dumps(report,ensure_ascii=False,indent=2).encode(),args.report)
            print(json.dumps({'passed':report['passed'],'slides':report['slides'],'segments':report['segments']}))
            if not report['passed']:raise SystemExit(1)
    except (ValueError,OSError,zipfile.BadZipFile,ET.XMLSyntaxError,KeyError,RuntimeError) as exc:
        # Never print source text or provider secrets in the default status channel.
        print(json.dumps({'error':type(exc).__name__,'message':str(exc) if not isinstance(exc,OSError) else 'Local file operation failed'}));raise SystemExit(1)


if __name__=='__main__':main()
