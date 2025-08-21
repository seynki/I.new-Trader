import os
import json
import asyncio
from typing import Any, Dict, Optional
from datetime import datetime

import websockets

# Lightweight Deriv integration: open-per-call WebSocket usage to avoid heavy persistent state.
# We keep timeouts small in preview environments and short-circuit when not configured.

DERIV_WSS_ENDPOINT = "ws.derivws.com"


def _get_env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


async def _ws_call(requests: list[Dict[str, Any]], app_id: int, timeout: float = 8.0) -> list[Dict[str, Any]]:
    """Open a websocket, send a sequence of requests, gather responses in order.
    This is a minimal helper suitable for diagnostics and one-shot orders.
    """
    uri = f"wss://{DERIV_WSS_ENDPOINT}/websockets/v3?app_id={app_id}"
    results: list[Dict[str, Any]] = []
    try:
        async with websockets.connect(uri, ping_interval=20, ping_timeout=10, close_timeout=10) as ws:
            # Send all requests
            for req in requests:
                await ws.send(json.dumps(req))
                # Wait one response per request (Deriv echoes one response per message with same req_id or msg_type)
                msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
                data = json.loads(msg)
                results.append(data)
    except asyncio.TimeoutError:
        results.append({"error": {"message": "timeout"}})
    except Exception as e:
        results.append({"error": {"message": str(e)}})
    return results


async def deriv_diagnostics() -> Dict[str, Any]:
    """Return quick diagnostics without requiring API token.
    - Uses ping and active_symbols calls if DERIV_APP_ID is present; otherwise reports not_configured.
    """
    app_id = _get_env_int("DERIV_APP_ID", 0)
    use_demo = os.getenv("DERIV_USE_DEMO", "1") == "1"
    if app_id <= 0:
        return {
            "status": "not_configured",
            "summary": "DERIV_APP_ID ausente. Configure DERIV_APP_ID e DERIV_API_TOKEN (demo)",
            "deriv_connected": False,
            "deriv_authenticated": False,
            "available_symbols": 0,
            "use_demo": use_demo,
            "timestamp": datetime.utcnow().isoformat(),
        }

    # Try ping and active_symbols
    responses = await _ws_call([{"ping": 1}, {"active_symbols": "brief"}], app_id=app_id)

    ping_ok = any("pong" in r for r in responses if isinstance(r, dict))
    symbols_count = 0
    for r in responses:
        if isinstance(r, dict) and r.get("msg_type") == "active_symbols":
            symbols = r.get("active_symbols", [])
            symbols_count = len(symbols)
            break

    errors = [r.get("error") for r in responses if isinstance(r, dict) and r.get("error")]

    return {
        "status": "success" if ping_ok else "partial",
        "summary": "OK" if ping_ok else (errors[0]["message"] if errors else "unknown"),
        "deriv_connected": bool(ping_ok),
        "deriv_authenticated": False,  # not attempted here
        "available_symbols": symbols_count,
        "use_demo": use_demo,
        "errors": errors,
        "timestamp": datetime.utcnow().isoformat(),
    }


def map_asset_to_deriv_symbol(asset: str) -> Optional[str]:
    """Map app asset (e.g., EURUSD, BTCUSDT, VOLATILITY_10) to Deriv symbol.
    If input already looks like a Deriv code (frx..., cry..., R_..., BOOM/CRASH...N), return as-is.
    """
    asset = (asset or "").upper()
    # Already a Deriv code
    if asset.startswith(("FRX", "CRY")) or asset.startswith("R_") or asset.startswith("BOOM") or asset.startswith("CRASH"):
        return asset
    mapping = {
        # Forex
        "EURUSD": "frxEURUSD",
        "GBPUSD": "frxGBPUSD",
        "USDJPY": "frxUSDJPY",
        "AUDUSD": "frxAUDUSD",
        "USDCAD": "frxUSDCAD",
        "USDCHF": "frxUSDCHF",
        "EURJPY": "frxEURJPY",
        "GBPJPY": "frxGBPJPY",
        # Crypto (USD settlement)
        "BTCUSDT": "cryBTCUSD",
        "ETHUSDT": "cryETHUSD",
        "LTCUSDT": "cryLTCUSD",
        "ADAUSDT": "cryADAUSD",
        "DOTUSDT": "cryDOTUSD",
        "BNBUSDT": "cryBNBUSD",
        # Synthetics (24/7)
        "VOLATILITY_10": "R_10",
        "VOLATILITY_25": "R_25",
        "VOLATILITY_50": "R_50",
        "VOLATILITY_75": "R_75",
        "VOLATILITY_100": "R_100",
        "BOOM_300": "BOOM300N",
        "BOOM_500": "BOOM500N",
        "CRASH_300": "CRASH300N",
        "CRASH_500": "CRASH500N",
    }
    return mapping.get(asset)


def _is_synthetic_symbol(symbol_code: str) -> bool:
    return symbol_code.startswith("R_") or symbol_code in {"BOOM300N", "BOOM500N", "CRASH300N", "CRASH500N"}


def _buy_only_symbol(symbol_code: str) -> bool:
    # BOOM/CRASH são geralmente buy-only na plataforma para determinados contratos
    return symbol_code in {"BOOM300N", "BOOM500N", "CRASH300N", "CRASH500N"}


