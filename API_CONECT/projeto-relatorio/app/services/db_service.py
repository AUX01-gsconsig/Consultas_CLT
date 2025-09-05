import os
import re
import mysql.connector
from typing import Optional, Dict
from app.utils.logger import ProcessLogger

def erro_db_retorno(id_consulta, titulo, etapa, mensagem):
    return {
        "id": id_consulta,
        "titulo": titulo,
        "etapa": etapa,
        "mensagem": mensagem
    }

def db_connect(logger: ProcessLogger = None, id_consulta=None):
    host = os.getenv("DB_HOST")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    database = os.getenv("DB_NAME")
    try:
        if logger:
            logger.db(f"Conectando ao banco {database}@{host} com usuário {user}")
            if not password:
                logger.warning("DB_PASSWORD não definido ou vazio!")
        else:
            print(f"[DB] Conectando ao banco {database}@{host} com usuário {user}")
        return mysql.connector.connect(
            host=host,
            user=user,
            password=password,
            database=database,
            autocommit=True
        )
    except mysql.connector.errors.InterfaceError as e:
        return erro_db_retorno(id_consulta, "Falha ao conectar ao banco de dados", "db_connect", str(e))
    except mysql.connector.errors.ProgrammingError as e:
        return erro_db_retorno(id_consulta, "Erro de autenticação ou banco/tabela não encontrada", "db_connect", str(e))
    except mysql.connector.errors.DatabaseError as e:
        return erro_db_retorno(id_consulta, "Erro de banco de dados", "db_connect", str(e))
    except Exception as e:
        return erro_db_retorno(id_consulta, "Timeout ou erro inesperado na conexão", "db_connect", str(e))

def get_um_pendente(conn, logger: ProcessLogger = None, id_consulta=None, limite_tentativas: int = 3) -> Optional[Dict]:
    try:
        if logger:
            logger.db("Buscando 1 registro pendente no controle_consultas...")
        else:
            print("[DB] Buscando 1 registro pendente no controle_consultas...")

        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT *
            FROM controle_consultas
            WHERE status IS NULL OR status NOT IN ('Finalizado','FINALIZADO')
            ORDER BY id ASC
        """)
        rows = cur.fetchall()
        cur.close()

        # aplica controle de tentativas
        for row in rows:
            obs = row.get("observacao") or ""
            match = re.search(r"tentativas=(\d+)", obs)
            tentativas = int(match.group(1)) if match else 0
            if tentativas < limite_tentativas:
                return row
        return None

    except mysql.connector.errors.ProgrammingError as e:
        return erro_db_retorno(id_consulta, "Erro de consulta SQL", "get_um_pendente", str(e))
    except mysql.connector.errors.DatabaseError as e:
        return erro_db_retorno(id_consulta, "Banco/tabela não encontrada ou permissão insuficiente", "get_um_pendente", str(e))
    except Exception as e:
        return erro_db_retorno(id_consulta, "Erro ao executar consulta ou fechar cursor", "get_um_pendente", str(e))

def mark_finalizado(conn, row_id: int, logger: ProcessLogger = None):
    try:
        if logger:
            logger.db(f"Marcando registro {row_id} como FINALIZADO...")
        else:
            print(f"[DB] Marcando registro {row_id} como FINALIZADO...")
        cur = conn.cursor()
        cur.execute("UPDATE controle_consultas SET status='FINALIZADO' WHERE id=%s", (row_id,))
        conn.commit()
        cur.close()
        if logger:
            logger.success("Status atualizado para FINALIZADO.")
        else:
            print("[SUCCESS] Status atualizado para FINALIZADO.")
    except mysql.connector.errors.ProgrammingError as e:
        return erro_db_retorno(row_id, "Erro de consulta SQL ao atualizar status", "mark_finalizado", str(e))
    except mysql.connector.errors.DatabaseError as e:
        return erro_db_retorno(row_id, "Banco/tabela não encontrada ou permissão insuficiente", "mark_finalizado", str(e))
    except Exception as e:
        return erro_db_retorno(row_id, "Erro ao executar update ou fechar cursor", "mark_finalizado", str(e))
