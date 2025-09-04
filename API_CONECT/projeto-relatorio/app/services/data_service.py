import os
import re
import pandas as pd
import numpy as np
import mysql.connector
from typing import Dict, Any, Tuple, List
from app.utils.logger import ProcessLogger

DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

EXPECTED_COLS = [
    'lote','cpf','matricula','nome','nascimento','data_admissao',
    'renda','valor_base_margem','valor_margem_disponivel','valor_parcela_clt',
    'cnpj_empresa','elegivel_clt','cnae','erro_simulacao','data_criacao',
    'data_modificacao','categoria_trabalhador','sexo','nome_empregador',
    'nome_mae','profissao','cnae_descricao','emprestimos_legados',
    'emprestimos_ativos_suspensos','banco_clt','prazo_maximo_clt',
    'valor_liberado_clt','plataforma_id','manychat_id','disparo_lote',
    'manychat_key','simulado'
]

RENAME_MAP = {
    'Lote': 'lote','CPF': 'cpf','Matrícula': 'matricula','Nome': 'nome',
    'Data Nascimento': 'nascimento','Data Admissão': 'data_admissao',
    'Valor Renda': 'renda','Valor Base Margem': 'valor_base_margem',
    'Valor Margem Disponível': 'valor_margem_disponivel',
    'Valor Máximo Prestação': 'valor_parcela_clt','CNPJ Empresa': 'cnpj_empresa',
    'Elegível': 'elegivel_clt','CNAE': 'cnae','Erro': 'erro_simulacao',
    'Data Criação': 'data_criacao','Data Modificação': 'data_modificacao',
    'Código Categoria Trabalhador': 'categoria_trabalhador','Sexo': 'sexo',
    'Nome Empregador': 'nome_empregador','Nome Mãe': 'nome_mae',
    'CBO Descrição': 'profissao','CNAE Descrição': 'cnae_descricao',
    'Empréstimos Legados': 'emprestimos_legados',
    'Qtd Empréstimos Ativos Suspensos': 'emprestimos_ativos_suspensos',
    'Prazo Máximo': 'prazo_maximo_clt','Valor Liberado': 'valor_liberado_clt'
}

DECIMAL_LIMIT = 99999999.99
DECIMAL_COLS = ['renda','valor_base_margem','valor_margem_disponivel','valor_parcela_clt','valor_liberado_clt']

def erro_retorno(id_consulta, titulo, etapa, mensagem):
    return {
        "id": id_consulta,
        "titulo": titulo,
        "etapa": etapa,
        "mensagem": mensagem
    }

