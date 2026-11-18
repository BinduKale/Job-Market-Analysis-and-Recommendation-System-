FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
ENV PORT=5000 AUTO_REFRESH=1 CHECK_SECS=3600
EXPOSE 5000
# one worker: it owns the in-memory model and the auto-update thread
CMD ["gunicorn", "-w", "1", "--threads", "4", "--timeout", "300", "-b", "0.0.0.0:5000", "app.server:app"]
