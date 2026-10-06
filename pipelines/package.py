"""Build a portable artifact, excluding runtime binaries, caches and partial attempts."""
from pathlib import Path
import hashlib
import zipfile


def main():
    root=Path(__file__).resolve().parents[1]
    target=root.parent/'rca-benchmark-lab-unified-v5.zip'
    excluded={'.deps','.eda_deps','.venv','__pycache__','wheelhouse','.git'}
    files=[]
    import os
    for current,dirs,names in os.walk(root):
        dirs[:]=[d for d in dirs if d not in excluded]
        for name in names:
            p=Path(current)/name
            rel=p.relative_to(root)
            if rel.parts[:2]==('data','internal'):continue
            if rel.parts[0]=='experiments' and len(rel.parts)>1 and rel.parts[1]!='unified':continue
            if rel.parts[:2]==('experiments','unified') and len(rel.parts)>2 and rel.parts[2].endswith('-validated'):continue
            if name.startswith('my_') or name.startswith('.env'):continue
            if p.suffix in ('.pyc','.tmp'):continue
            if rel.parts[:3] in (('data','public','rcaeval_csv'),('data','public','rcaeval'),('data','public','telecomts')):continue
            files.append(p)
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for p in files:archive.write(p,Path(root.name)/p.relative_to(root))
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:raise ValueError('ZIP CRC check failed')
    digest=hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.zip.sha256').write_text(f'{digest}  {target.name}\n',encoding='ascii')
    print(dict(path=str(target),files=len(files),bytes=target.stat().st_size,sha256=digest))


if __name__=='__main__':main()
