import asyncio
import os
import time
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel
from playwright.async_api import async_playwright

SESSION_DIR = "/data/session"
LOGIN_URL = "https://iqoption.com/en/login"
TRADEROOM_URL = "https://iqoption.com/traderoom"
HEADLESS = os.getenv("BRIDGE_HEADLESS", "1") not in ("0", "false", "False")

app = FastAPI(title="IQ-Bridge", version="0.2.0")

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
        self.play = None

    async def ensure(self):
        if self.browser and self.context and self.page:
            return
        self.play = await async_playwright().start()
        self.context = await self.play.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR,
            headless=HEADLESS,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
            viewport={"width": 1366, "height": 900}
        )
        pages = self.context.pages
        self.browser = self.context
        self.page = pages[0] if pages else await self.context.new_page()

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

@app.get("/bridge/status")
async def status():
    await bridge.ensure()
    page = bridge.page
    return {"url": page.url, "headless": HEADLESS}

@app.get("/bridge/screenshot")
async def screenshot(full: bool = False):
    await bridge.ensure()
    page = bridge.page
    try:
        img = await page.screenshot(full_page=full)
        return Response(content=img, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"screenshot error: {e}")

@app.post("/bridge/login")
async def bridge_login(body: LoginBody):
    await bridge.ensure()
    async with bridge.lock:
        page = bridge.page
        try:
            # Se já está no traderoom, retorna
            try:
                await page.goto(TRADEROOM_URL, timeout=30000, wait_until="domcontentloaded")
            except Exception:
                pass
            if "traderoom" in page.url and "login" not in page.url:
                return {"status": "ok", "message": "Já logado", "url": page.url}

            await page.goto(LOGIN_URL, timeout=30000, wait_until="domcontentloaded")

            # Possíveis campos (pt/en)
            candidates_email = [
                "input[name=login]", "input[type=email]", "#email", "input[name=email]"
            ]
            candidates_pass = [
                "input[name=password]", "input[type=password]", "#password"
            ]

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

            # Submeter
            submit_candidates = [
                "button[type=submit]", "button:has-text('Log in')", "button:has-text('Sign in')",
                "button:has-text('Entrar')", "button:has-text('Iniciar sessão')"
            ]
            clicked = False
            for sel in submit_candidates:
                if await page.locator(sel).count() > 0:
                    try:
                        await page.click(sel)
                        clicked = True
                        break
                    except Exception:
                        pass
            if not clicked:
                await page.keyboard.press("Enter")

            # Esperar traderoom ou OTP
            try:
                await page.wait_for_url("**/traderoom**", timeout=35000)
                return {"status": "ok", "message": "Login OK", "url": page.url}
            except Exception:
                if body.otp_code:
                    otp_candidates = [
                        "input[name=otp]", "input[name=code]", "input[autocomplete=one-time-code]",
                        "input[type=tel]"
                    ]
                    for sel in otp_candidates:
                        if await page.locator(sel).count() > 0:
                            await page.fill(sel, body.otp_code)
                            await page.keyboard.press("Enter")
                            await page.wait_for_url("**/traderoom**", timeout=35000)
                            return {"status": "ok", "message": "Login OK (2FA)", "url": page.url}
                raise HTTPException(status_code=503, detail="Não entrou no traderoom (possível OTP/captcha)")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Erro login: {e}")

async def select_asset(page, asset_display: str):
    # Abre busca
    try:
        for key in ["/"]:
            await page.keyboard.press(key)
            await asyncio.sleep(0.3)
    except Exception:
        pass

    candidates_open_search = [
        "[data-testid=search]", "button:has-text('Search')", "button:has-text('Buscar')",
        "[class*='search']", "input[type=search]"
    ]
    for sel in candidates_open_search:
        if await page.locator(sel).count() > 0:
            try:
                await page.click(sel)
                break
            except Exception:
                pass

    # Digita o ativo
    inputs = [
        "input[type=search]", "input[placeholder*='Search']", "input[placeholder*='Buscar']",
        "input[role=combobox]", "input"
    ]
    typed = False
    for sel in inputs:
        if await page.locator(sel).count() > 0:
            try:
                await page.fill(sel, asset_display)
                await page.keyboard.press("Enter")
                await asyncio.sleep(1.5)
                typed = True
                break
            except Exception:
                pass
    if not typed:
        # Tenta atalho: digitar direto
        try:
            await page.keyboard.type(asset_display)
            await page.keyboard.press("Enter")
            await asyncio.sleep(1.2)
        except Exception:
            pass

