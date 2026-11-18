"""Load + clean raw job postings (same logic as the notebook). New monthly files go in data/incoming/."""
import hashlib, re
from pathlib import Path
import numpy as np, pandas as pd

RAW, INCOMING = Path("data/raw"), Path("data/incoming")
COLS = {"title": "title", "date": "published_date", "link": "link", "hourly_low": "hourly_low",
        "hourly_high": "hourly_high", "budget": "budget", "country": "country"}   # canonical -> YOUR column

_norm = lambda c: re.sub(r"[^a-z0-9]+", "_", str(c).lower()).strip("_")
_num = lambda s: pd.to_numeric(s.astype(str).str.replace(r"[^0-9.]", "", regex=True).replace("", np.nan), errors="coerce")

def clean(raw):
    raw = raw.copy(); raw.columns = [_norm(c) for c in raw.columns]
    df = raw.rename(columns={_norm(v): k for k, v in COLS.items()})
    for c in ("link", "country", "hourly_low", "hourly_high", "budget"):
        if c not in df: df[c] = np.nan
    df["title_raw"] = df["title"].astype(str).str.strip()
    df["title_clean"] = (df.title_raw.str.lower().str.replace(r"[^a-z0-9+# ]+", " ", regex=True)
                         .str.replace(r"\s+", " ", regex=True).str.strip())
    df["date"] = pd.to_datetime(df["date"], errors="coerce", utc=True, format="mixed").dt.tz_localize(None)
    df = df[(df.title_clean.str.len() > 1) & df.date.notna()].copy()
    for c in ("hourly_low", "hourly_high", "budget"): df[c] = _num(df[c])
    mid = df[["hourly_low", "hourly_high"]].mean(axis=1)
    df["salary_value"] = np.where(mid > 0, mid, np.where(df.budget > 0, df.budget, np.nan))
    df["salary_basis"] = np.where(mid > 0, "hourly", np.where(df.budget > 0, "fixed", None))
    df["country"] = df.country.astype(str).str.strip().str.title().replace({"Nan": np.nan})
    key = df.title_raw + df.date.astype(str) + df.link.astype(str)
    df["id"] = key.map(lambda k: hashlib.md5(k.encode()).hexdigest()[:10])
    return df.drop_duplicates("id").reset_index(drop=True)

def load_all():
    files = sorted(RAW.glob("*.csv")) + sorted(INCOMING.glob("*.csv"))
    if not files: raise FileNotFoundError("Put your CSV in data/raw/ (new monthly files go in data/incoming/).")
    return clean(pd.concat([pd.read_csv(f, low_memory=False) for f in files], ignore_index=True)), len(files)
