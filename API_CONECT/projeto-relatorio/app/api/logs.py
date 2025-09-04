from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse
import os

router = APIRouter()

LOG_PATH = os.getenv("LOG_PATH", "app/logs/processamento.log")

@router.get("/logs", response_class=PlainTextResponse)
def get_logs(lines: int = Query(100, ge=1, le=1000)):
    try:
        with open(LOG_PATH, "r") as f:
            log_lines = f.readlines()[-lines:]
        return "".join(log_lines)
    except Exception as e:
        return f"Erro ao ler o log: {str(e)}"
