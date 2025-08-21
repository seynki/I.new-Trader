"""
Wrapper para estender o app base (server_restored) com rotas Deriv e override do quick-order.
Mantém toda a lógica existente, apenas adiciona/ajusta rotas necessárias para Deriv.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Any, Dict, Optional
import json

from fastapi import HTTPException
from pydantic import BaseModel

# Importa o app e helpers já existentes
from server_restored import app, db, broadcast_message, logger  # type: ignore

# Integração Deriv (leve)
try:
    from deriv_integration import (
        deriv_diagnostics as deriv_diag_fn,
        deriv_quick_order as deriv_quick_order_fn,
        map_asset_to_deriv_symbol,
        deriv_auth_check,
    )
except Exception:
    deriv_diag_fn = None
    deriv_quick_order_fn = None
    map_asset_to_deriv_symbol = None
    deriv_auth_check = None

# Flags/credenciais Deriv a partir do ambiente
USE_DERIV = os.getenv("USE_DERIV", "1")  # manter ligado por padrão
DERIV_APP_ID = os.getenv("DERIV_APP_ID")
DERIV_API_TOKEN = os.getenv("DERIV_API_TOKEN")


# Util: converter nomes comuns para código Deriv
def to_deriv_code(asset: str) -> str:
    a = (asset or "").upper().strip()
    if not a:
        return a
    if a.startswith(("FRX", "CRY")) or a.startswith("R_") or a.startswith("BOOM") or a.startswith("CRASH"):
        return a
    if map_asset_to_deriv_symbol:
        try:
            m = map_asset_to_deriv_symbol(a)
            if m:
                return m
        except Exception:
            pass
    # Forex 6 letras
    if len(a) == 6 and a.isalpha():
        return f"frx{a}"
    # Crypto USDT/ USD
    if a.endswith("USDT"):
        base = a[:-1]
        return f"cry{base}"
    if a.endswith("USD"):
        return f"cry{a}"
    return a


# Remover rota duplicada se já existir (para sobrescrever quick-order antigo)
def _remove_route(path: str, method: str | None = None) -> None:
    try:
        to_remove = []
        for r in list(app.router.routes):
            if getattr(r, "path", None) == path:
                if method is None or (hasattr(r, "methods") and method in r.methods):
                    to_remove.append(r)
        for r in to_remove:
            app.router.routes.remove(r)
            logger.info(f"Rota removida para override: {path} {getattr(r, 'methods', set())}")
    except Exception as e:
        logger.warning(f"Falha ao remover rota {path}: {e}")


# 1) Endpoint de diagnóstico Deriv
if deriv_diag_fn is not None:
    @app.get("/api/deriv/diagnostics")
    async def deriv_diagnostics_endpoint():
        try:
            return await deriv_diag_fn()
        except Exception as e:
            logger.error(f"Deriv diagnostics error: {e}")
            return {"status": "error", "summary": str(e)}

# 1.1) Endpoint de verificação de autenticação Deriv (confirma token/loginid)
if deriv_auth_check is not None:
    @app.get("/api/deriv/status")
    async def deriv_status():
        try:
            return await deriv_auth_check()
        except Exception as e:
            logger.error(f"Deriv auth check error: {e}")
            return {"status": "error", "summary": str(e)}


# 2) Override do quick-order para priorizar Deriv quando USE_DERIV=1
class QuickOrderRequest(BaseModel):
    asset: str
    direction: str  # 'call' or 'put'
    amount: float
    expiration: int  # minutos (ou ticks para sintéticos)
    account_type: str = "demo"
    option_type: str = "binary"

class QuickOrderResponse(BaseModel):
    success: bool
    message: str
    order_id: Optional[str] = None
    echo: Optional[Dict[str, Any]] = None


_remove_route("/api/trading/quick-order", method="POST")

@app.post("/api/trading/quick-order")
async def quick_order(order: QuickOrderRequest):
    # Se Deriv desativado, encaminhar para comportamento antigo via rota legacy
    if USE_DERIV != "1" or deriv_quick_order_fn is None:
        raise HTTPException(status_code=503, detail="Integração Deriv indisponível ou desativada (USE_DERIV!=1)")

    if not DERIV_APP_ID or not DERIV_API_TOKEN:
        raise HTTPException(status_code=503, detail="Deriv não configurado (defina DERIV_APP_ID e DERIV_API_TOKEN)")

    # Regras para mercados Deriv (synthetics R_* usam ticks 1–10; BOOM/CRASH buy-only)
    d_sym = to_deriv_code(order.asset)
    is_synth = d_sym.startswith("R_") or "BOOM" in d_sym or "CRASH" in d_sym
    if ("BOOM" in d_sym or "CRASH" in d_sym) and order.direction != "call":
        raise HTTPException(status_code=400, detail="Este mercado aceita apenas compra (CALL).")
    if is_synth:
        if not (1 <= int(order.expiration) <= 10):
            raise HTTPException(status_code=400, detail="expiration deve estar entre 1 e 10 ticks para mercados sintéticos (Deriv)")
    else:
        if not (1 <= int(order.expiration) <= 60):
            raise HTTPException(status_code=400, detail="expiration deve estar entre 1 e 60 minutos")

    try:
        result = await deriv_quick_order_fn(order.asset, order.direction, float(order.amount), int(order.expiration))
        if not result.get("success"):
            # Melhorar mensagem para o usuário
            msg = result.get("error", "Falha desconhecida Deriv")
            raise HTTPException(status_code=502, detail=msg)

        # Criar e publicar alerta de execução
        alert = {
            "id": str(uuid.uuid4()),
            "signal_id": str(uuid.uuid4()),
            "alert_type": "order_execution",
            "title": f"✅ Ordem via Deriv - {to_deriv_code(order.asset)}",
            "message": f"{order.direction.upper()} • ${order.amount} • exp {result.get('duration_value', order.expiration)}{result.get('duration_unit', 'm')} • via deriv",
            "priority": "high",
            "timestamp": datetime.now(),
            "signal_type": "buy" if order.direction == "call" else "sell",
            "symbol": to_deriv_code(order.asset),
            "iq_option_ready": False,
            "read": False,
        }
        try:
            await db.alerts.insert_one({**alert, "timestamp": alert["timestamp"]})
        except Exception:
            pass
        await broadcast_message(json.dumps({"type": "trading_alert", "data": alert}, default=str))

        return QuickOrderResponse(
            success=True,
            message="Ordem enviada via Deriv",
            order_id=str(result.get("contract_id")),
            echo={
                "asset": order.asset,
                "direction": order.direction,
                "amount": order.amount,
                "expiration": result.get("duration_value", order.expiration),
                "duration_unit": result.get("duration_unit", "m"),
                "account_type": order.account_type,
                "option_type": order.option_type,
                "provider": "deriv",
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro Deriv quick-order: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno Deriv: {e}")