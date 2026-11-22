FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd -m app && mkdir /data && chown app /data
USER app
ENV DATABASE=/data/studytrail.sqlite
VOLUME /data
EXPOSE 8000
# One worker: the login rate limiter keeps its counters in process memory (see ISSUES.md).
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:8000", "wsgi:app"]
