FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY legifrance_mcp ./legifrance_mcp
ENV PORT=8000
CMD ["python", "-m", "legifrance_mcp.server"]
