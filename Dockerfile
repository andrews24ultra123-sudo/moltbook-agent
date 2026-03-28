FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt requirements.txt
COPY agent.py agent.py
RUN pip install --no-cache-dir -r requirements.txt
ENTRYPOINT ["python3", "-u", "agent.py"]
