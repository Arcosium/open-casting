FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=10000
WORKDIR /srv/app
RUN useradd --create-home --uid 10001 casting
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=casting:casting app ./app
COPY --chown=casting:casting tests ./tests
COPY pytest.ini .
USER casting
EXPOSE 10000
CMD ["python", "-m", "app.serve"]
