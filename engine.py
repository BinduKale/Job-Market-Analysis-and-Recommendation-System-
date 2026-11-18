"""Content-based recommender: TF-IDF + latent (SVD) similarity, Rocchio feedback, filters, recency, MMR diversity."""
import numpy as np, scipy.sparse as sp
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.preprocessing import normalize

STOP = list(ENGLISH_STOP_WORDS | {"need", "needed", "wanted", "looking", "urgent", "hiring", "expert", "required", "project", "job"})
TP = r"[a-z0-9][a-z0-9+#]+"

class Recommender:
    def __init__(s, df):
        s.df = df.reset_index(drop=True)
        s.tf = TfidfVectorizer(stop_words=STOP, ngram_range=(1, 2), min_df=2, sublinear_tf=True, token_pattern=TP)
        s.X = s.tf.fit_transform(s.df.title_clean)
        s.svd = TruncatedSVD(max(2, min(64, s.X.shape[1] - 1)), random_state=0)
        s.Z = normalize(s.svd.fit_transform(s.X))
        s.age = (s.df.date.max() - s.df.date).dt.days.values
        s.pos = {i: n for n, i in enumerate(s.df.id)}
        s.an, s._metrics = s.tf.build_analyzer(), None

    def top_terms(s, n=40):
        w, t = np.asarray(s.X.sum(axis=0)).ravel(), s.tf.get_feature_names_out()
        return [t[i] for i in np.argsort(-w) if " " not in t[i]][:n]

    def _rel(s, text, liked=(), disliked=()):
        q = s.tf.transform([text])
        for ids, w in ((liked, .6), (disliked, -.4)):              # Rocchio relevance feedback
            idx = [s.pos[i] for i in ids if i in s.pos]
            if idx: q = q + w * sp.csr_matrix(s.X[idx].mean(axis=0))
        q = normalize(q)
        lat = s.Z @ normalize(s.svd.transform(q)).T
        return np.clip(.65 * (s.X @ q.T).toarray().ravel() + .35 * np.asarray(lat).ravel(), 0, None)

    def recommend(s, skills="", titles="", liked=(), disliked=(), countries=(), pay_type="any", min_pay=0,
                  max_age=None, diversity=.3, n=12, exclude=()):
        text = f"{skills} {titles} {titles}".strip()
        rel, d = s._rel(text, liked, disliked), s.df
        fresh = np.exp(-s.age / 30)
        score = .88 * rel + .12 * fresh if rel.max() > 0 else fresh      # no profile yet -> trending/recent
        m = np.ones(len(d), bool)
        if countries: m &= d.country.isin(countries).values
        if pay_type != "any":
            m &= (d.salary_basis == pay_type).values
            if min_pay: m &= (d.salary_value >= min_pay).values
        if max_age: m &= s.age <= max_age
        for i in exclude:
            if i in s.pos: m[s.pos[i]] = False
        score = np.where(m, score, -1)
        seen, keep = set(), []
        for c in np.argsort(-score)[:300]:
            if score[c] > 0 and d.title_clean.iat[c] not in seen: seen.add(d.title_clean.iat[c]); keep.append(c)
        cand, chosen = np.array(keep, int), []
        if len(cand):
            S, left = s.Z[cand] @ s.Z[cand].T, list(range(len(cand)))
            while left and len(chosen) < n:                               # MMR: relevance vs. diversity
                j = left[0] if not chosen else max(left, key=lambda a: (1 - diversity) * score[cand[a]] - diversity * S[a, chosen].max())
                chosen.append(j); left.remove(j)
        top, qa = max([score[cand[j]] for j in chosen] or [1]), set(s.an(text))
        return [s._card(cand[j], score[cand[j]] / top, qa) for j in chosen]

    def similar(s, job_id, n=6):
        return s.recommend(liked=[job_id], exclude=[job_id], diversity=.2, n=n)

    def _card(s, i, rel, qa):
        r = s.df.iloc[i]
        if r.salary_basis == "hourly":
            lo, hi = r.hourly_low, r.hourly_high
            pay = f"${lo:g}–${hi:g}/hr" if lo == lo and hi == hi and lo != hi else f"${r.salary_value:g}/hr"
        else: pay = f"${r.salary_value:,.0f} fixed" if r.salary_basis == "fixed" else "Not stated"
        return {"id": r.id, "title": r.title_raw, "link": r.link if isinstance(r.link, str) else None,
                "country": r.country if isinstance(r.country, str) else None, "posted": str(r.date.date()),
                "pay": pay, "basis": r.salary_basis, "match": int(min(99, round(rel * 100))),
                "why": [t for t in dict.fromkeys(r.title_clean.split()) if t in qa][:4]}

    def evaluate(s, n=300, k=10, seed=0):
        """Masked-title test: query with the first half of a posting's title; is the full title in the top-k?"""
        if s._metrics: return s._metrics
        rng, hits, rr, cnt = np.random.default_rng(seed), 0, 0., 0
        for i in rng.choice(len(s.df), min(n, len(s.df)), replace=False):
            w = s.df.title_clean.iat[i].split()
            if len(w) < 3: continue
            order = np.argsort(-s._rel(" ".join(w[:len(w) // 2])))[:2000]
            uniq, t = list(dict.fromkeys(s.df.title_clean.values[order])), s.df.title_clean.iat[i]
            cnt += 1; rank = uniq.index(t) + 1 if t in uniq else None
            hits += bool(rank and rank <= k); rr += 1 / rank if rank else 0
        s._metrics = {"queries": cnt, f"hit_rate_at_{k}": round(hits / max(cnt, 1), 3), "mrr": round(rr / max(cnt, 1), 3)}
        return s._metrics
