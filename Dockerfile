FROM python:3.10-slim
WORKDIR /app

# install deps
RUN pip install --no-cache-dir prometheus_client requests

# copy in our exporter
COPY exporter.py /app/exporter.py

# run it
CMD ["python", "exporter.py"]

