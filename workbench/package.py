"""Package only public/demo inputs; private input directory is deliberately excluded."""
from pathlib import Path
import os,zipfile,hashlib


def main():
    root=Path(__file__).resolve().parents[1];target=root.parent/'rca-data-workbench-v1.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for current,dirs,files in os.walk(root):
            dirs[:]=[d for d in dirs if d not in ('.venv','__pycache__','wheelhouse','private','.git')]
            for name in files:
                p=Path(current)/name
                if p.suffix not in ('.pyc','.tmp'):archive.write(p,Path(root.name)/p.relative_to(root))
    with zipfile.ZipFile(target) as archive:
        if archive.testzip():raise ValueError('Bad ZIP')
    digest=hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.zip.sha256').write_text(f'{digest}  {target.name}\n',encoding='ascii')
    print(dict(path=str(target),bytes=target.stat().st_size,sha256=digest))


if __name__=='__main__':main()
