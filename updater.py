"""Live store + refresh logic. AUTOMATIC: background thread rebuilds on new files / new month.
MANUAL: Store.refresh('manual') via the dashboard button, POST /api/update/refresh, or `python -m app.updater`."""
import hashlib, json, os, threading, time, urllib.request
from datetime import datetime
from pathlib import Path
from app import data
from app.engine import Recommender

STATE_F = Path("data/state/state.json")
CHECK_SECS = int(os.getenv("CHECK_SECS", 3600))        # how often the auto-updater looks for changes
AUTO = os.getenv("AUTO_REFRESH", "1") == "1"
SOURCE_URL = os.getenv("SOURCE_URL", "")               # optional: CSV URL downloaded at each monthly rebuild

class Store:
    def __init__(s):
        s.lock, s.running, s.engine, s.df, s.cache, s.next_check = threading.Lock(), False, None, None, {}, None
        s.state = json.loads(STATE_F.read_text()) if STATE_F.exists() else {"history": []}
        s.refresh("startup")

    def _fp(s):
        files = sorted([*data.RAW.glob("*.csv"), *data.INCOMING.glob("*.csv")])
        return hashlib.md5("|".join(f"{f}{f.stat().st_mtime}{f.stat().st_size}" for f in files).encode()).hexdigest()

    def refresh(s, reason="manual"):
        if not s.lock.acquire(blocking=False): return False
        s.running = True
        try:
            t0 = time.time()
            if SOURCE_URL and reason == "auto: monthly rebuild":
                data.INCOMING.mkdir(parents=True, exist_ok=True)
                urllib.request.urlretrieve(SOURCE_URL, data.INCOMING / f"auto_{datetime.now():%Y_%m}.csv")
            df, n_files = data.load_all()
            before = len(s.df) if s.df is not None else None
            s.engine, s.df, s.cache = Recommender(df), df, {}
            now = datetime.now()
            s.state.update(fp=s._fp(), built_month=f"{now:%Y-%m}", built_at=now.isoformat(timespec="seconds"),
                           rows=len(df), files=n_files, latest=str(df.date.max().date()), last_error=None)
            s.state["history"] = ([{"at": s.state["built_at"], "reason": reason, "rows": len(df),
                                    "new_rows": None if before is None else len(df) - before, "secs": round(time.time() - t0, 1)}]
                                  + s.state["history"])[:10]
            STATE_F.parent.mkdir(parents=True, exist_ok=True); STATE_F.write_text(json.dumps(s.state))
            return True
        except Exception as e:
            s.state["last_error"] = str(e); raise
        finally:
            s.running = False; s.lock.release()

    def _loop(s):
        while True:
            s.next_check = time.time() + CHECK_SECS; time.sleep(CHECK_SECS)
            try:
                if s._fp() != s.state.get("fp"): s.refresh("auto: new data detected")
                elif f"{datetime.now():%Y-%m}" != s.state.get("built_month"): s.refresh("auto: monthly rebuild")
            except Exception as e: s.state["last_error"] = str(e)

    def start_auto(s):
        if AUTO: threading.Thread(target=s._loop, daemon=True).start()

    def status(s):
        return {**{k: v for k, v in s.state.items() if k != "fp"}, "running": s.running, "auto": AUTO,
                "check_every_secs": CHECK_SECS, "next_check_in_secs": max(0, int(s.next_check - time.time())) if s.next_check else None}

if __name__ == "__main__":                              # manual run from a terminal / cron / CI
    st = Store(); print("Rebuilt:", st.status())
