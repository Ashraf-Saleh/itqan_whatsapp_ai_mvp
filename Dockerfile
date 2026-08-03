FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
# Shell form (not exec array form) so $PORT is expanded. Render injects PORT at
# runtime; 8000 is used for local `docker run` / docker-compose.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
