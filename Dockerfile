FROM python:3.12-slim

WORKDIR /processor

COPY processor/ /processor/processor/

ENV PYTHONPATH="/processor"

CMD ["python3", "-m", "processor.main"]
