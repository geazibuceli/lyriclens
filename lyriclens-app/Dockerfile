FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend /app/backend
RUN pip install --no-cache-dir './backend[inference]'
ARG WITH_SEPARATION=false
RUN if [ "$WITH_SEPARATION" = "true" ]; then pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.5.1 torchaudio==2.5.1 && pip install --no-cache-dir './backend[separation]'; fi
ARG WITH_TRANSLATION=false
RUN if [ "$WITH_TRANSLATION" = "true" ]; then pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.5.1 && pip install --no-cache-dir './backend[translation]'; fi
ENV LYRICLENS_DATA=/data
RUN useradd --create-home lyriclens && mkdir /data && chown lyriclens:lyriclens /data
USER lyriclens
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "lyriclens.api:app", "--host", "0.0.0.0", "--port", "8000"]
