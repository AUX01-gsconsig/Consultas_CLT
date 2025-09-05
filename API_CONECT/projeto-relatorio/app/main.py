import os
import re
import pandas as pd
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.openapi.utils import get_openapi

from app.utils.logger import info, error
from app.services.db_service import db_connect, get_um_pendente, mark_finalizado
from app.services.playwright_service import baixar_excel_por_id
from app.services.data_service import tratar_df, inserir_mysql
from app.api.logs import router as logs_router
from app.auth.dependencies import get_current_user


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
    observacao: str | None = None
    tentativas: int | None = None
    tentativas_limite: bool | None = None


# ============================================================
# APP CONFIG
# ============================================================

app = FastAPI(
    title="Relatório CLT API",
    version="1.2.0",
    description="API para automação de relatórios CLT da ConectPromotora.",
    license_info={"name": "Uso interno - GS Consig"}
)

app.include_router(logs_router)


# ============================================================
# PROTEGENDO DOCS COM LOGIN
# ============================================================

@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui(user=Depends(get_current_user)):
    return get_swagger_ui_html(openapi_url=app.openapi_url, title=app.title + " - Docs")


@app.get("/redoc", include_in_schema=False)
async def custom_redoc(user=Depends(get_current_user)):
    return get_redoc_html(openapi_url=app.openapi_url, title=app.title + " - ReDoc")


@app.get("/openapi.json", include_in_schema=False)
async def custom_openapi(user=Depends(get_current_user)):
    return get_openapi(title=app.title, version=app.version, routes=app.routes)


# ============================================================
# ENDPOINTS (TODOS EXIGEM LOGIN)
# ============================================================

@app.get("/", tags=["Status"], response_model=StatusResponse)
@app.get("/status", tags=["Status"], response_model=StatusResponse)
def root(user=Depends(get_current_user)):
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
def listar_pendentes(user=Depends(get_current_user)):
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
async def processar(user=Depends(get_current_user)):
    """Processa o **próximo pendente** encontrado"""
    conn = db_connect()
    pendente = get_um_pendente(conn)
    if not pendente:
        return {"status": "sem_pendentes", "msg": "Nenhum registro pendente encontrado."}
    return await _executar_fluxo(conn, pendente)


@app.post("/processar/{row_id}", tags=["Processamento"], response_model=ProcessarResponse)
async def processar_por_id(row_id: int, user=Depends(get_current_user)):
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
def historico(user=Depends(get_current_user)):
    """Lista registros já finalizados"""
    conn = db_connect()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT id, titulo_consulta, banco, quantidade, data_criacao, status, observacao
        FROM controle_consultas
        WHERE status IN ('FINALIZADO','Finalizado')
        ORDER BY data_criacao DESC
        LIMIT 50
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return {"total": len(rows), "historico": rows}


@app.post("/reprocessar/{row_id}", tags=["Processamento"], response_model=ProcessarResponse)
async def reprocessar(row_id: int, user=Depends(get_current_user)):
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
def download(row_id: int, user=Depends(get_current_user)):
    """Retorna o arquivo Excel correspondente a um registro já processado"""
    safe_name = f"{row_id}.xlsx"
    file_path = os.path.join("downloads", safe_name)
    if not os.path.exists(file_path):
        return {"status": "erro", "msg": f"Arquivo para ID {row_id} não encontrado"}
    return FileResponse(file_path, filename=safe_name, media_type="application/vnd.ms-excel")


@app.get("/metrics", tags=["Status"])
def metrics(user=Depends(get_current_user)):
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

def mark_erro(conn, row_id, etapa, detalhe, limite_tentativas=3):
    cur = conn.cursor()
    cur.execute("SELECT observacao FROM controle_consultas WHERE id=%s", (row_id,))
    obs = cur.fetchone()[0] or ""
    match = re.search(r"tentativas=(\d+)", obs)
    tentativas = int(match.group(1)) if match else 0
    tentativas += 1

    nova_obs = f"tentativas={tentativas} | {etapa}: {detalhe}"
    cur.execute("""
        UPDATE controle_consultas
        SET status='ERRO', observacao=%s
        WHERE id=%s
    """, (nova_obs, row_id))
    conn.commit()
    cur.close()
    return tentativas >= limite_tentativas, tentativas


async def _executar_fluxo(conn, pendente, reprocessar: bool = False, limite_tentativas=3):
    row_id = pendente["id"]
    titulo = pendente["titulo_consulta"]
    try:
        # 1) baixar excel
        path = await baixar_excel_por_id(row_id, titulo)
        if not path:
            limite, tentativas = mark_erro(conn, row_id, "download", "Falha ao baixar arquivo", limite_tentativas)
            msg = f"Falha ao baixar arquivo (tentativas={tentativas})"
            if limite:
                msg += " | Limite de tentativas atingido."
            return {
                "status": "erro",
                "etapa": "download",
                "detalhe": msg,
                "tentativas": tentativas,
                "tentativas_limite": limite
            }

        # 2) tratar + inserir
        info("Lendo relatório com pandas...")
        df = pd.read_excel(path)
        df, meta = tratar_df(df)
        insert_result = inserir_mysql(df)
        if not insert_result.get("ok"):
            limite, tentativas = mark_erro(conn, row_id, "inserir_mysql", insert_result.get("erro"), limite_tentativas)
            msg = f"{insert_result.get('erro')} (tentativas={tentativas})"
            if limite:
                msg += " | Limite de tentativas atingido."
            return {
                "status": "erro",
                "etapa": "inserir_mysql",
                "detalhe": msg,
                "tentativas": tentativas,
                "tentativas_limite": limite
            }

        # 3) marcar finalizado se não for reprocessamento
        if not reprocessar:
            cur = conn.cursor()
            cur.execute("SELECT observacao FROM controle_consultas WHERE id=%s", (row_id,))
            obs = cur.fetchone()[0] or ""
            match = re.search(r"tentativas=(\d+)", obs)
            tentativas = int(match.group(1)) if match else 0
            cur.execute("""
                UPDATE controle_consultas
                SET status='FINALIZADO', observacao=%s
                WHERE id=%s
            """, (f"SUCESSO após {tentativas} tentativas", row_id))
            conn.commit()
            cur.close()

        return {
            "status": "ok",
            "id": row_id,
            "titulo": titulo,
            "arquivo": str(path),
            "meta": meta,
            "insercao": insert_result,
            "observacao": f"SUCESSO após {tentativas} tentativas",
            "tentativas": tentativas
        }

    except Exception as e:
        limite, tentativas = mark_erro(conn, row_id, "processamento", str(e), limite_tentativas)
        msg = f"{str(e)} (tentativas={tentativas})"
        if limite:
            msg += " | Limite de tentativas atingido."
        error(f"Erro no processamento: {msg}")
        return {
            "status": "erro",
            "etapa": "processamento",
            "detalhe": msg,
            "tentativas": tentativas,
            "tentativas_limite": limite
        }
