FROM python:3.12-slim
WORKDIR /app
COPY server.py .
# No third-party dependencies: stdlib only
ENV HOST=0.0.0.0
EXPOSE 8000
CMD ["python3", "server.py"]
