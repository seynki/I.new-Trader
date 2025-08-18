import asyncio
import os
import time
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from playwright.async_api import async_playwright

SESSION_DIR = "/data/session"
LOGIN_URL = "https://iqoption.com/en/login"
TRADEROOM_URL = "https://iqoption.com/traderoom"

app = FastAPI(title="IQ-Bridge", version="0.1.0")

class LoginBody(BaseModel):
    email: str
    password: str
    otp_code: str | None = None

class OrderBody(BaseModel):
    asset: str  # EURUSD, EURUSD-OTC, BTCUSD
    direction: str  # call|put
    amount: float
    expiration: int
    account_type: str = "demo"  # demo|real
    option_type: str = "binary" # binary|digital

class Bridge:
    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None
        self.lock = asyncio.Lock()

    async def ensure(self):
        if self.browser and self.context and self.page:
            return
        p = await async_playwright().start()
        self.browser = await p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR,
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
            viewport={"width": 1280, "height": 800}
        )
        pages = self.browser.pages
        self.page = pages[0] if pages else await self.browser.new_page()

    async def close(self):
        try:
            if self.browser:
                await self.browser.close()
        except Exception:
            pass

bridge = Bridge()

@app.get("/bridge/health")
async def health():
    return {"status": "ok", "ts": time.time()}

@app.post("/bridge/login")
async def bridge_login(body: LoginBody):
    await bridge.ensure()
    async with bridge.lock:
        page = bridge.page
        try:
            await page.goto(TRADEROOM_URL, timeout=30000)
            # Se já estiver logado, traderoom carrega sem redirecionar
            if TRADEROOM_URL in page.url and "login" not in page.url:
                return {"status": "ok", "message": "Já logado", "url": page.url}

            await page.goto(LOGIN_URL, timeout=30000)
            # Campos de login (os seletores podem mudar; usar tentativas)
            candidates_email = ["input[name=login]", "input[type=email]", "#email"]
            candidates_pass = ["input[name=password]", "input[type=password]", "#password"]

            found = False
            for sel in candidates_email:
                if await page.locator(sel).count() > 0:
                    await page.fill(sel, body.email)
                    found = True
                    break
            if not found:
                raise HTTPException(status_code=500, detail="Campo de email não encontrado")

            found = False
            for sel in candidates_pass:
                if await page.locator(sel).count() > 0:
                    await page.fill(sel, body.password)
                    found = True
                    break
            if not found:
                raise HTTPException(status_code=500, detail="Campo de senha não encontrado")

            # Enviar form (tentar botão com type=submit)
            submit_candidates = ["button[type=submit]", "button:has-text('Log in')", "button:has-text('Sign in')"]
            clicked = False
            for sel in submit_candidates:
                if await page.locator(sel).count() > 0:
                    await page.click(sel)
                    clicked = True
                    break
            if not clicked:
                # Pressiona Enter
                await page.keyboard.press("Enter")

            # Espera traderoom ou desafio 2FA/captcha
            try:
                await page.wait_for_url("**/traderoom**", timeout=30000)
                return {"status": "ok", "message": "Login OK", "url": page.url}
            except Exception:
                # Verificar se há campo de OTP
                if body.otp_code:
                    otp_candidates = ["input[name=otp]", "input[name=code]", "input[autocomplete=one-time-code]"]
                    for sel in otp_candidates:
                        if await page.locator(sel).count() > 0:
                            await page.fill(sel, body.otp_code)
                            await page.keyboard.press("Enter")
                            try:
                                await page.wait_for_url("**/traderoom**", timeout=30000)
                                return {"status": "ok", "message": "Login OK (2FA)", "url": page.url}
                            except Exception:
                                break
                raise HTTPException(status_code=503, detail="Não entrou no traderoom (possível captcha/2FA sem código)")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Erro login: {e}")

async def select_asset(page, asset_display: str):
    # Tenta abrir campo de busca e selecionar o ativo
    # IQ Option muda layout; tentamos buscas genéricas
    candidates_open_search = ["[data-testid=search]", "button:has-text('Search')", "[class*='search']"]
    for sel in candidates_open_search:
        if await page.locator(sel).count() > 0:
            try:
                await page.click(sel)
                break
            except Exception:
                pass
    # Inputs possíveis
    inputs = ["input[type=search]", "input[placeholder*='Search']", "input"]
    for sel in inputs:
        if await page.locator(sel).count() > 0:
            try:
                await page.fill(sel, asset_display)
                await page.keyboard.press("Enter")
                await asyncio.sleep(1.5)
                break
            except Exception:
                pass

@app.post("/bridge/quick-order")
async def bridge_quick_order(body: OrderBody):
    await bridge.ensure()
    async with bridge.lock:
        page = bridge.page
        try:
            await page.goto(TRADEROOM_URL, timeout=30000)
            # Determinar exibição do ativo (EURUSD -> EUR/USD, EURUSD-OTC -> EUR/USD-OTC, BTCUSD -> BTC/USD)
            a = body.asset.upper()
            display = a
            if len(a) == 6 and a.isalpha():
                display = f"{a[:3]}/{a[3:]}"
                if a.endswith("-OTC"):
                    display = display + "-OTC"
            elif a.endswith("USD") and not a.endswith("-OTC") and a[:-3].isalpha():
                display = f"{a[:-3]}/USD"
            # Seleciona ativo
            await select_asset(page, display)

            # Seleciona conta DEMO/REAL (best-effort)
            if body.account_type.lower() == "demo":
                try:
                    await page.get_by_text("practice", exact=False).click(timeout=2000)
                except Exception:
                    pass
            else:
                try:
                    await page.get_by_text("real", exact=False).click(timeout=2000)
                except Exception:
                    pass

            # Define valor (best-effort)
            try:
                amount_inputs = ["input[name=amount]", "input[aria-label*='amount']", "input[type=number]"]
                for sel in amount_inputs:
                    if await page.locator(sel).count() > 0:
                        await page.fill(sel, str(int(body.amount)))
                        break
            except Exception:
                pass

            # Clicar Buy/Sell (botões comuns na sala)
            clicked = False
            if body.direction == "call":
                for txt in ["Buy", "CALL", "Higher"]:
                    loc = page.get_by_text(txt, exact=False)
                    if await loc.count() > 0:
                        try:
                            await loc.first.click()
                            clicked = True
                            break
                        except Exception:
                            pass
            else:
                for txt in ["Sell", "PUT", "Lower"]:
                    loc = page.get_by_text(txt, exact=False)
                    if await loc.count() > 0:
                        try:
                            await loc.first.click()
                            clicked = True
                            break
                        except Exception:
                            pass
            if not clicked:
                raise HTTPException(status_code=503, detail="Não foi possível clicar Buy/Sell automaticamente (UI diferente)")

            return {"status": "ok", "message": "Ordem enviada via Bridge (best-effort)", "asset_display": display}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Erro quick-order bridge: {e}")