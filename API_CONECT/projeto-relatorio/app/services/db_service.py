import os
import mysql.connector
from typing import Optional, Dict
from app.utils.logger import ProcessLogger

def db_connect(logger: ProcessLogger = None):
    host = os.getenv("DB_HOST")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    database = os.getenv("DB_NAME")

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

def get_um_pendente(conn, logger: ProcessLogger = None) -> Optional[Dict]:
    if logger:
        logger.db("Buscando 1 registro pendente no controle_consultas...")
    else:
        print("[DB] Buscando 1 registro pendente no controle_consultas...")
        
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT id, titulo_consulta, banco, quantidade, data_criacao, status
        FROM controle_consultas
        WHERE status IS NULL OR status NOT IN ('Finalizado','FINALIZADO')
        ORDER BY id DESC
        LIMIT 1
    """)
    row = cur.fetchone()
    cur.close()

    if row:
        if logger:
            logger.success(f"Registro encontrado → ID={row['id']} | Titulo={row['titulo_consulta']} | Banco={row.get('banco')} | Qtd={row.get('quantidade')}")
        else:
            print(f"[SUCCESS] Registro encontrado → ID={row['id']} | Titulo={row['titulo_consulta']} | Banco={row.get('banco')} | Qtd={row.get('quantidade')}")
    else:
        if logger:
            logger.warning("Nenhum registro pendente encontrado.")
        else:
            print("[WARNING] Nenhum registro pendente encontrado.")

    return row

def mark_finalizado(conn, row_id: int, logger: ProcessLogger = None):
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
