import csv
from pathlib import Path
from datetime import datetime
import pandas as pd

def ensure_output_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p

def export_rows(rows, columns, out_dir: str | Path, base_name: str):
    out = ensure_output_dir(out_dir)
    date = datetime.now().strftime("%Y-%m-%d")
    base = f"{base_name}_{date}"
    csv_f = out / f"{base}.csv"
    xlsx_f = out / f"{base}.xlsx"

    with csv_f.open('w', newline='', encoding='utf-8') as f:
        csv.writer(f, delimiter=';').writerows([columns, *rows])

    pd.DataFrame(rows, columns=columns).to_excel(xlsx_f, index=False)
    return csv_f, xlsx_f
