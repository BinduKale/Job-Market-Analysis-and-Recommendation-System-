"""Dashboard metrics: per-period series, KPIs (vs previous period), top countries, rising/falling title keywords."""
import numpy as np, pandas as pd
from sklearn.feature_extraction.text import CountVectorizer
from app.engine import STOP, TP

_f = lambda x: None if x is None or pd.isna(x) or np.isinf(x) else round(float(x), 2)
_chg = lambda a, b: _f((a / b - 1) * 100) if b and not pd.isna(a) and not pd.isna(b) else None

def trends(df, country=None):
    d = df[df.country == country] if country else df
    if len(d) < 50: return {"error": "Not enough postings for this selection."}
    span = (d.date.max() - d.date.min()).days
    f = "M" if span >= 150 else "W" if span >= 49 else "D"             # month / week / day buckets
    d = d.assign(p=d.date.dt.to_period(f).dt.start_time, h=(d.salary_basis == "hourly") * 100.0)
    idx = sorted(d.p.unique()); last = idx[-1]
    partial = f != "D" and d.date.max() < pd.Period(last, f).end_time.normalize() - pd.Timedelta(days=3 if f == "M" else 1)
    g = d.groupby("p")
    s = pd.DataFrame({"postings": g.size(), "median_hourly": d[d.salary_basis == "hourly"].groupby("p").salary_value.median(),
                      "median_fixed": d[d.salary_basis == "fixed"].groupby("p").salary_value.median(),
                      "hourly_share": g.h.mean(), "countries": g.country.nunique()}).reindex(idx)
    ci = len(idx) - 2 if partial and len(idx) > 2 else len(idx) - 1      # last COMPLETE period
    cur, prev = idx[ci], (idx[ci - 1] if ci > 0 else None)
    kp = lambda c: {"value": _f(s[c].iloc[ci]), "change_pct": _chg(s[c].iloc[ci], s[c].iloc[ci - 1]) if prev is not None else None}
    cc, pc = d[d.p == cur].country.value_counts().head(8), (d[d.p == prev].country.value_counts() if prev is not None else {})
    top = [{"country": c, "postings": int(n), "change_pct": _chg(n, pc[c]) if c in pc else None} for c, n in cc.items()]
    rising = falling = []
    if prev is not None:
        cv = CountVectorizer(stop_words=STOP, token_pattern=TP, binary=True, min_df=5)
        X, t = cv.fit_transform(d.title_clean), cv.get_feature_names_out()
        ic, ip = (d.p == cur).values, (d.p == prev).values
        nc, npv = np.asarray(X[ic].sum(0)).ravel(), np.asarray(X[ip].sum(0)).ravel()
        lift = (nc / ic.sum() * 100 + .05) / (npv / ip.sum() * 100 + .05)
        ok, order = nc >= max(10, .002 * ic.sum()), np.argsort(-lift)
        row = lambda i: {"term": t[i], "now": int(nc[i]), "prev": int(npv[i]), "lift": _f(lift[i])}
        rising, falling = [row(i) for i in order if ok[i]][:10], [row(i) for i in order[::-1] if ok[i]][:10]
    fmt = "%b %Y" if f == "M" else "%d %b"
    return {"meta": {"granularity": {"M": "month", "W": "week", "D": "day"}[f], "current": cur.strftime(fmt),
                     "previous": prev.strftime(fmt) if prev is not None else None, "partial_last": bool(partial),
                     "rows": int(len(d)), "country": country},
            "kpis": {c: kp(c) for c in ("postings", "median_hourly", "hourly_share", "countries")},
            "series": {"x": [i.strftime(fmt) for i in idx], **{c: [_f(v) for v in s[c]] for c in s.columns}},
            "top_countries": top, "rising": rising, "falling": falling}