async def deriv_quick_order(asset: str, direction: str, amount: float, expiration_min: int) -> Dict[str, Any]:
    """Execute a minimal quick order flow on Deriv using proposal -> buy.
    Requirements: DERIV_APP_ID and DERIV_API_TOKEN must be set. Runs on demo if DERIV_USE_DEMO=1.
    Returns a dict similar to QuickOrderResponse fields.
    - Auto: forex/crypto use minutes; synthetics (R_*) use ticks; BOOM/CRASH are buy-only.
    """
    app_id = _get_env_int("DERIV_APP_ID", 0)
    api_token = os.getenv("DERIV_API_TOKEN")
    use_demo = os.getenv("DERIV_USE_DEMO", "1") == "1"

    if app_id <= 0 or not api_token:
        return {
            "success": False,
            "error": "Deriv não configurado (defina DERIV_APP_ID e DERIV_API_TOKEN)",
        }

    symbol = map_asset_to_deriv_symbol(asset)
    if not symbol:
        return {
            "success": False,
            "error": f"Ativo não suportado para Deriv: {asset}",
        }

    # Direction mapping
    dir_norm = (direction or "").lower()
    if dir_norm in ("call", "rise", "up"):
        contract_type = "CALL"
    elif dir_norm in ("put", "fall", "down"):
        contract_type = "PUT"
    else:
        return {"success": False, "error": f"Direção inválida: {direction}"}

    # Enforce buy-only symbols
    if _buy_only_symbol(symbol) and contract_type != "CALL":
        return {"success": False, "error": "Este mercado aceita apenas compra (CALL)."}

    # duration auto mode
    duration_unit = "m"
    duration_value = int(expiration_min)
    if _is_synthetic_symbol(symbol):
        duration_unit = "t"  # ticks
        # clamp ticks between 1 and 10 for safety if user passed minutes
        duration_value = max(1, min(10, int(expiration_min or 5)))

    # Build request sequence: authorize -> proposal -> buy
    req_authorize = {"authorize": api_token}
    req_proposal = {
        "proposal": 1,
        "amount": float(amount),
        "basis": "stake",
        "contract_type": contract_type,
        "currency": "USD",
        "duration": duration_value,
        "duration_unit": duration_unit,
        "symbol": symbol,
    }

    # Do authorize and proposal first
    responses = await _ws_call([req_authorize, req_proposal], app_id=app_id, timeout=12.0)

    # Validate authorize
    auth_ok = any(isinstance(r, dict) and r.get("msg_type") == "authorize" for r in responses)
    if not auth_ok:
        err = next((r.get("error", {}).get("message") for r in responses if isinstance(r, dict) and r.get("error")), "falha ao autorizar")
        return {"success": False, "error": f"Falha na autorização: {err}"}

    # Get proposal
    proposal_data: Optional[Dict[str, Any]] = None
    for r in responses:
        if isinstance(r, dict) and r.get("msg_type") == "proposal":
            proposal_data = r.get("proposal")
            break
    if not proposal_data:
        err = next((r.get("error", {}).get("message") for r in responses if isinstance(r, dict) and r.get("error")), "falha ao obter proposta")
        return {"success": False, "error": f"Falha na proposta: {err}"}

    proposal_id = proposal_data.get("id")
    ask_price = proposal_data.get("ask_price")
    if not proposal_id:
        return {"success": False, "error": "ID de proposta ausente"}

    # Buy (robust): reautoriza e envia buy para garantir resposta correta como 2ª mensagem
    req_buy = {"buy": proposal_id, "price": float(ask_price) if ask_price is not None else float(amount)}
    buy_responses = await _ws_call([{"authorize": api_token}, req_buy], app_id=app_id, timeout=12.0)

    # Procurar erro explícito primeiro
    explicit_err = next((r.get("error", {}).get("message") for r in buy_responses if isinstance(r, dict) and r.get("error")), None)
    if explicit_err:
        return {"success": False, "error": f"Falha na compra: {explicit_err}"}

    # Encontrar mensagem de compra
    buy_msg = next((r for r in buy_responses if isinstance(r, dict) and r.get("msg_type") == "buy"), None)
    if not buy_msg:
        # Sem mensagem 'buy' — retornar erro descritivo com amostra de resposta
        sample = buy_responses[-1] if buy_responses else {"info": "sem respostas"}
        return {"success": False, "error": f"Falha na compra: resposta inesperada ({str(sample)[:200]})"}

    # Extrair dados de compra de forma tolerante
    buy_data = buy_msg.get("buy") or buy_msg.get("purchase") or {}
    contract_id = buy_data.get("contract_id") or buy_msg.get("contract_id") or buy_data.get("transaction_id") or buy_msg.get("transaction_id")
    buy_price = buy_data.get("buy_price") or buy_msg.get("buy_price")
    payout = buy_data.get("payout") or buy_msg.get("payout")

    if not contract_id:
        return {"success": False, "error": f"Falha na compra: resposta sem contract_id ({str(buy_msg)[:200]})"}

    return {
        "success": True,
        "contract_id": contract_id,
        "proposal_id": proposal_id,
        "purchase_price": buy_price,
        "payout": payout,
        "asset": asset,
        "direction": direction,
        "duration_unit": duration_unit,
        "duration_value": duration_value,
        "timestamp": datetime.utcnow().isoformat(),
        "provider": "deriv",
        "use_demo": use_demo,
    }