import os
import pandas as pd
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

from app.utils.logger import info, error
from app.services.db_service import db_connect, get_um_pendente, mark_finalizado
from app.services.playwright_service import baixar_excel_por_id
from app.services.data_service import tratar_df, inserir_mysql


# ============================================================
# MODELOS DE RESPOSTA
# ============================================================

class StatusResponse(BaseModel):
    status: str
    msg: str
    db: Optional[str] = None
    pendentes: Optional[int] = None
    ultimo_processamento: Optional[str] = None


class ProcessarResponse(BaseModel):
    status: str
    id: int | None = None
    titulo: str | None = None
    arquivo: str | None = None
    meta: dict | None = None
    insercao: dict | None = None
    detalhe: str | None = None
    etapa: str | None = None


# ============================================================
# APP CONFIG
# ============================================================

app = FastAPI(
    title="Relatório CLT API",
    version="1.2.0",
    description="API para automação de relatórios CLT da ConectPromotora.",
    
    license_info={"name": "Uso interno - GS Consig"}
)


# ============================================================
# ENDPOINTS
# ============================================================

@app.get("/", tags=["Status"], response_model=StatusResponse)
@app.get("/status", tags=["Status"], response_model=StatusResponse)
def root():
    """Verifica se a API está rodando + status básico do DB"""
    try:
        conn = db_connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM controle_consultas WHERE status IS NULL OR status NOT IN ('FINALIZADO','Finalizado')")
        pendentes = cur.fetchone()[0]
        cur.execute("SELECT MAX(data_criacao) FROM controle_consultas WHERE status='FINALIZADO'")
        ultimo = cur.fetchone()[0]
        cur.close(); conn.close()
        return {
            "status": "ok",
            "msg": "Relatório CLT API em execução 🚀",
            "db": "conectado",
            "pendentes": pendentes,
            "ultimo_processamento": str(ultimo) if ultimo else None
        }
    except Exception as e:
        return {"status": "erro", "msg": f"Falha ao conectar DB: {e}", "db": "falha"}


@app.get("/pendentes", tags=["Consultas"])
def listar_pendentes():
    """Lista registros pendentes de processamento"""
    conn = db_connect()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT id, titulo_consulta, banco, quantidade, data_criacao
        FROM controle_consultas
        WHERE status IS NULL OR status NOT IN ('FINALIZADO','Finalizado')
        ORDER BY id DESC
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return {"total": len(rows), "registros": rows}


@app.post("/processar", tags=["Processamento"], response_model=ProcessarResponse)
async def processar():
    """Processa o **próximo pendente** encontrado"""
    conn = db_connect()
    pendente = get_um_pendente(conn)
    if not pendente:
        return {"status": "sem_pendentes", "msg": "Nenhum registro pendente encontrado."}
    return await _executar_fluxo(conn, pendente)


@app.post("/processar/{row_id}", tags=["Processamento"], response_model=ProcessarResponse)
async def processar_por_id(row_id: int):
    """Processa um **registro específico** pelo ID"""
    conn = db_connect()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM controle_consultas WHERE id=%s", (row_id,))
    pendente = cur.fetchone()
    cur.close()
    if not pendente:
        return {"status": "erro", "msg": f"Registro {row_id} não encontrado"}
    return await _executar_fluxo(conn, pendente)


@app.get("/historico", tags=["Consultas"])
def historico():
    """Lista registros já finalizados"""
    conn = db_connect()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT id, titulo_consulta, banco, quantidade, data_criacao, status
        FROM controle_consultas
        WHERE status IN ('FINALIZADO','Finalizado')
        ORDER BY data_criacao DESC
        LIMIT 50
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return {"total": len(rows), "historico": rows}


@app.post("/reprocessar/{row_id}", tags=["Processamento"], response_model=ProcessarResponse)
async def reprocessar(row_id: int):
    """Reprocessa manualmente um registro específico"""
    conn = db_connect()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM controle_consultas WHERE id=%s", (row_id,))
    pendente = cur.fetchone()
    cur.close()
    if not pendente:
        return {"status": "erro", "msg": f"Registro {row_id} não encontrado"}
    return await _executar_fluxo(conn, pendente, reprocessar=True)


@app.get("/download/{row_id}", tags=["Arquivos"])
def download(row_id: int):
    """Retorna o arquivo Excel correspondente a um registro já processado"""
    safe_name = f"{row_id}.xlsx"
    file_path = os.path.join("downloads", safe_name)
    if not os.path.exists(file_path):
        return {"status": "erro", "msg": f"Arquivo para ID {row_id} não encontrado"}
    return FileResponse(file_path, filename=safe_name, media_type="application/vnd.ms-excel")


@app.get("/metrics", tags=["Status"])
def metrics():
    """Estatísticas gerais do processamento"""
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM controle_consultas WHERE status='FINALIZADO'")
    total_finalizados = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM controle_consultas WHERE status IS NULL OR status NOT IN ('FINALIZADO','Finalizado')")
    pendentes = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM controle_consultas WHERE status='ERRO'")
    erros = cur.fetchone()[0] if cur.description else 0
    cur.close(); conn.close()
    return {
        "total_processados": total_finalizados,
        "pendentes": pendentes,
        "falhas": erros
    }


# ============================================================
# FUNÇÃO INTERNA PARA EXECUTAR FLUXO
# ============================================================

async def _executar_fluxo(conn, pendente, reprocessar: bool = False):
    row_id = pendente["id"]
    titulo = pendente["titulo_consulta"]

    try:
        # 1) baixar excel
        path = await baixar_excel_por_id(row_id, titulo)
        if not path:
            return {"status": "erro", "etapa": "download"}

        # 2) tratar + inserir
        info("Lendo relatório com pandas...")
        df = pd.read_excel(path)
        df, meta = tratar_df(df)
        insert_result = inserir_mysql(df)

        if not insert_result.get("ok"):
            return {"status": "erro", "etapa": "inserir_mysql", "detalhe": insert_result.get("erro")}

        # 3) marcar finalizado se não for reprocessamento
        if not reprocessar:
            mark_finalizado(conn, row_id)

        return {
            "status": "ok",
            "id": row_id,
            "titulo": titulo,
            "arquivo": str(path),
            "meta": meta,
            "insercao": insert_result
        }

    except Exception as e:
        error(f"Erro no processamento: {e}")
        return {"status": "erro", "etapa": "processamento", "detalhe": str(e)}