def tratar_df(df: pd.DataFrame, logger: ProcessLogger = None, id_consulta=None) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    try:
        if logger:
            logger.data("Ajustando colunas e limpando dados...")
        else:
            print("[DATA] Ajustando colunas e limpando dados...")
            
        original = len(df)

        # renomear
        df = df.rename(columns=RENAME_MAP)

        # garantir todas as colunas esperadas
        for col in EXPECTED_COLS:
            if col not in df.columns:
                df[col] = None
        df = df[EXPECTED_COLS]

        # CPF: apenas dígitos + zero-pad
        if 'cpf' in df.columns:
            df['cpf'] = (
                df['cpf'].astype(str)
                .str.replace(r'\D', '', regex=True)
                .str.zfill(11)
                .where(lambda s: s != '00000000000', np.nan)
            )
            # Excluir linhas onde CPF é nulo, vazio, 'nan', 'none', etc.
            df = df[df['cpf'].notnull() & (df['cpf'] != '') & (df['cpf'].str.lower() != 'nan') & (df['cpf'].str.lower() != 'none')]

        # datas
        for col in ['nascimento','data_admissao','data_criacao','data_modificacao']:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce', dayfirst=True).dt.date

        # booleanos → 1/0
        if 'elegivel_clt' in df.columns:
            df['elegivel_clt'] = df['elegivel_clt'].map({True:1, False:0, 'True':1, 'False':0})

        # numéricos decimais seguros
        for col in DECIMAL_COLS:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                df.loc[df[col].abs() > DECIMAL_LIMIT, col] = None

        # strings vazias -> None
        for col in df.columns:
            if df[col].dtype == 'O':
                df[col] = df[col].replace({'': None, 'nan': None, 'NaN': None, 'None': None})

        # deduplicar por CPF (mantém a última)
        antes = len(df)
        df = df.drop_duplicates(subset=['cpf'], keep='last')
        dedup = antes - len(df)
        if dedup > 0:
            if logger:
                logger.warning(f"Removidos {dedup} CPFs duplicados (de {antes} → {len(df)})")
            else:
                print(f"[WARNING] Removidos {dedup} CPFs duplicados (de {antes} → {len(df)})")

        # todos NaN/NaT → None
        df = df.astype(object).where(pd.notna(df), None)

        if logger:
            logger.success(f"Excel: {original} linhas | Após tratamento: {len(df)} linhas")
        else:
            print(f"[SUCCESS] Excel: {original} linhas | Após tratamento: {len(df)} linhas")
            
        return df, {"linhas_excel": original, "linhas_tratadas": len(df), "cpfs_dedup": dedup}
    except FileNotFoundError as e:
        return erro_retorno(id_consulta, "Arquivo não encontrado", "tratamento_dados", str(e)), {}
    except pd.errors.EmptyDataError as e:
        return erro_retorno(id_consulta, "Arquivo vazio ou corrompido", "tratamento_dados", str(e)), {}
    except Exception as e:
        return erro_retorno(id_consulta, "Erro no processo de tratamento", "tratamento_dados", str(e)), {}

def inserir_mysql(df: pd.DataFrame, logger: ProcessLogger = None, id_consulta=None) -> Dict[str, Any]:
    if logger:
        logger.db("Preparando inserção no MySQL...")
    else:
        print("[DB] Preparando inserção no MySQL...")
    
    try:
        conn = mysql.connector.connect(
            host=DB_HOST, database=DB_NAME,
            user=DB_USER, password=DB_PASS,
            charset='utf8mb4', collation='utf8mb4_unicode_ci'
        )
        cur = conn.cursor()

        colunas = list(df.columns)
        placeholders = ','.join(['%s']*len(colunas))
        colunas_str = ','.join([f'`{c}`' for c in colunas])
        updates = ','.join([f"`{c}`=VALUES(`{c}`)" for c in colunas if c != 'cpf'])

        sql = f"""
        INSERT INTO consulta_dia_clt ({colunas_str})
        VALUES ({placeholders})
        ON DUPLICATE KEY UPDATE {updates}
        """

        # métricas de novos / existentes
        cpfs = [str(x) for x in df['cpf'].tolist() if x]
        existentes = set()
        if cpfs:
            placeholders_in = ",".join(["%s"] * len(cpfs))
            cur.execute(f"SELECT cpf FROM consulta_dia_clt WHERE cpf IN ({placeholders_in})", cpfs)
            existentes = {row[0] for row in cur.fetchall()}

        vals = [tuple(row[c] for c in colunas) for _, row in df.iterrows()]
        cur.executemany(sql, vals)
        conn.commit()
        rowcount = cur.rowcount

        novos = len([c for c in cpfs if c not in existentes])
        atualizados = len(cpfs) - novos

        if logger:
            logger.success(f"Inseridos/Atualizados com sucesso. Enviados: {len(df)} | novos: {novos} | atualizados: {atualizados}")
        else:
            print(f"[SUCCESS] Inseridos/Atualizados com sucesso. Enviados: {len(df)} | novos: {novos} | atualizados: {atualizados}")
            
        cur.close(); conn.close()
        return {"enviados": len(df), "ok": True}
    except mysql.connector.Error as e:
        return erro_retorno(id_consulta, "Erro na conexão ou inserção de dados", "insercao_dados", str(e))
    except Exception as e:
        return erro_retorno(id_consulta, "Erro inesperado na inserção de dados", "insercao_dados", str(e))