@app.post("/bridge/quick-order")
async def bridge_quick_order(body: OrderBody):
    await bridge.ensure()
    async with bridge.lock:
        page = bridge.page
        step = "start"
        try:
            step = "goto_traderoom"
            await page.goto(TRADEROOM_URL, timeout=35000, wait_until="domcontentloaded")
            await asyncio.sleep(1.2)
            # Se fomos redirecionados para login, retornar 401 para o backend tentar /bridge/login
            if "login" in page.url:
                raise HTTPException(status_code=401, detail={"error": "not_logged", "step": step, "url": page.url})

            # Aceitar cookies/popups (best-effort)
            step = "accept_cookies"
            for txt in ["Accept", "I agree", "Aceitar", "Concordo"]:
                loc = page.get_by_text(txt, exact=False)
                if await loc.count() > 0:
                    try:
                        await loc.first.click(timeout=1500)
                        break
                    except Exception:
                        pass

            # Determinar exibição do ativo
            a = body.asset.upper()
            display = a
            if len(a) == 6 and a.isalpha():
                display = f"{a[:3]}/{a[3:]}"
                if a.endswith("-OTC"):
                    display = display + "-OTC"
            elif a.endswith("USD") and not a.endswith("-OTC") and a[:-3].isalpha():
                display = f"{a[:-3]}/USD"

            step = "select_asset"
            await select_asset(page, display)

            # Seleciona conta DEMO/REAL (best-effort)
            step = "select_account"
            if body.account_type.lower() == "demo":
                for txt in ["practice", "demo", "Prática", "Conta de treinamento"]:
                    loc = page.get_by_text(txt, exact=False)
                    if await loc.count() > 0:
                        try:
                            await loc.first.click(timeout=1500)
                            break
                        except Exception:
                            pass
            else:
                for txt in ["real", "Real"]:
                    loc = page.get_by_text(txt, exact=False)
                    if await loc.count() > 0:
                        try:
                            await loc.first.click(timeout=1500)
                            break
                        except Exception:
                            pass

            # Define valor (best-effort)
            step = "set_amount"
            try:
                amount_inputs = [
                    "input[name=amount]", "input[aria-label*='amount']",
                    "input[type=number]", "input[pattern='[0-9]*']"
                ]
                done = False
                for sel in amount_inputs:
                    if await page.locator(sel).count() > 0:
                        await page.fill(sel, str(int(max(1, body.amount))))
                        done = True
                        break
                if not done:
                    # Tenta botões +/-
                    for txt in ["+", "-"]:
                        loc = page.get_by_text(txt, exact=True)
                        if await loc.count() > 0:
                            await loc.first.click(timeout=1000)
                            break
            except Exception:
                pass

            # Clicar Buy/Sell
            step = "click_order"
            clicked = False
            if body.direction == "call":
                for txt in ["Buy", "CALL", "Higher", "Comprar", "Mais alto", "Acima"]:
                    loc = page.get_by_text(txt, exact=False)
                    if await loc.count() > 0:
                        try:
                            await loc.first.click()
                            clicked = True
                            break
                        except Exception:
                            pass
            else:
                for txt in ["Sell", "PUT", "Lower", "Vender", "Mais baixo", "Abaixo"]:
                    loc = page.get_by_text(txt, exact=False)
                    if await loc.count() > 0:
                        try:
                            await loc.first.click()
                            clicked = True
                            break
                        except Exception:
                            pass
            if not clicked:
                raise HTTPException(status_code=503, detail=f"Não foi possível clicar Buy/Sell automaticamente (step={step})")

            return {"status": "ok", "message": "Ordem enviada via Bridge", "asset_display": display}
        except HTTPException as he:
            # Tenta screenshot para diagnóstico
            try:
                img = await page.screenshot(full_page=True)
            except Exception:
                img = None
            detail = {"error": he.detail, "step": step, "url": page.url}
            raise HTTPException(status_code=503, detail=detail)
        except Exception as e:
            try:
                img = await page.screenshot(full_page=True)
            except Exception:
                img = None
            raise HTTPException(status_code=503, detail={"error": str(e), "step": step, "url": page.url})