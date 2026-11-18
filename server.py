"""Flask API + UI.  Run: python -m app.server   (docs at /docs, UI at /)"""
import os, threading
from flask import Flask, jsonify, request
from app.trends import trends
from app.updater import Store

app = Flask(__name__, static_folder="static", static_url_path="")
store = Store(); store.start_auto()
bad = lambda m, c=400: (jsonify(error=m), c)

@app.get("/")
def home(): return app.send_static_file("index.html")

@app.get("/api/health")
def health(): return jsonify(status="ok", rows=len(store.df), latest=store.state["latest"], built_at=store.state["built_at"])

@app.get("/api/options")
def options():
    d, h = store.df, store.df[store.df.salary_basis == "hourly"].salary_value
    return jsonify(countries=d.country.value_counts().head(80).index.tolist(), keywords=store.engine.top_terms(40),
                   date_min=str(d.date.min().date()), date_max=str(d.date.max().date()),
                   hourly_range=[_r(h.quantile(.02)), _r(h.quantile(.98))] if len(h) else [0, 100])
_r = lambda v: round(float(v))

@app.post("/api/recommend")
def recommend():
    b = request.get_json(silent=True) or {}
    sk = b.get("skills", ""); sk = " ".join(sk) if isinstance(sk, list) else str(sk)
    try:
        n, div = min(max(int(b.get("n", 12)), 1), 50), min(max(float(b.get("diversity", .3)), 0), 1)
        res = store.engine.recommend(sk, str(b.get("titles", "")), b.get("liked", []), b.get("disliked", []), b.get("countries", []),
                                     b.get("pay_type", "any"), float(b.get("min_pay") or 0), int(b["max_age"]) if b.get("max_age") else None, div, n)
    except (ValueError, TypeError) as e: return bad(f"Invalid parameter: {e}")
    return jsonify(count=len(res), results=res)

@app.get("/api/similar/<job_id>")
def similar(job_id):
    if job_id not in store.engine.pos: return bad("Unknown job id", 404)
    return jsonify(results=store.engine.similar(job_id, min(int(request.args.get("n", 6)), 20)))

@app.get("/api/dashboard")
def dashboard():
    c = request.args.get("country") or None
    if c not in store.cache: store.cache[c] = trends(store.df, c)
    return jsonify(store.cache[c])

@app.get("/api/engine/metrics")
def metrics(): return jsonify(store.engine.evaluate())

@app.get("/api/update/status")
def ustatus(): return jsonify(store.status())

@app.post("/api/update/refresh")
def refresh():
    if store.running: return bad("A refresh is already running.", 409)
    threading.Thread(target=lambda: store.refresh("manual"), daemon=True).start()
    return jsonify(started=True), 202

def _get(summary, params=None):
    return {"get": {"summary": summary, "parameters": params or [], "responses": {"200": {"description": "OK"}}}}
_arr = lambda t="string": {"type": "array", "items": {"type": t}}
SPEC = {"openapi": "3.0.3", "info": {"title": "Shortlist API", "version": "1.0", "description": "Job recommendations + live market dashboard"},
        "paths": {
 "/api/recommend": {"post": {"summary": "Personalised job recommendations", "requestBody": {"content": {"application/json": {"schema": {"type": "object", "properties": {
     "skills": {**_arr(), "example": ["python", "data analysis"]}, "titles": {"type": "string", "example": "data analyst"},
     "countries": _arr(), "pay_type": {"type": "string", "enum": ["any", "hourly", "fixed"]}, "min_pay": {"type": "number"},
     "max_age": {"type": "integer", "description": "max posting age in days"}, "diversity": {"type": "number", "minimum": 0, "maximum": 1},
     "n": {"type": "integer", "default": 12}, "liked": _arr(), "disliked": _arr()}}}}}, "responses": {"200": {"description": "Ranked jobs"}, "400": {"description": "Invalid parameter"}}}},
 "/api/similar/{id}": _get("Jobs similar to one posting", [{"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}, {"name": "n", "in": "query", "schema": {"type": "integer"}}]),
 "/api/options": _get("Filter options and suggested keywords"), "/api/health": _get("Service status"),
 "/api/dashboard": _get("Market trends (KPIs, series, rising keywords)", [{"name": "country", "in": "query", "schema": {"type": "string"}}]),
 "/api/engine/metrics": _get("Offline quality of the recommender (hit-rate@10, MRR)"), "/api/update/status": _get("Auto/manual update status and history"),
 "/api/update/refresh": {"post": {"summary": "Manual refresh (rebuild data, model and trends)", "responses": {"202": {"description": "Started"}, "409": {"description": "Already running"}}}}}}

@app.get("/api/openapi.json")
def spec(): return jsonify(SPEC)

@app.get("/docs")
def docs():
    return ('<!doctype html><title>Shortlist API</title><link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">'
            '<div id="ui"></div><script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>'
            '<script>SwaggerUIBundle({url:"/api/openapi.json",dom_id:"#ui"})</script>')

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), threaded=True)
