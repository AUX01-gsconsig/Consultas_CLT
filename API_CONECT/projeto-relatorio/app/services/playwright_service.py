import os
import re
import asyncio
from pathlib import Path
from typing import Optional
from playwright.async_api import async_playwright, Page
from app.utils.logger import ProcessLogger

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "./downloads"))
OUTPUT_DIR.mkdir(exist_ok=True)

SITE_USER = os.getenv("SITE_USER")
SITE_PASS = os.getenv("SITE_PASS")
HEADLESS = os.getenv("HEADLESS", "true").lower() in ("1","true","yes","y")

def erro_playwright_retorno(id_consulta, titulo, etapa, mensagem):
    return {
        "id": id_consulta,
        "titulo": titulo,
        "etapa": etapa,
        "mensagem": mensagem
    }

async def wait_for_element(page, locator, timeout=30000, retries=5, sleep=2):
    for attempt in range(retries):
        try:
            await locator.wait_for(state="visible", timeout=timeout)
            return True
        except Exception:
            await asyncio.sleep(sleep)
    return False

async def _aplicar_filtro_por_id(page: Page, row_id: int, logger: ProcessLogger = None, id_consulta=None) -> Optional[dict]:
    if logger:
        logger.web(f"Aplicando filtro pelo ID: {row_id}")
    else:
        print(f"[WEB] Aplicando filtro pelo ID: {row_id}")
        
    try:
        id_input = page.locator('#cltlotesearch-id')
        if await id_input.count() == 0:
            id_input = page.locator('input[name="CltLoteSearch[id]"]')

        if await id_input.count() == 0:
            filtro_btn = page.get_by_role("button", name=re.compile("Filtro|Filtros|Pesquisar|Buscar", re.I))
            if await filtro_btn.count() > 0:
                await filtro_btn.first.click()
                await page.wait_for_timeout(400)
                id_input = page.locator('#cltlotesearch-id')
                if await id_input.count() == 0:
                    id_input = page.locator('input[name="CltLoteSearch[id]"]')

        id_input = id_input.first
        # Redundância: aguarda elemento com retries e timeout maior
        if not await wait_for_element(page, id_input, timeout=40000, retries=5, sleep=3):
            return erro_playwright_retorno(id_consulta, "Campo de filtro por ID não encontrado", "playwright_service", "Timeout ao aguardar campo de filtro.")
        await id_input.click()
        await id_input.fill(str(row_id))
        await id_input.press("Enter")
        await page.wait_for_load_state("networkidle", timeout=40000)

        search_btn = page.get_by_role("button", name=re.compile("Pesquisar|Buscar|Filtrar", re.I))
        if await search_btn.count() > 0:
            await search_btn.first.click()
            await page.wait_for_load_state("networkidle", timeout=40000)

        if logger:
            logger.success("Filtro aplicado com sucesso.")
        else:
            print("[SUCCESS] Filtro aplicado com sucesso.")
        return None
    except Exception as e:
        return erro_playwright_retorno(id_consulta, "Erro ao aplicar filtro por ID", "playwright_service", str(e))

async def baixar_excel_por_id(row_id: int, titulo: str, logger: ProcessLogger = None, id_consulta=None) -> Optional[Path]:
    try:
        async with async_playwright() as p:
            if logger:
                logger.web("Iniciando navegador Playwright")
            else:
                print("[WEB] Iniciando navegador Playwright")
            browser = await p.chromium.launch(headless=HEADLESS)
            context = await browser.new_context(accept_downloads=True)
            page = await context.new_page()
            if logger:
                logger.web("Fazendo login no site...")
            else:
                print("[WEB] Fazendo login no site...")
            await page.goto("https://dashboard.conectpromotora.com.br/login", timeout=40000)
            usuario_input = page.get_by_role("textbox", name="Usuário")
            senha_input = page.get_by_role("textbox", name="Senha")
            if not await wait_for_element(page, usuario_input, timeout=40000, retries=5, sleep=3):
                await context.close(); await browser.close()
                return erro_playwright_retorno(id_consulta, "Campo Usuário não encontrado", "playwright_service", "Timeout ao aguardar campo Usuário.")
            if not await wait_for_element(page, senha_input, timeout=40000, retries=5, sleep=3):
                await context.close(); await browser.close()
                return erro_playwright_retorno(id_consulta, "Campo Senha não encontrado", "playwright_service", "Timeout ao aguardar campo Senha.")
            await usuario_input.fill(SITE_USER)
            await senha_input.fill(SITE_PASS)
            await page.get_by_role("button", name="Acessar").click()
            await page.wait_for_load_state("networkidle", timeout=40000)
            if logger:
                logger.web("Navegando para Consultas em Lote > CLT ...")
            else:
                print("[WEB] Navegando para Consultas em Lote > CLT ...")
            await page.get_by_role("link", name="Consultas em Lote").click()
            await page.wait_for_load_state("networkidle", timeout=40000)
            await page.get_by_role("link", name="CLT").click()
            await page.wait_for_load_state("networkidle", timeout=40000)
            filtro_result = await _aplicar_filtro_por_id(page, row_id, logger, id_consulta)
            if isinstance(filtro_result, dict):
                await context.close(); await browser.close()
                return filtro_result
            consultas_link = page.get_by_role("link", name="Consultas")
            if await consultas_link.count() > 1:
                await consultas_link.nth(1).click()
            else:
                await consultas_link.first.click()
            await page.wait_for_load_state("networkidle", timeout=40000)
            if logger:
                logger.web("Procurando botão 'Exportar Excel' e realizando download...")
            else:
                print("[WEB] Procurando botão 'Exportar Excel' e realizando download...")
            export_btn = page.get_by_role("link", name="Exportar Excel")
            if not await wait_for_element(page, export_btn, timeout=40000, retries=5, sleep=3):
                await context.close(); await browser.close()
                return erro_playwright_retorno(id_consulta, "Botão 'Exportar Excel' não encontrado", "playwright_service", "Timeout ao aguardar botão Exportar Excel.")
            async with page.expect_download() as dlinfo:
                await export_btn.first.click()
            dl = await dlinfo.value
            safe_name = re.sub(r'[\\/*?"<>|]+', '_', titulo)
            dest = OUTPUT_DIR / f"{safe_name}.xlsx"
            try:
                await dl.save_as(str(dest))
            except Exception as e:
                await context.close(); await browser.close()
                return erro_playwright_retorno(id_consulta, "Erro ao salvar arquivo baixado", "playwright_service", str(e))
            if logger:
                logger.success(f"Arquivo baixado: {dest}")
            else:
                print(f"[SUCCESS] Arquivo baixado: {dest}")
            await context.close()
            await browser.close()
            return dest
    except Exception as e:
        return erro_playwright_retorno(id_consulta, "Erro geral no Playwright", "playwright_service", str(e))
