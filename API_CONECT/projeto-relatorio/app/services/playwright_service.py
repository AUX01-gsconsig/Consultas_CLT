import os
import re
from pathlib import Path
from typing import Optional
from playwright.async_api import async_playwright, Page
from app.utils.logger import ProcessLogger

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "./downloads"))
OUTPUT_DIR.mkdir(exist_ok=True)

SITE_USER = os.getenv("SITE_USER")
SITE_PASS = os.getenv("SITE_PASS")
HEADLESS = os.getenv("HEADLESS", "true").lower() in ("1","true","yes","y")

async def _aplicar_filtro_por_id(page: Page, row_id: int, logger: ProcessLogger = None) -> None:
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
        await id_input.wait_for(state="visible", timeout=10000)
        await id_input.click()
        await id_input.fill(str(row_id))
        await id_input.press("Enter")
        await page.wait_for_load_state("networkidle")

        search_btn = page.get_by_role("button", name=re.compile("Pesquisar|Buscar|Filtrar", re.I))
        if await search_btn.count() > 0:
            await search_btn.first.click()
            await page.wait_for_load_state("networkidle")

        if logger:
            logger.success("Filtro aplicado com sucesso.")
        else:
            print("[SUCCESS] Filtro aplicado com sucesso.")
    except Exception as e:
        if logger:
            logger.warning(f"Não foi possível aplicar o filtro pelo ID: {e}")
        else:
            print(f"[WARNING] Não foi possível aplicar o filtro pelo ID: {e}")

async def baixar_excel_por_id(row_id: int, titulo: str, logger: ProcessLogger = None) -> Optional[Path]:
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
            
        await page.goto("https://dashboard.conectpromotora.com.br/login")
        await page.get_by_role("textbox", name="Usuário").fill(SITE_USER)
        await page.get_by_role("textbox", name="Senha").fill(SITE_PASS)
        await page.get_by_role("button", name="Acessar").click()

        if logger:
            logger.web("Navegando para Consultas em Lote > CLT ...")
        else:
            print("[WEB] Navegando para Consultas em Lote > CLT ...")
            
        await page.get_by_role("link", name="Consultas em Lote").click()
        await page.get_by_role("link", name="CLT").click()

        # tenta filtrar pelo ID
        await _aplicar_filtro_por_id(page, row_id, logger)

        # entra na aba Consultas (segunda ocorrência costuma ser a lista de consultas)
        consultas_link = page.get_by_role("link", name="Consultas")
        if await consultas_link.count() > 1:
            await consultas_link.nth(1).click()
        else:
            await consultas_link.first.click()
        await page.wait_for_load_state("networkidle")

        if logger:
            logger.web("Procurando botão 'Exportar Excel' e realizando download...")
        else:
            print("[WEB] Procurando botão 'Exportar Excel' e realizando download...")
            
        export_btn = page.get_by_role("link", name="Exportar Excel")
        if await export_btn.count() == 0:
            if logger:
                logger.error("Botão 'Exportar Excel' não encontrado.")
            else:
                print("[ERROR] Botão 'Exportar Excel' não encontrado.")
            await context.close(); await browser.close()
            return None

        async with page.expect_download() as dlinfo:
            await export_btn.first.click()
        dl = await dlinfo.value

        safe_name = re.sub(r'[\\/*?"<>|]+', '_', titulo)
        dest = OUTPUT_DIR / f"{safe_name}.xlsx"
        await dl.save_as(str(dest))
        
        if logger:
            logger.success(f"Arquivo baixado: {dest}")
        else:
            print(f"[SUCCESS] Arquivo baixado: {dest}")

        await context.close()
        await browser.close()
        return dest
