from pathlib import Path
import gzip
root=Path(__file__).resolve().parents[1]
for f in (root/'legacy').rglob('*.csv.gz'):
    out=f.with_suffix('')
    if not out.exists():out.write_bytes(gzip.decompress(f.read_bytes()))
    print(out.relative_to(root))
