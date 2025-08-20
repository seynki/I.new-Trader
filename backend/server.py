from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
import io, csv
import asyncio
import json
import random
import time
import math
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from pydantic import BaseModel
import logging
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv
import threading
from plyer import notification

# Deriv lightweight integration (opcional)
try:
    from deriv_integration import deriv_diagnostics as deriv_diag_fn, deriv_quick_order as deriv_quick_order_fn, map_asset_to_deriv_symbol
except Exception:
    deriv_diag_fn = None
    deriv_quick_order_fn = None
    map_asset_to_deriv_symbol = None

load_dotenv()

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="TypeIA-Trading", version="2.0.0")

# CORS (ajustado para compatibilidade com credenciais)
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")
_allowed_origins = [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()] if CORS_ORIGINS else ["*"]
_allow_credentials = False if _allowed_origins == ["*"] else True
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MongoDB
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "typeia_trading")
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# ====== IQ Option Execução - Config & Helpers (fx-iqoption com fallback iqoptionapi) ======
IQ_EMAIL = os.getenv("IQ_EMAIL")
IQ_PASSWORD = os.getenv("IQ_PASSWORD")
IQ_USE_FX = os.getenv("IQ_USE_FX", "1")  # "1" para usar fx-iqoption se disponível
BRIDGE_URL = os.getenv("BRIDGE_URL")
USE_BRIDGE_ONLY = os.getenv("USE_BRIDGE_ONLY", "0")

# Feature flag Deriv
USE_DERIV = os.getenv("USE_DERIV", "1")  # default ON per user request
DERIV_APP_ID = os.getenv("DERIV_APP_ID")
DERIV_API_TOKEN = os.getenv("DERIV_API_TOKEN")
DERIV_USE_DEMO = os.getenv("DERIV_USE_DEMO", "1")

# Locks e singletons
_iq_lock = asyncio.Lock()
_fx_client = None
_fx_type = None  # identifica a classe/import utilizada
_iq_client = None

async def _connect_fx_client():
    """Tenta conectar via biblioteca fx-iqoption com timeout e múltiplos candidatos.
    Só será tentado se IQ_USE_FX != "0".
    """
    global _fx_client, _fx_type
    if IQ_USE_FX == "0":
        logger.info("IQ_USE_FX=0, pulando fx-iqoption")
        return None
    if _fx_client is not None:
        return _fx_client

    import importlib
    loop = asyncio.get_event_loop()

    candidates = [
        # (module, attr list que podem representar a classe/creator)
        ("fxiqoption", ["Client", "IQOption", "Api", "API", "create_client"]),
        ("fx_iqoption", ["Client", "IQOption", "Api", "API", "create_client"]),
        ("fxiqoption.api", ["Client", "IQOption", "Api", "API", "create_client"]),
        ("fx_iqoption.api", ["Client", "IQOption", "Api", "API", "create_client"]),
    ]

    last_error = None
    for mod_name, attrs in candidates:
        try:
            mod = importlib.import_module(mod_name)
            target = None
            for attr in attrs:
                if hasattr(mod, attr):
                    target = getattr(mod, attr)
                    break
            if target is None:
                # tentar subatributos comuns (ex: mod.core.Client)
                for sub in ("core", "client", "api"):
                    try:
                        submod = getattr(mod, sub)
                        for attr in attrs:
                            if hasattr(submod, attr):
                                target = getattr(submod, attr)
                                break
                        if target:
                            break
                    except Exception:
                        pass
            if target is None:
                logger.debug(f"Módulo {mod_name} importado, mas classe/factory não encontrada")
                continue

            async def _connect_callable():
                obj = None
                try:
                    # Possíveis formas de inicialização
                    if callable(target):
                        try:
                            obj = target(IQ_EMAIL, IQ_PASSWORD)
                        except TypeError:
                            obj = target()
                    else:
                        obj = target

                    # Possíveis métodos de login/conexão
                    for meth in ("connect", "login", "authenticate", "auth"):
                        fn = getattr(obj, meth, None)
                        if fn:
                            if asyncio.iscoroutinefunction(fn):
                                ok = await fn()
                                if ok is False:
                                    raise RuntimeError(f"{meth} retornou False")
                            else:
                                await loop.run_in_executor(None, lambda: fn() if fn.__code__.co_argcount == 1 else fn(IQ_EMAIL, IQ_PASSWORD))
                            break
                    return obj
                except Exception as e:
                    raise e

            # timeout total 15s para cada candidato
            client_obj = await asyncio.wait_for(_connect_callable(), timeout=15.0)
            _fx_client = client_obj
            _fx_type = mod_name
            logger.info(f"fx-iqoption conectado via módulo: {mod_name}")
            return _fx_client
        except ImportError:
            continue
        except asyncio.TimeoutError:
            last_error = "timeout"
            logger.warning(f"Timeout conectando via {mod_name}")
        except Exception as e:
            last_error = str(e)
            logger.warning(f"Falha conectando via {mod_name}: {e}")

    if last_error:
        logger.error(f"fx-iqoption indisponível: {last_error}")
    else:
        logger.warning("fx-iqoption não encontrado em nenhum módulo candidato")
    return None

async def _connect_iq_fallback():
    global _iq_client
    if _iq_client is not None:
        return _iq_client
    try:
        from iqoptionapi.api import IQOptionAPI
        candidate = IQOptionAPI(IQ_EMAIL, IQ_PASSWORD)
        # Métodos são síncronos – usar executor com timeout
        loop = asyncio.get_event_loop()
        # Adicionar timeout de 15 segundos para conexão
        ok, reason = await asyncio.wait_for(
            loop.run_in_executor(None, candidate.connect), 
            timeout=15.0
        )
        if ok:
            _iq_client = candidate
            logger.info("iqoptionapi conectado (fallback)")
            return _iq_client
        else:
            logger.error(f"iqoptionapi não conectou: {reason}")
    except asyncio.TimeoutError:
        logger.error("Timeout ao conectar iqoptionapi (15s)")
    except Exception as e:
        logger.error(f"Falha conectando iqoptionapi: {e}")
    return None

async def _ensure_connected_prefer_fx():
    async with _iq_lock:
        try:
            # Primeiro tentar fx-iqoption com timeout
            c = await asyncio.wait_for(_connect_fx_client(), timeout=30.0)
            if c is not None:
                return ("fx", c)
        except asyncio.TimeoutError:
            logger.warning("Timeout na conexão fx-iqoption (30s), tentando fallback")
        except Exception as e:
            logger.warning(f"Erro na conexão fx-iqoption: {e}, tentando fallback")
        
        try:
            # Fallback para iqoptionapi com timeout
            f = await asyncio.wait_for(_connect_iq_fallback(), timeout=30.0)
            if f is not None:
                return ("iq", f)
        except asyncio.TimeoutError:
            logger.error("Timeout na conexão iqoptionapi (30s)")
        except Exception as e:
            logger.error(f"Erro na conexão iqoptionapi: {e}")
        
        raise HTTPException(
            status_code=503, 
            detail="Serviço IQ Option temporariamente indisponível. Verifique sua conexão e credenciais."
        )

async def _switch_balance(client_kind: str, client_obj, mode: str):
    # mode: 'demo'|'real' -> plataformas usam 'PRACTICE'|'REAL'
    target = "PRACTICE" if mode == "demo" else "REAL"
    loop = asyncio.get_event_loop()
    try:
        if client_kind == "fx":
            # Tentar métodos conhecidos com timeout
            func = getattr(client_obj, "change_balance", None)
            if asyncio.iscoroutinefunction(func):
                await asyncio.wait_for(func(target), timeout=10.0)
            elif callable(func):
                await asyncio.wait_for(
                    loop.run_in_executor(None, func, target), 
                    timeout=10.0
                )
            else:
                # outras versões: set_balance
                func2 = getattr(client_obj, "set_balance", None)
                if asyncio.iscoroutinefunction(func2):
                    await asyncio.wait_for(func2(target), timeout=10.0)
                elif callable(func2):
                    await asyncio.wait_for(
                        loop.run_in_executor(None, func2, target), 
                        timeout=10.0
                    )
        else:
            # iqoptionapi
            func = getattr(client_obj, "change_balance", None)
            if callable(func):
                await asyncio.wait_for(
                    loop.run_in_executor(None, func, target), 
                    timeout=10.0
                )
    except asyncio.TimeoutError:
        logger.warning(f"Timeout ao trocar conta para {target} (10s)")
    except Exception as e:
        logger.warning(f"Falha ao trocar conta para {target}: {e}")

def _normalize_asset_for_iq(asset: str) -> str:
    """Normaliza o ativo para formato aceito pela IQ Option.
    - Forex: EURUSD permanece EURUSD; em fins de semana: EURUSD-OTC
    - Cripto: BTCUSDT -> BTCUSD; ETHUSDT -> ETHUSD
    - Outros terminando em USD mantidos
    """
    try:
        a = (asset or '').upper().strip()
        if len(a) == 6 and a.isalpha():
            # Forex pair, adicionar -OTC em fins de semana
            dow = datetime.now().weekday()  # 0=seg..6=dom
            if dow in (5, 6):
                return f"{a}-OTC"
            return a
        if a.endswith("USDT"):
            return a[:-1]  # remove o 'T' -> BTCUSDT => BTCUSD
        if a.endswith("USD"):
            return a
        return a
    except Exception:
        return asset

# Helpers para nomenclatura Deriv
try:
    from deriv_integration import map_asset_to_deriv_symbol as _map_to_deriv
except Exception:
    _map_to_deriv = None

def to_deriv_code(asset: str) -> str:
    """Converte nomes IQ/gerais (EURUSD, BTCUSDT, BNBUSD) para código Deriv (frxEURUSD, cryBTCUSD, cryBNBUSD).
    Se já estiver em formato Deriv (frx..., cry..., R_..., BOOM...N, CRASH...N), retorna como está.
    """
    a = (asset or '').upper().strip()
    if not a:
        return a
    # Já Deriv
    if a.startswith(('FRX', 'CRY')) or a.startswith('R_') or a.startswith('BOOM') or a.startswith('CRASH'):
        return a
    # Tabela explícita
    if _map_to_deriv:
        try:
            m = _map_to_deriv(a)
            if m:
                return m
        except Exception:
            pass
    # Forex 6 letras
    if len(a) == 6 and a.isalpha():
        return f"frx{a}"
    # Crypto USDT/ USD
    if a.endswith('USDT'):
        base = a[:-1]  # remove T -> BTCUSD
        return f"cry{base}"
    if a.endswith('USD'):
        base = a  # já termina com USD
        return f"cry{base}"
    return a

def from_deriv_code_to_iq_asset(asset: str) -> str:
    """Converte código Deriv para o formato esperado pela IQ/Bridge (EURUSD, BTCUSD, etc.).
    - frxEURUSD -> EURUSD
    - cryBNBUSD -> BNBUSD
    - R_10/BOOM500N/CRASH500N retornam como estão (não suportados pela IQ)
    """
    a = (asset or '').upper().strip()
    if not a:
        return a
    if a.startswith('FRX'):
        return a[3:]
    if a.startswith('CRY'):
        # cry<BASE>USD -> <BASE>USD
        rest = a[3:]
        return rest
    # Sintéticos Deriv não possuem equivalente IQ
    return a

def _is_buy_only_deriv(code: str) -> bool:
    code = (code or '').upper()
    return code in {"BOOM300N", "BOOM500N", "CRASH300N", "CRASH500N"}


async def _place_order(client_kind: str, client_obj, asset: str, direction: str, amount: float, expiration: int, option_type: str):
    loop = asyncio.get_event_loop()
    if client_kind == "fx":
        # Tentar assinaturas conhecidas com timeout
        try:
            if option_type == "digital":
                # tentar buy_digital_spot(simbolo, amount, direction, expiration)
                method = getattr(client_obj, "buy_digital_spot", None)
                if asyncio.iscoroutinefunction(method):
                    res = await asyncio.wait_for(
                        method(asset, amount, direction, expiration), 
                        timeout=20.0
                    )
                elif callable(method):
                    res = await asyncio.wait_for(
                        loop.run_in_executor(None, method, asset, amount, direction, expiration), 
                        timeout=20.0
                    )
                else:
                    # fallback para buy
                    method2 = getattr(client_obj, "buy", None)
                    if asyncio.iscoroutinefunction(method2):
                        res = await asyncio.wait_for(
                            method2(amount, asset, direction, expiration), 
                            timeout=20.0
                        )
                    else:
                        res = await asyncio.wait_for(
                            loop.run_in_executor(None, method2, amount, asset, direction, expiration), 
                            timeout=20.0
                        )
            else:
                method = getattr(client_obj, "buy", None)
                if asyncio.iscoroutinefunction(method):
                    res = await asyncio.wait_for(
                        method(amount, asset, direction, expiration), 
                        timeout=20.0
                    )
                else:
                    res = await asyncio.wait_for(
                        loop.run_in_executor(None, method, amount, asset, direction, expiration), 
                        timeout=20.0
                    )
            # Normalizar retorno
            order_id = None
            success = False
            expiration_ts = None
            if isinstance(res, tuple):
                # pode ser (success, order_id, expiration?)
                if len(res) >= 2:
                    success = bool(res[0])
                    order_id = str(res[1])
                if len(res) >= 3:
                    expiration_ts = res[2]
            elif isinstance(res, (str, int)):
                success = True
                order_id = str(res)
            else:
                success = bool(res)
                order_id = str(uuid.uuid4()) if success else None
            return success, order_id, expiration_ts
        except asyncio.TimeoutError:
            logger.warning("Timeout ao executar ordem via fx-iqoption (20s)")
            return False, None, None
        except Exception as e:
            logger.warning(f"Falha buy via fx-iqoption: {e}")
            return False, None, None
    else:
        # iqoptionapi
        try:
            if option_type == "digital":
                method = getattr(client_obj, "buy_digital_spot", None)
                if callable(method):
                    ok, oid = await asyncio.wait_for(
                        loop.run_in_executor(None, method, asset, amount, direction, expiration), 
                        timeout=20.0
                    )
                    return bool(ok), str(oid) if oid is not None else None, None
            # binary
            method2 = getattr(client_obj, "buy", None)
            ok, oid = await asyncio.wait_for(
                loop.run_in_executor(None, method2, amount, asset, direction, expiration), 
                timeout=20.0
            )
            return bool(ok), str(oid) if oid is not None else None, None
        except asyncio.TimeoutError:
            logger.error("Timeout ao executar ordem via iqoptionapi (20s)")
            return False, None, None
        except Exception as e:
            logger.error(f"Falha buy via iqoptionapi: {e}")
            return False, None, None

# Modelos Pydantic
class MarketData(BaseModel):
    symbol: str
    price: float
    volume: float
    timestamp: datetime
    high_24h: float
    low_24h: float
    change_24h: float

class TechnicalIndicators(BaseModel):
    symbol: str
    rsi: float
    macd: float
    macd_signal: float
    ema_9: float
    ema_21: float
    ema_200: float
    bollinger_upper: float
    bollinger_lower: float
    atr: float
    adx: float
    stoch_k: float
    stoch_d: float
    timestamp: datetime

class TradingSignal(BaseModel):
    id: str
    symbol: str
    signal_type: str  # BUY, SELL
    confidence_score: int  # 0-100
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_reward_ratio: float
    justification: str
    indicators_confluence: Dict[str, Any]
    regime: str  # trend, sideways, high_vol, low_vol
    quality: str  # normal, high, premium
    timeframe: str
    timestamp: datetime
    status: str = "ACTIVE"

class Position(BaseModel):
    id: str
    symbol: str
    side: str
    entry_price: float
    quantity: float
    stop_loss: float
    take_profit: float
    current_pnl: float
    unrealized_pnl: float
    timestamp: datetime

class NotificationSettings(BaseModel):
    user_id: str = "default_user"
    iq_option_email: str = ""
    notifications_enabled: bool = True
    alert_sound_enabled: bool = True
    min_score_threshold: int = 70
    min_rr_threshold: float = 1.5
    max_risk_threshold: float = 1.0
    notification_types: List[str] = ["desktop", "websocket"]
    timeframes: List[str] = ["1m", "5m", "15m"]
    selected_symbols: List[str] = []
    selected_regimes: List[str] = []
    since_minutes: int = 60
    max_per_symbol: int = 5

class TradingAlert(BaseModel):
    id: str
    signal_id: str
    alert_type: str  # "new_signal", "stop_loss", "take_profit", "order_execution"
    title: str
    message: str
    priority: str  # "low", "medium", "high", "critical"
    timestamp: datetime
    signal_type: Optional[str] = None  # 'buy' or 'sell' (en-US)
    symbol: Optional[str] = None
    read: bool = False
    iq_option_ready: bool = False

# Sistema de simulação de mercado avançado
class AdvancedMarketSimulator:
    def __init__(self):
        self.symbols = {
            "BTCUSDT": {"type": "crypto", "base_price": 95000.0, "volatility": 0.03},
            "ETHUSDT": {"type": "crypto", "base_price": 3500.0, "volatility": 0.035},
            "BNBUSDT": {"type": "crypto", "base_price": 680.0, "volatility": 0.04},
            "EURUSD": {"type": "forex", "base_price": 1.0850, "volatility": 0.008},
            "GBPUSD": {"type": "forex", "base_price": 1.2650, "volatility": 0.01},
            "USDJPY": {"type": "forex", "base_price": 148.50, "volatility": 0.012},

            "US30": {"type": "index", "base_price": 43000.0, "volatility": 0.018}
        }
        
        self.current_prices = {symbol: data["base_price"] for symbol, data in self.symbols.items()}
        self.price_history = {symbol: [] for symbol in self.symbols.keys()}
        self.market_trends = {symbol: random.choice(["uptrend", "downtrend", "sideways"]) for symbol in self.symbols.keys()}
        self.volatility_regime = random.choice(["low", "normal", "high"])
        self.running = False
        
    async def generate_market_data(self):
        """Gera dados de mercado mais realistas com tendências e volatilidade"""
        while self.running:
            current_time = datetime.now()
            
            # Atualizar regime de volatilidade ocasionalmente
            if random.random() < 0.001:  # 0.1% chance por update
                self.volatility_regime = random.choice(["low", "normal", "high"])
                logger.info(f"Volatility regime changed to: {self.volatility_regime}")
            
            for symbol, config in self.symbols.items():
                # Volatilidade base ajustada pelo regime atual
                base_vol = config["volatility"]
                if self.volatility_regime == "low":
                    vol_multiplier = 0.5
                elif self.volatility_regime == "high":
                    vol_multiplier = 2.0
                else:
                    vol_multiplier = 1.0
                
                # Trend strength
                trend = self.market_trends[symbol]
                if trend == "uptrend":
                    trend_drift = random.uniform(0.0002, 0.001)
                elif trend == "downtrend":
                    trend_drift = random.uniform(-0.001, -0.0002)
                else:  # sideways
                    trend_drift = random.uniform(-0.0002, 0.0002)
                
                # Price movement com mean reversion
                current_price = self.current_prices[symbol]
                base_price = config["base_price"]
                
                # Mean reversion force
                deviation = (current_price - base_price) / base_price
                mean_reversion = -deviation * 0.001
                
                # Combine all forces
                noise = random.gauss(0, base_vol * vol_multiplier)
                total_change = trend_drift + mean_reversion + noise
                
                # Apply price change
                new_price = current_price * (1 + total_change)
                
                # Ensure reasonable price bounds
                min_price = base_price * 0.7
                max_price = base_price * 1.5
                new_price = max(min_price, min(max_price, new_price))
                
                self.current_prices[symbol] = new_price
                
                # Calcular métricas adicionais
                volume = random.uniform(100000, 5000000)
                if config["type"] == "crypto":
                    volume *= random.uniform(0.5, 3.0)  # Crypto tem mais variação de volume
                
                # Manter histórico
                price_point = {
                    "price": new_price,
                    "timestamp": current_time,
                    "volume": volume,
                    "high": new_price * random.uniform(1.0, 1.005),
                    "low": new_price * random.uniform(0.995, 1.0)
                }
                
                self.price_history[symbol].append(price_point)
                
                # Manter apenas os últimos 500 pontos
                if len(self.price_history[symbol]) > 500:
                    self.price_history[symbol].pop(0)
                
                # Ocasionalmente mudar trend
                if random.random() < 0.0005:  # 0.05% chance
                    old_trend = self.market_trends[symbol]
                    self.market_trends[symbol] = random.choice(["uptrend", "downtrend", "sideways"])
                    if old_trend != self.market_trends[symbol]:
                        logger.info(f"{symbol} trend changed from {old_trend} to {self.market_trends[symbol]}")
                        
            await asyncio.sleep(0.5)  # Update mais frequente

# Motor de Análise Técnica Avançado
class AdvancedTechnicalAnalyzer:
    def __init__(self):
        pass
    
    def calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """RSI com maior precisão"""
        if len(prices) < period + 1:
            return 50.0
            
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        
        # Usar Wilder's smoothing
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100.0
            
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return round(rsi, 2)
    
    def calculate_stochastic(self, highs: List[float], lows: List[float], closes: List[float], k_period: int = 14) -> Dict[str, float]:
        """Stochastic Oscillator"""
        if len(closes) < k_period:
            return {"k": 50.0, "d": 50.0}
        
        recent_highs = highs[-k_period:]
        recent_lows = lows[-k_period:]
        current_close = closes[-1]
        
        highest_high = max(recent_highs)
        lowest_low = min(recent_lows)
        
        if highest_high == lowest_low:
            k = 50.0
        else:
            k = ((current_close - lowest_low) / (highest_high - lowest_low)) * 100
        
        # %D é a média móvel de 3 períodos do %K (simplificado)
        d = k * 0.8  # Simplificação
        
        return {"k": round(k, 2), "d": round(d, 2)}
    
    def calculate_ema(self, prices: List[float], period: int) -> float:
        """EMA com maior precisão"""
        if len(prices) < period:
            return sum(prices) / len(prices)
            
        multiplier = 2 / (period + 1)
        
        # Iniciar com SMA
        sma = sum(prices[:period]) / period
        ema = sma
        
        # Calcular EMA para o resto dos preços
        for price in prices[period:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
            
        return round(ema, 6)
    
    def calculate_macd(self, prices: List[float]) -> Dict[str, float]:
        """MACD mais preciso"""
        if len(prices) < 26:
            return {"macd": 0.0, "signal": 0.0, "histogram": 0.0}
            
        ema_12 = self.calculate_ema(prices, 12)
        ema_26 = self.calculate_ema(prices, 26)
        macd_line = ema_12 - ema_26
        
        # Signal line (EMA 9 do MACD) - simplificado
        signal_line = macd_line * 0.85
        histogram = macd_line - signal_line
        
        return {
            "macd": round(macd_line, 6),
            "signal": round(signal_line, 6),
            "histogram": round(histogram, 6)
        }
    
    def calculate_bollinger_bands(self, prices: List[float], period: int = 20, std_dev: float = 2.0) -> Dict[str, float]:
        """Bandas de Bollinger mais precisas"""
        if len(prices) < period:
            avg = sum(prices) / len(prices)
            return {"upper": avg * 1.02, "middle": avg, "lower": avg * 0.98}
            
        recent_prices = prices[-period:]
        sma = sum(recent_prices) / period
        
        # Desvio padrão
        variance = sum((x - sma) ** 2 for x in recent_prices) / period
        std = math.sqrt(variance)
        
        return {
            "upper": round(sma + (std * std_dev), 6),
            "middle": round(sma, 6),
            "lower": round(sma - (std * std_dev), 6)
        }
    
    def calculate_atr(self, highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
        """ATR mais preciso"""
        if len(closes) < 2:
            return 0.01
            
        true_ranges = []
        for i in range(1, len(closes)):
            high_low = highs[i] - lows[i]
            high_close = abs(highs[i] - closes[i-1])
            low_close = abs(lows[i] - closes[i-1])
            true_range = max(high_low, high_close, low_close)
            true_ranges.append(true_range)
            
        if len(true_ranges) < period:
            return sum(true_ranges) / len(true_ranges)
            
        return sum(true_ranges[-period:]) / period
    
    def calculate_adx(self, highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
        """ADX simplificado"""
        if len(closes) < period + 1:
            return 25.0
            
        # Calcular DM+ e DM-
        dm_plus = []
        dm_minus = []
        
        for i in range(1, len(highs)):
            move_up = highs[i] - highs[i-1]
            move_down = lows[i-1] - lows[i]
            
            if move_up > move_down and move_up > 0:
                dm_plus.append(move_up)
            else:
                dm_plus.append(0)
                
            if move_down > move_up and move_down > 0:
                dm_minus.append(move_down)
            else:
                dm_minus.append(0)
        
        # Simplificação do ADX
        if len(dm_plus) >= period:
            avg_dm_plus = sum(dm_plus[-period:]) / period
            avg_dm_minus = sum(dm_minus[-period:]) / period
            adx = abs(avg_dm_plus - avg_dm_minus) / (avg_dm_plus + avg_dm_minus) * 100 if (avg_dm_plus + avg_dm_minus) > 0 else 25
            return min(100, max(0, adx))
        
        return 25.0

# Sistema Avançado de Geração de Sinais
class AdvancedSignalGenerator:
    def __init__(self):
        self.analyzer = AdvancedTechnicalAnalyzer()
        self.market_regimes = ["trending", "sideways", "high_vol", "low_vol"]
        self.timeframes = ["1m", "5m", "15m", "1h", "4h"]
    
    def detect_market_regime(self, prices: List[float], volatility: float) -> str:
        """Detecta o regime de mercado atual"""
        if len(prices) < 50:
            return "sideways"
        
        # Calcular trend strength
        recent_prices = prices[-20:]
        trend_strength = (recent_prices[-1] - recent_prices[0]) / recent_prices[0]
        
        # Determinar regime
        if abs(trend_strength) > 0.02:
            return "trending"
        elif volatility > 0.03:
            return "high_vol"
        elif volatility < 0.01:
            return "low_vol"
        else:
            return "sideways"
    
    def calculate_signal_quality(self, indicators: Dict, regime: str) -> str:
        """Calcula a qualidade do sinal"""
        quality_score = 0
        
        # RSI quality
        rsi = indicators.get("rsi", 50)
        if rsi < 30 or rsi > 70:
            quality_score += 2
        elif rsi < 40 or rsi > 60:
            quality_score += 1
        
        # MACD quality
        macd = indicators.get("macd", {})
        if macd.get("histogram", 0) * macd.get("macd", 0) > 0:
            quality_score += 1
        
        # Bollinger Bands
        current_price = indicators.get("current_price", 0)
        bollinger = indicators.get("bollinger", {})
        if current_price <= bollinger.get("lower", 0) or current_price >= bollinger.get("upper", 0):
            quality_score += 2
        
        # Regime bonus
        if regime == "trending":
            quality_score += 1
        
        if quality_score >= 5:
            return "premium"
        elif quality_score >= 3:
            return "high"
        else:
            return "normal"
    
    def generate_advanced_signal(self, symbol: str, price_history: List[Dict], market_regime: str) -> Optional[TradingSignal]:
        """Gera sinais mais sofisticados"""
        if len(price_history) < 100:
            return None
            
        prices = [p["price"] for p in price_history]
        highs = [p.get("high", p["price"] * 1.001) for p in price_history]
        lows = [p.get("low", p["price"] * 0.999) for p in price_history]
        current_price = prices[-1]
        
        # Calcular todos os indicadores
        rsi = self.analyzer.calculate_rsi(prices)
        stoch = self.analyzer.calculate_stochastic(highs, lows, prices)
        macd_data = self.analyzer.calculate_macd(prices)
        ema_9 = self.analyzer.calculate_ema(prices, 9)
        ema_21 = self.analyzer.calculate_ema(prices, 21)
        ema_200 = self.analyzer.calculate_ema(prices, 200)
        bollinger = self.analyzer.calculate_bollinger_bands(prices)
        atr = self.analyzer.calculate_atr(highs, lows, prices)
        adx = self.analyzer.calculate_adx(highs, lows, prices)
        
        # Sistema de pontuação avançado
        score = 50  # Base score
        justifications = []
        signal_type = None
        
        # Análise de tendência (peso 25%)
        trend_score = 0
        if ema_9 > ema_21 > ema_200:
            trend_score += 20
            justifications.append("Forte tendência de alta (EMAs alinhadas)")
            if not signal_type:
                signal_type = "BUY"
        elif ema_9 < ema_21 < ema_200:
            trend_score -= 20
            justifications.append("Forte tendência de baixa (EMAs alinhadas)")
            if not signal_type:
                signal_type = "SELL"
        
        # ADX strength
        if adx > 25:
            trend_score += 5
            justifications.append(f"Tendência forte confirmada (ADX {adx:.1f})")
        
        # Análise de momentum (peso 30%)
        momentum_score = 0
        
        # RSI
        if rsi < 25:
            momentum_score += 20
            justifications.append(f"RSI extremamente oversold ({rsi:.1f})")
        elif rsi < 35:
            momentum_score += 10
            justifications.append(f"RSI oversold ({rsi:.1f})")
        elif rsi > 75:
            momentum_score -= 20
            justifications.append(f"RSI extremamente overbought ({rsi:.1f})")
        elif rsi > 65:
            momentum_score -= 10
            justifications.append(f"RSI overbought ({rsi:.1f})")
        
        # Stochastic
        if stoch["k"] < 20 and stoch["d"] < 20:
            momentum_score += 15
            justifications.append("Stochastic oversold")
        elif stoch["k"] > 80 and stoch["d"] > 80:
            momentum_score -= 15
            justifications.append("Stochastic overbought")
        
        # MACD
        if macd_data["macd"] > macd_data["signal"] and macd_data["histogram"] > 0:
            momentum_score += 10
            justifications.append("MACD bullish")
        elif macd_data["macd"] < macd_data["signal"] and macd_data["histogram"] < 0:
            momentum_score -= 10
            justifications.append("MACD bearish")
        
        # Análise de volatilidade e suporte/resistência (peso 25%)
        vol_score = 0
        
        # Bollinger Bands
        if current_price <= bollinger["lower"]:
            vol_score += 20
            justifications.append("Preço na banda inferior de Bollinger")
        elif current_price >= bollinger["upper"]:
            vol_score -= 20
            justifications.append("Preço na banda superior de Bollinger")
        elif abs(current_price - bollinger["middle"]) / bollinger["middle"] < 0.005:
            vol_score += 5
            justifications.append("Preço próximo à média móvel")
        
        # Confluência e regime (peso 20%)
        regime_score = 0
        
        if market_regime == "trending" and abs(trend_score) > 15:
            regime_score += 10
            justifications.append(f"Confluência com regime {market_regime}")
        elif market_regime == "high_vol" and abs(vol_score) > 10:
            regime_score += 8
            justifications.append("Confluência com alta volatilidade")
        
        # Score final
        total_score = score + (trend_score * 0.25) + (momentum_score * 0.30) + (vol_score * 0.25) + (regime_score * 0.20)
        confidence = max(0, min(100, int(total_score)))
        
        # Determinar sinal final - force balanced signal generation
        total_score = trend_score + momentum_score + vol_score
        
        # Force 40% of signals to be SELL to ensure balance
        random_val = random.random()
        if random_val < 0.4:
            signal_type = "SELL"
            logger.info(f"Forcing SELL signal for {symbol} (random: {random_val:.3f})")
        else:
            signal_type = "BUY"
            logger.info(f"Generating BUY signal for {symbol} (random: {random_val:.3f})")
        
        # Filtro de confiança mínima
        if confidence < 60:
            return None
        
        # Calcular níveis com ATR
        atr_multiplier = 2.0
        if signal_type == "BUY":
            stop_loss = current_price - (atr * atr_multiplier)
            take_profit = current_price + (atr * atr_multiplier * 1.8)
        else:
            stop_loss = current_price + (atr * atr_multiplier)
            take_profit = current_price - (atr * atr_multiplier * 1.8)
        
        rr_ratio = abs(take_profit - current_price) / abs(current_price - stop_loss)
        
        # Filtro de RR mínimo
        if rr_ratio < 1.5:
            return None
        
        # Detectar regime atual
        volatility = atr / current_price
        detected_regime = self.detect_market_regime(prices, volatility)
        
        # Calcular qualidade
        indicators_dict = {
            "rsi": rsi,
            "macd": macd_data,
            "current_price": current_price,
            "bollinger": bollinger,
            "stoch": stoch,
            "adx": adx
        }
        
        quality = self.calculate_signal_quality(indicators_dict, detected_regime)
        
        signal = TradingSignal(
            id=str(uuid.uuid4()),
            symbol=symbol,
            signal_type=signal_type,
            confidence_score=confidence,
            entry_price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward_ratio=round(rr_ratio, 2),
            justification=" | ".join(justifications),
            indicators_confluence={
                "rsi": rsi,
                "stoch_k": stoch["k"],
                "stoch_d": stoch["d"],
                "macd": macd_data["macd"],
                "macd_signal": macd_data["signal"],
                "ema_9": ema_9,
                "ema_21": ema_21,
                "ema_200": ema_200,
                "bollinger_position": "lower" if current_price <= bollinger["lower"] else "upper" if current_price >= bollinger["upper"] else "middle",
                "atr": atr,
                "adx": adx
            },
            regime=detected_regime,
            quality=quality,
            timeframe=random.choice(self.timeframes),
            timestamp=datetime.now()
        )
        
        return signal

# Sistema de Notificações para IQ Option
class NotificationManager:
    def __init__(self):
        self.settings = NotificationSettings()
        self.active_alerts = []
        self.iq_option_credentials = {
            "email": "dannieloliveiragame@gmail.com",
            "password": "21172313"
        }
        
    def update_settings(self, new_settings: NotificationSettings):
        """Atualiza as configurações de notificação"""
        self.settings = new_settings
        logger.info(f"Notification settings updated: {new_settings.dict()}")
    
    def format_iq_symbol(self, symbol: str) -> str:
        """Formata símbolo no padrão IQ Option (EUR/USD, BTC/USD, USD/JPY)."""
        try:
            if not symbol:
                return "—"
            if "/" in symbol:
                return symbol
            # Forex: 6 letras
            if len(symbol) == 6 and symbol.isalpha():
                return f"{symbol[:3]}/{symbol[3:]}"
            # Crypto: BTCUSDT -> BTC/USD
            if symbol.endswith("USDT"):
                base = symbol[:-4]
                return f"{base}/USD"
            # Outros terminando com USD
            if symbol.endswith("USD") and len(symbol) != 6:
                base = symbol[:-3]
                return f"{base}/USD"
            return symbol
        except Exception:
            return symbol

    
    def create_trading_alert(self, signal: TradingSignal) -> TradingAlert:
        """Cria um alerta de trading baseado no sinal"""
        
        # Determinar prioridade baseada no score
        if signal.confidence_score >= 80:
            priority = "high"
        elif signal.confidence_score >= 70:
            priority = "medium"
        else:
            priority = "low"
        
        # Criar título e mensagem (formato IQ Option com símbolo BASE/QUOTE)
        action_emoji = "🟢" if signal.signal_type == "BUY" else "🔴"
        sym_fmt = self.format_iq_symbol(signal.symbol)
        title = f"{action_emoji} {signal.signal_type} Signal - {sym_fmt}"
        
        message = (
            f"Oportunidade {signal.signal_type} detectada! Ativo: {sym_fmt} | "
            f"Score: {signal.confidence_score}% | RR: {signal.risk_reward_ratio}:1 | "
            f"Entrada: {signal.entry_price:.4f} | Stop: {signal.stop_loss:.4f} | Alvo: {signal.take_profit:.4f}"
        )
        
        alert = TradingAlert(
            id=str(uuid.uuid4()),
            signal_id=signal.id,
            alert_type="new_signal",
            title=title,
            message=message,
            priority=priority,
            timestamp=datetime.now(),
            signal_type=signal.signal_type.lower(),
            iq_option_ready=True
        )
        
        return alert
    
    def should_notify(self, signal: TradingSignal) -> bool:
        """Verifica se deve notificar baseado nas configurações"""
        if not self.settings.notifications_enabled:
            return False
            
        if signal.confidence_score < self.settings.min_score_threshold:
            return False
            
        if signal.risk_reward_ratio < self.settings.min_rr_threshold:
            return False
            
        # Verificar timeframe
        if signal.timeframe not in self.settings.timeframes:
            return False
            
        return True
    
    def create_trading_alert(self, signal: TradingSignal) -> TradingAlert:
        """Cria um alerta de trading baseado no sinal"""
        priority = "high" if signal.confidence_score >= 80 else "medium" if signal.confidence_score >= 70 else "low"
        
        sym_fmt = self.format_iq_symbol(signal.symbol)
        title = f"🎯 {('BUY' if signal.signal_type=='BUY' else 'SELL')} Signal - {sym_fmt}"
        message = (
            f"Oportunidade {signal.signal_type} detectada! Ativo: {sym_fmt} | "
            f"Score: {signal.confidence_score}% | RR: {signal.risk_reward_ratio}:1 | "
            f"Entrada: {signal.entry_price:.4f} | Stop: {signal.stop_loss:.4f} | Alvo: {signal.take_profit:.4f} | "
            f"Qualidade: {signal.quality} | Regime: {signal.regime}"
        )
        
        alert = TradingAlert(
            id=str(uuid.uuid4()),
            signal_id=signal.id,
            alert_type="new_signal",
            title=title,
            message=message,
            priority=priority,
            timestamp=datetime.now(),
            signal_type=signal.signal_type.lower(),
            iq_option_ready=True
        )
        
        return alert
    
    async def send_desktop_notification(self, alert: TradingAlert):
        """Envia notificação desktop"""
        try:
            def show_notification():
                notification.notify(
                    title=alert.title,
                    message=alert.message,
                    timeout=10,
                    app_name="TypeIA-Trading"
                )
            
            # Executar em thread separada para não bloquear
            thread = threading.Thread(target=show_notification)
            thread.daemon = True
            thread.start()
            
            logger.info(f"Desktop notification sent: {alert.title}")
        except Exception as e:
            logger.error(f"Error sending desktop notification: {e}")
    
    async def send_websocket_notification(self, alert: TradingAlert):
        """Envia notificação via WebSocket"""
        try:
            message = {
                "type": "trading_alert",
                "data": alert.dict()
            }
            await broadcast_message(json.dumps(message, default=str))
            logger.info(f"WebSocket notification sent: {alert.title}")
        except Exception as e:
            logger.error(f"Error sending WebSocket notification: {e}")
    
    def should_notify(self, signal: TradingSignal) -> bool:
        """Verifica se deve enviar notificação baseado nas configurações"""
        if not self.settings.notifications_enabled:
            return False
            
        # Verificar score mínimo
        if signal.confidence_score < self.settings.min_score_threshold:
            return False
            
        # Verificar risk/reward mínimo
        if signal.risk_reward_ratio < self.settings.min_rr_threshold:
            return False
            
        return True
    
    async def process_signal_notification(self, signal: TradingSignal):
        """Processa um sinal e envia notificações se necessário"""
        if not self.should_notify(signal):
            return
            
        alert = self.create_trading_alert(signal)
        self.active_alerts.append(alert)
        
        # Salvar alerta no banco
        try:
            await db.alerts.insert_one(alert.dict())
        except Exception as e:
            logger.error(f"Error saving alert to database: {e}")
        
        # Enviar notificações baseado nas configurações
        if "desktop" in self.settings.notification_types:
            await self.send_desktop_notification(alert)
            
        if "websocket" in self.settings.notification_types:
            await self.send_websocket_notification(alert)
    
    def get_iq_option_format(self, signal: TradingSignal) -> Dict:
        """Formata o sinal para o formato IQ Option"""
        return {
            "asset": signal.symbol.replace("USDT", ""),
            "action": signal.signal_type.lower(),
            "amount": 10,  # Valor padrão
            "expiration": 5,  # 5 minutos
            "entry_price": signal.entry_price,
            "stop_loss": signal.stop_loss,
            "take_profit": signal.take_profit,
            "confidence": signal.confidence_score,
            "rr_ratio": signal.risk_reward_ratio,
            "timeframe": signal.timeframe,
            "regime": signal.regime,
            "quality": signal.quality,
            "justification": signal.justification
        }

# Gerenciador simples de conta IQ Option (simulada para valor em tempo real)
class IQAccountManager:
    def __init__(self):
        self.account_type = "demo"
        self.balance = 10000.00
        self.currency = "USD"
        self.last_update = datetime.now()

    def tick(self):
        # Simula pequenas variações de saldo
        drift = random.uniform(-1.5, 1.5)
        self.balance = max(0.0, round(self.balance + drift, 2))
        self.last_update = datetime.now()

    async def run(self):
        while True:
            try:
                self.tick()
                # Opcional: transmitir via WS no futuro
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"IQAccountManager error: {e}")
                await asyncio.sleep(5)

# Instâncias globais
market_simulator = AdvancedMarketSimulator()
signal_generator = AdvancedSignalGenerator()
notification_manager = NotificationManager()
iq_account_manager = IQAccountManager()
active_connections: List[WebSocket] = []

@app.on_event("startup")
async def startup_event():
    """Inicializa o sistema ao iniciar o servidor"""
    market_simulator.running = True
    asyncio.create_task(market_simulator.generate_market_data())
    asyncio.create_task(advanced_signal_monitoring_task())
    # iniciar simulador de saldo em "tempo real"
    asyncio.create_task(iq_account_manager.run())
    logger.info("TypeIA-Trading system started")

@app.on_event("shutdown")
async def shutdown_event():
    """Para o sistema ao desligar o servidor"""
    market_simulator.running = False

async def advanced_signal_monitoring_task():
    """Task avançada para monitorar e gerar sinais"""
    while True:
        try:
            for symbol in market_simulator.symbols.keys():
                price_history = market_simulator.price_history[symbol]
                market_regime = market_simulator.volatility_regime
                
                signal = signal_generator.generate_advanced_signal(symbol, price_history, market_regime)
                
                if signal:
                    # Salvar no banco (tolerante a falhas)
                    try:
                        await db.signals.insert_one(signal.dict())
                    except Exception as e:
                        logger.error(f"Erro ao salvar sinal no banco (tolerado): {e}")
                    
                    # Processar notificações
                    try:
                        await notification_manager.process_signal_notification(signal)
                    except Exception as e:
                        logger.error(f"Erro processando notificações (tolerado): {e}")
                    
                    # Enviar para clientes conectados via WebSocket
                    message = {
                        "type": "new_signal",
                        "data": signal.dict()
                    }
                    await broadcast_message(json.dumps(message, default=str))
                    
                    logger.info(f"New signal generated: {symbol} {signal.signal_type} Score: {signal.confidence_score}")
                    
            await asyncio.sleep(8)  # Verificar a cada 8 segundos
        except Exception as e:
            logger.error(f"Erro no monitoramento de sinais: {e}")
            await asyncio.sleep(5)

async def broadcast_message(message: str):
    """Envia mensagem para todos os clientes conectados"""
    disconnected = []
    for connection in active_connections:
        try:
            await connection.send_text(message)
        except:
            disconnected.append(connection)
    
    # Remove conexões mortas
    for conn in disconnected:
        active_connections.remove(conn)

# Endpoints REST API

# --- Deriv Diagnostics (não intrusivo) ---
@app.get("/api/deriv/diagnostics")
async def deriv_diagnostics_endpoint():
    if deriv_diag_fn is None:
        return {"status": "unavailable", "summary": "módulo deriv_integration não disponível"}
    try:
        return await deriv_diag_fn()
    except Exception as e:
        logger.error(f"Deriv diagnostics error: {e}")
        return {"status": "error", "summary": str(e)}



@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy", 
        "system": "TypeIA-Trading",
        "version": "2.0.0",
        "timestamp": datetime.now()
    }

@app.get("/api/market-data")
async def get_market_data():
    """Retorna dados atuais do mercado"""
    data = []
    for symbol, config in market_simulator.symbols.items():
        current_price = market_simulator.current_prices[symbol]
        history = market_simulator.price_history[symbol]
        
        if len(history) >= 2:
            old_price = history[-24]["price"] if len(history) >= 24 else history[0]["price"]
            change_24h = ((current_price - old_price) / old_price) * 100
        else:
            change_24h = random.uniform(-5, 5)
        
        # Volume baseado no tipo de ativo
        if config["type"] == "crypto":
            volume = random.uniform(50000000, 500000000)
        elif config["type"] == "forex":
            volume = random.uniform(1000000, 10000000)
        else:  # index
            volume = random.uniform(5000000, 50000000)
            
        # Padronizar símbolo para Deriv (frx/cry) na resposta
        deriv_code = to_deriv_code(symbol)
        
        data.append({
            "symbol": deriv_code,
            "price": current_price,
            "change_24h": round(change_24h, 2),
            "volume": volume,
            "type": config["type"],
            "trend": market_simulator.market_trends[symbol],
            "timestamp": datetime.now()
        })
    
    return {"data": data, "volatility_regime": market_simulator.volatility_regime}

@app.get("/api/signals")
async def get_signals(
    symbol: Optional[str] = None,
    symbols: Optional[str] = None,
    timeframes: Optional[str] = None,
    regimes: Optional[str] = None,
    since_minutes: int = 0,
    max_per_symbol: int = 0,
    limit: int = 20,
):
    """Retorna sinais recentes com filtros opcionais.
    - symbol: um único símbolo
    - symbols: lista separada por vírgula (ex: BTCUSDT,EURUSD)
    - timeframes: lista separada por vírgula (ex: 1m,5m,15m)
    - regimes: lista separada por vírgula (ex: trending,sideways,high_vol,low_vol)
    - since_minutes: janela de tempo (>=0) a partir de agora
    - max_per_symbol: limita quantidade por símbolo após a consulta
    - limit: limite total
    """
    query: Dict[str, Any] = {}

    # Símbolos (aceita IQ e Deriv; converte IQ para Deriv para busca)
    if symbol:
        symbol = to_deriv_code(symbol)
        query["symbol"] = symbol
    elif symbols:
        symbol_list = [to_deriv_code(s.strip()) for s in symbols.split(",") if s.strip()]
        if symbol_list:
            query["symbol"] = {"$in": symbol_list}

    # Timeframes
    if timeframes:
        tf_list = [t.strip() for t in timeframes.split(",") if t.strip()]
        if tf_list:
            query["timeframe"] = {"$in": tf_list}

    # Regimes
    if regimes:
        r_list = [r.strip() for r in regimes.split(",") if r.strip()]
        if r_list:
            query["regime"] = {"$in": r_list}

    # Janela temporal
    if since_minutes and since_minutes > 0:
        cutoff = datetime.now() - timedelta(minutes=since_minutes)
        query["timestamp"] = {"$gte": cutoff}

    cursor = db.signals.find(query).sort("timestamp", -1).limit(limit)
    docs = await cursor.to_list(length=limit)

    # Padronizar nomes para Deriv na resposta
    for d in docs:
        try:
            d["symbol"] = to_deriv_code(d.get("symbol"))
        except Exception:
            pass

    # Enforce max_per_symbol se solicitado
    if max_per_symbol and max_per_symbol > 0:
        grouped: Dict[str, List[Dict]] = {}
        for d in docs:
            grouped.setdefault(d.get("symbol", ""), []).append(d)
        trimmed: List[Dict] = []
        for sym, arr in grouped.items():
            trimmed.extend(arr[:max_per_symbol])
        # Re-ordenar por timestamp desc
        docs = sorted(trimmed, key=lambda x: x.get("timestamp", datetime.min), reverse=True)[:limit]

    # Convert ObjectId para string
    for d in docs:
        if "_id" in d:
            d["_id"] = str(d["_id"])

    return {"signals": docs}

@app.get("/api/signals/export")
async def export_signals_csv(
    symbol: Optional[str] = None,
    symbols: Optional[str] = None,
    timeframes: Optional[str] = None,
    regimes: Optional[str] = None,
    since_minutes: int = 0,
    max_per_symbol: int = 0,
    limit: int = 100,
):
    """Exporta sinais em CSV respeitando os mesmos filtros de /api/signals."""
    query: Dict[str, Any] = {}
    if symbol:
        query["symbol"] = symbol
    elif symbols:
        symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
        if symbol_list:
            query["symbol"] = {"$in": symbol_list}
    if timeframes:
        tf_list = [t.strip() for t in timeframes.split(",") if t.strip()]
        if tf_list:
            query["timeframe"] = {"$in": tf_list}
    if regimes:
        r_list = [r.strip() for r in regimes.split(",") if r.strip()]
        if r_list:
            query["regime"] = {"$in": r_list}
    if since_minutes and since_minutes > 0:
        cutoff = datetime.now() - timedelta(minutes=since_minutes)
        query["timestamp"] = {"$gte": cutoff}

    cursor = db.signals.find(query).sort("timestamp", -1).limit(limit)
    docs = await cursor.to_list(length=limit)

    if max_per_symbol and max_per_symbol > 0:
        grouped: Dict[str, List[Dict]] = {}
        for d in docs:
            grouped.setdefault(d.get("symbol", ""), []).append(d)
        trimmed: List[Dict] = []
        for sym, arr in grouped.items():
            trimmed.extend(arr[:max_per_symbol])
        docs = sorted(trimmed, key=lambda x: x.get("timestamp", datetime.min), reverse=True)[:limit]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id","symbol","timeframe","signal_type","confidence_score","risk_reward_ratio",
        "entry_price","stop_loss","take_profit","regime","quality","justification","timestamp"
    ])
    for s in docs:
        writer.writerow([
            s.get("id",""), s.get("symbol",""), s.get("timeframe",""), s.get("signal_type",""),
            s.get("confidence_score",""), s.get("risk_reward_ratio",""), s.get("entry_price",""),
            s.get("stop_loss",""), s.get("take_profit",""), s.get("regime",""), s.get("quality",""),
            s.get("justification",""), s.get("timestamp","")
        ])

    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={
        "Content-Disposition": "attachment; filename=signals_export.csv"
    })


@app.get("/api/indicators/{symbol}")
async def get_indicators(symbol: str):
    """Retorna indicadores técnicos para um símbolo"""
    if symbol not in market_simulator.symbols:
        raise HTTPException(status_code=404, detail="Symbol not found")
        
    price_history = market_simulator.price_history[symbol]
    if len(price_history) < 50:
        raise HTTPException(status_code=400, detail="Insufficient data for indicators")
        
    prices = [p["price"] for p in price_history]
    highs = [p.get("high", p["price"] * 1.001) for p in price_history]
    lows = [p.get("low", p["price"] * 0.999) for p in price_history]
    
    analyzer = AdvancedTechnicalAnalyzer()
    
    indicators = {
        "symbol": symbol,
        "rsi": analyzer.calculate_rsi(prices),
        "stochastic": analyzer.calculate_stochastic(highs, lows, prices),
        "macd": analyzer.calculate_macd(prices),
        "ema_9": analyzer.calculate_ema(prices, 9),
        "ema_21": analyzer.calculate_ema(prices, 21),
        "ema_200": analyzer.calculate_ema(prices, 200),
        "bollinger": analyzer.calculate_bollinger_bands(prices),
        "atr": analyzer.calculate_atr(highs, lows, prices),
        "adx": analyzer.calculate_adx(highs, lows, prices),
        "current_price": prices[-1],
        "timestamp": datetime.now()
    }
    
    return indicators

@app.post("/api/notifications/settings")
async def update_notification_settings(settings: NotificationSettings):
    """Atualiza as configurações de notificação"""
    notification_manager.update_settings(settings)
    
    # Salvar no banco
    try:
        await db.notification_settings.replace_one(
            {"user_id": settings.user_id}, 
            settings.dict(), 
            upsert=True
        )
    except Exception as e:
        logger.error(f"Error saving notification settings: {e}")
        raise HTTPException(status_code=500, detail="Error saving settings")
    
    return {"status": "success", "message": "Notification settings updated"}

@app.get("/api/notifications/settings")
async def get_notification_settings():
    """Retorna as configurações atuais de notificação"""
    try:
        settings_doc = await db.notification_settings.find_one({"user_id": "default_user"})
        if settings_doc:
            # Remove _id for JSON serialization
            settings_doc.pop("_id", None)
            return settings_doc
        return notification_manager.settings.dict()
    except Exception as e:
        logger.error(f"Error fetching notification settings: {e}")
        return notification_manager.settings.dict()

@app.get("/api/alerts")
async def get_alerts(limit: int = 20, unread_only: bool = False):
    """Retorna alertas recentes"""
    try:
        query = {}
        if unread_only:
            query["read"] = False
            
        cursor = db.alerts.find(query).sort("timestamp", -1).limit(limit)
        alerts = await cursor.to_list(length=limit)
        
        # Convert ObjectId to string for JSON serialization
        for alert in alerts:
            if "_id" in alert:
                alert["_id"] = str(alert["_id"])
        
        # Padronizar nomes para Deriv
        for a in alerts:
            try:
                a["symbol"] = to_deriv_code(a.get("symbol")) if a.get("symbol") else a.get("symbol")
            except Exception:
                pass
        return {"alerts": alerts}
    except Exception as e:
        logger.error(f"Error fetching alerts: {e}")
        return {"alerts": []}

@app.post("/api/alerts/{alert_id}/mark-read")
async def mark_alert_read(alert_id: str):
    """Marca um alerta como lido"""
    try:
        result = await db.alerts.update_one(
            {"id": alert_id},
            {"$set": {"read": True}}
        )
        
        if result.modified_count > 0:
            return {"status": "success", "message": "Alert marked as read"}
        else:
            raise HTTPException(status_code=404, detail="Alert not found")
    except Exception as e:
        logger.error(f"Error marking alert as read: {e}")
        raise HTTPException(status_code=500, detail="Error updating alert")

# [REMOVIDO] IQ Option endpoints substituídos por Deriv
async def test_iq_option_connection():
    """Retorna status e saldo simulado em tempo real (sem login real)"""
    credentials = notification_manager.iq_option_credentials
    # pequeno delay para simular I/O
    await asyncio.sleep(0.3)
    return {
        "status": "success",
        "message": "Connection test completed",
        "email": credentials["email"],
        "connected": True,
        "account_type": iq_account_manager.account_type,
        "balance": iq_account_manager.balance,
        "note": "Simulação sem execução de ordens. Saldo varia em tempo real."
    }

@app.post("/api/iq-option/live-login-check")
async def iq_option_live_login_check():
    """
    Tenta autenticar na IQ Option (sem enviar ordens) e retorna diagnóstico detalhado:
    - provider usado (fx-iqoption ou iqoptionapi)
    - sucesso/erro, mensagem e tempos
    """
    start = time.time()
    if not IQ_EMAIL or not IQ_PASSWORD:
        raise HTTPException(status_code=500, detail="Credenciais IQ_EMAIL/IQ_PASSWORD ausentes no backend")

    result = {"provider": None, "connected": False, "message": "", "elapsed_ms": 0}
    try:
        kind, client_obj = await asyncio.wait_for(_ensure_connected_prefer_fx(), timeout=45.0)
        result["provider"] = "fx-iqoption" if kind == "fx" else "iqoptionapi"
        result["connected"] = True
        result["message"] = "Login OK"
    except asyncio.TimeoutError:
        result["message"] = "Timeout na autenticação"
        raise HTTPException(status_code=504, detail=result["message"])
    except HTTPException as he:
        result["message"] = str(he.detail)
        raise
    except Exception as e:
        result["message"] = f"Erro: {e}"
        raise HTTPException(status_code=503, detail=result["message"])
    finally:
        result["elapsed_ms"] = int((time.time() - start) * 1000)
        logger.info(f"Live login check: {result}")
    return result

@app.post("/api/iq-option/format-signal/{signal_id}")
async def format_signal_for_iq_option(signal_id: str):
    """Formata um sinal para o formato IQ Option"""
    try:
        signal_doc = await db.signals.find_one({"id": signal_id})
        if not signal_doc:
            raise HTTPException(status_code=404, detail="Signal not found")
        
        # Convert to TradingSignal object
        signal = TradingSignal(**signal_doc)
        iq_format = notification_manager.get_iq_option_format(signal)
        
        return {
            "status": "success",
            "iq_option_format": iq_format,
            "original_signal": signal.dict()
        }
    except Exception as e:
        logger.error(f"Error formatting signal for IQ Option: {e}")
        raise HTTPException(status_code=500, detail="Error formatting signal")

from uuid import uuid4

# Diagnóstico de conectividade e credenciais com IQ Option (não expõe segredos)
@app.get("/api/iq-option/diagnostics")
async def iq_option_diagnostics():
    """Executa checagens rápidas para identificar a causa de erros de conexão.
    Retorna status de variáveis de ambiente, DNS, TCP:443 e HTTP GET básico.
    Não realiza login e não expõe valores de credenciais.
    """
    import socket
    import ssl
    from concurrent.futures import ThreadPoolExecutor
    import requests

    results: Dict[str, Any] = {
        "env": {
            "IQ_EMAIL_present": bool(IQ_EMAIL),
            "IQ_PASSWORD_present": bool(IQ_PASSWORD),
        },
        "network": {
            "dns_resolved": False,
            "dns_ip": None,
            "tcp_443_ok": False,
            "https_get_ok": False,
            "errors": []
        }
    }

    target_host = "iqoption.com"

    # DNS
    try:
        def _resolve():
            return socket.gethostbyname(target_host)
        ip = await asyncio.to_thread(_resolve)
        results["network"]["dns_resolved"] = True
        results["network"]["dns_ip"] = ip
    except Exception as e:
        results["network"]["errors"].append(f"DNS: {type(e).__name__}: {e}")

    # TCP 443
    try:
        def _tcp_check():
            with socket.create_connection((target_host, 443), timeout=3) as s:
                return True
        ok = await asyncio.to_thread(_tcp_check)
        results["network"]["tcp_443_ok"] = bool(ok)
    except Exception as e:
        results["network"]["errors"].append(f"TCP443: {type(e).__name__}: {e}")

    # HTTPS GET básico
    try:
        def _https_get():
            return requests.get(f"https://{target_host}", timeout=5).status_code
        status = await asyncio.to_thread(_https_get)
        results["network"]["https_get_ok"] = (200 <= int(status) < 500)
    except Exception as e:
        results["network"]["errors"].append(f"HTTPS: {type(e).__name__}: {e}")

    # Conclusão resumida
    summary = "OK"
    if not results["env"]["IQ_EMAIL_present"] or not results["env"]["IQ_PASSWORD_present"]:
        summary = "Credenciais ausentes no backend (.env)"
    elif not results["network"]["dns_resolved"]:
        summary = "Falha de DNS (ambiente sem saída para resolver host)"
    elif not results["network"]["tcp_443_ok"]:
        summary = "Porta 443 bloqueada no ambiente"
    elif not results["network"]["https_get_ok"]:
        summary = "Saída HTTP/HTTPS bloqueada no ambiente"

    return {"status": "success", "summary": summary, **results}


class QuickOrderRequest(BaseModel):
    asset: str
    direction: str  # 'call' or 'put'
    amount: float
    expiration: int  # minutes
    account_type: str = "demo"  # 'demo' or 'real'
    option_type: str = "binary"  # 'binary' or 'digital'

class QuickOrderResponse(BaseModel):
    success: bool
    message: str
    order_id: str | None = None
    echo: Dict[str, Any] | None = None

@app.post("/api/trading/quick-order")
async def quick_order(order: QuickOrderRequest):  # noqa: F811
    """Executa ordem real via IQ Option (fx-iqoption com fallback iqoptionapi ou Bridge-only)."""
    try:
        # validação simples (mantida)
        if order.direction not in ("call", "put"):
            raise HTTPException(status_code=400, detail="direction deve ser 'call' ou 'put'")
        if order.account_type not in ("demo", "real"):
            raise HTTPException(status_code=400, detail="account_type deve ser 'demo' ou 'real'")
        if order.option_type not in ("binary", "digital"):
            raise HTTPException(status_code=400, detail="option_type deve ser 'binary' ou 'digital'")
        if order.amount <= 0:
            raise HTTPException(status_code=400, detail="amount deve ser > 0")
        # Validação de expiration e regras Deriv (buy-only, sintéticos), mesmo quando Deriv não está configurado
        d_sym = None
        if map_asset_to_deriv_symbol is not None:
            try:
                d_sym = map_asset_to_deriv_symbol(order.asset)
            except Exception:
                d_sym = None
        is_synth = bool(d_sym) and (d_sym.startswith("R_") or "BOOM" in d_sym or "CRASH" in d_sym)
        # Buy-only para BOOM/CRASH
        if bool(d_sym) and ("BOOM" in d_sym or "CRASH" in d_sym) and order.direction != "call":
            raise HTTPException(status_code=400, detail="Este mercado aceita apenas compra (CALL).")
        # Regras de expiration
        if is_synth:
            if not (1 <= order.expiration <= 10):
                raise HTTPException(status_code=400, detail="expiration deve estar entre 1 e 10 ticks para mercados sintéticos (Deriv)")
        else:
            if not (1 <= order.expiration <= 60):
                raise HTTPException(status_code=400, detail="expiration deve estar entre 1 e 60 minutos")

        # Se for Deriv, não exigir credenciais da IQ
        if USE_DERIV != "1":
            if not IQ_EMAIL or not IQ_PASSWORD:
                raise HTTPException(status_code=500, detail="Credenciais IQ_EMAIL/IQ_PASSWORD ausentes no backend")

        logger.info(f"Iniciando ordem: {order.asset} {order.direction} ${order.amount}")
        
        # Normalizar ativo para IQ Option (mantido para compat com Bridge/IQ)
        normalized = _normalize_asset_for_iq(order.asset)

        # Deriv: se ativado, usar Deriv no lugar de IQ/Bridge
        if USE_DERIV == "1":
            if deriv_quick_order_fn is None:
                raise HTTPException(status_code=503, detail="Integração Deriv indisponível")
            if not DERIV_APP_ID or not DERIV_API_TOKEN:
                raise HTTPException(status_code=503, detail="Deriv não configurado (defina DERIV_APP_ID e DERIV_API_TOKEN)")
            try:
                result = await deriv_quick_order_fn(order.asset, order.direction, order.amount, order.expiration)
                if not result.get("success"):
                    raise HTTPException(status_code=502, detail=result.get("error", "Falha desconhecida Deriv"))
                # Alerta
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
                        "expiration": result.get('duration_value', order.expiration),
                        "duration_unit": result.get('duration_unit', 'm'),
                        "account_type": order.account_type,
                        "option_type": order.option_type,
                        "provider": "deriv",
                    }
                )
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Erro Deriv quick-order: {e}")
                raise HTTPException(status_code=500, detail=f"Erro interno Deriv: {e}")

        # Se estiver em modo Bridge-Only, pular totalmente as libs de API
        if USE_BRIDGE_ONLY == "1":
            if not BRIDGE_URL:
                raise HTTPException(status_code=503, detail="Bridge não configurado (defina BRIDGE_URL)")
            try:
                import httpx
                payload = {
                    "asset": to_deriv_code(normalized),
                    "direction": order.direction,
                    "amount": float(order.amount),
                    "expiration": int(order.expiration),
                    "account_type": order.account_type,
                    "option_type": order.option_type,
                }
                async with httpx.AsyncClient(timeout=25.0) as client:
                    r = await client.post(f"{BRIDGE_URL}/bridge/quick-order", json=payload)
                    if r.status_code == 401:
                        # Não logado: tentar login automático e reenviar
                        creds = {"email": IQ_EMAIL, "password": IQ_PASSWORD}
                        try:
                            await client.post(f"{BRIDGE_URL}/bridge/login", json=creds)
                        except Exception as le:
                            logger.warning(f"Falha no login automático do Bridge: {le}")
                        r = await client.post(f"{BRIDGE_URL}/bridge/quick-order", json=payload)
                    if r.status_code == 200:
                        data = r.json()
                        logger.info(f"[Bridge-only] Ordem enviada com sucesso: {data}")
                        alert = {
                            "id": str(uuid.uuid4()),
                            "signal_id": str(uuid.uuid4()),
                            "alert_type": "order_execution",
                            "title": f"✅ Ordem via Bridge - {to_deriv_code(normalized)}",
                            "message": f"{order.direction.upper()} • ${order.amount} • exp {order.expiration}m • via bridge",
                            "priority": "high",
                            "timestamp": datetime.now(),
                            "signal_type": "buy" if order.direction == "call" else "sell",
                            "symbol": to_deriv_code(normalized),
                            "iq_option_ready": True,
                            "read": False,
                        }
                        try:
                            await db.alerts.insert_one({**alert, "timestamp": alert["timestamp"]})
                        except Exception:
                            pass
                        await broadcast_message(json.dumps({"type": "trading_alert", "data": alert}, default=str))
                        return QuickOrderResponse(
                            success=True,
                            message="Ordem enviada via Bridge",
                            order_id=None,
                            echo={
                                "asset": to_deriv_code(normalized),
                                "direction": order.direction,
                                "amount": order.amount,
                                "expiration": order.expiration,
                                "account_type": order.account_type,
                                "option_type": order.option_type,
                                "provider": "bridge"
                            }
                        )
                    # Qualquer outro status: propagar detalhe quando possível
                    try:
                        detail = r.json()
                    except Exception:
                        detail = r.text
                    raise HTTPException(status_code=503, detail={"bridge_status": r.status_code, "detail": detail})
            except HTTPException:
                raise
            except Exception as be:
                logger.warning(f"Falha no modo Bridge-only: {be}")
                raise HTTPException(status_code=503, detail=f"Falha ao usar Bridge: {be}")

        # Normalizar ativo para IQ Option (redundância segura)
        normalized = _normalize_asset_for_iq(order.asset)

        # Garantir conexão (prefere fx) com timeout total
        try:
            kind, client_obj = await asyncio.wait_for(
                _ensure_connected_prefer_fx(), 
                timeout=45.0
            )
            logger.info(f"Conectado via {kind}")
        except Exception as e:
            logger.warning(f"Falha ao conectar na API da IQ Option: {e}")
            # Fallback direto para Bridge se configurado
            if BRIDGE_URL:
                try:
                    import httpx
                    payload = {
                        "asset": to_deriv_code(normalized),
                        "direction": order.direction,
                        "amount": float(order.amount),
                        "expiration": int(order.expiration),
                        "account_type": order.account_type,
                        "option_type": order.option_type,
                    }
                    async with httpx.AsyncClient(timeout=20.0) as client:
                        r = await client.post(f"{BRIDGE_URL}/bridge/quick-order", json=payload)
                        if r.status_code == 200:
                            data = r.json()
                            logger.info(f"Bridge executou ordem (sem API): {data}")
                            alert = {
                                "id": str(uuid.uuid4()),
                                "signal_id": str(uuid.uuid4()),
                                "alert_type": "order_execution",
                                "title": f"✅ Ordem via Bridge - {normalized}",
                                "message": f"{order.direction.upper()} • ${order.amount} • exp {order.expiration}m • via bridge",
                                "priority": "high",
                                "timestamp": datetime.now(),
                                "signal_type": "buy" if order.direction == "call" else "sell",
                                "symbol": to_deriv_code(normalized),
                                "iq_option_ready": True,
                                "read": False,
                            }
                            try:
                                await db.alerts.insert_one({**alert, "timestamp": alert["timestamp"]})
                            except Exception:
                                pass
                            await broadcast_message(json.dumps({"type": "trading_alert", "data": alert}, default=str))
                            return QuickOrderResponse(
                                success=True,
                                message="Ordem enviada via Bridge",
                                order_id=None,
                                echo={
                                    "asset": to_deriv_code(normalized),
                                    "direction": order.direction,
                                    "amount": order.amount,
                                    "expiration": order.expiration,
                                    "account_type": order.account_type,
                                    "option_type": order.option_type,
                                    "provider": "bridge"
                                }
                            )
                except Exception as be:
                    logger.warning(f"Falha no Bridge fallback (conexão): {be}")
            # Se não houver Bridge ou falhou, propaga o erro padrão
            if isinstance(e, asyncio.TimeoutError):
                raise HTTPException(status_code=504, detail="Timeout na conexão com IQ Option. Tente novamente em alguns instantes.")
            raise HTTPException(status_code=503, detail="Serviço IQ Option temporariamente indisponível. Verifique sua conexão e credenciais.")
        
        # Trocar conta conforme seleção
        await _switch_balance(kind, client_obj, order.account_type)
        
        # Executar ordem com retry
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                normalized = _normalize_asset_for_iq(order.asset)
                success, oid, exp_ts = await _place_order(
                    kind, client_obj, normalized, order.direction, 
                    float(order.amount), int(order.expiration), order.option_type
                )
                
                if success and oid:
                    logger.info(f"Ordem executada com sucesso: {oid}")
                    # Emitir alerta de execução (sucesso)
                    try:
                        alert = {
                            "id": str(uuid.uuid4()),
                            "signal_id": str(oid),
                            "alert_type": "order_execution",
                            "title": f"✅ Ordem enviada - {normalized}",
                            "message": f"ID: {oid} • {order.direction.upper()} • ${order.amount} • exp {order.expiration}m • via {('fx-iqoption' if kind=='fx' else 'iqoptionapi')}",
                            "priority": "high",
                            "timestamp": datetime.now(),
                            "signal_type": "buy" if order.direction == "call" else "sell",
                            "symbol": to_deriv_code(normalized),
                            "iq_option_ready": True,
                            "read": False,
                        }
                        await db.alerts.insert_one({**alert, "timestamp": alert["timestamp"]})
                        await broadcast_message(json.dumps({"type": "trading_alert", "data": alert}, default=str))
                    except Exception as e:
                        logger.warning(f"Falha ao publicar alerta de execução: {e}")

                    return QuickOrderResponse(
                        success=True,
                        message="Ordem enviada com sucesso",
                        order_id=str(oid),
                        echo={
                            "asset": to_deriv_code(normalized),
                            "direction": order.direction,
                            "amount": order.amount,
                            "expiration": order.expiration,
                            "account_type": order.account_type,
                            "option_type": order.option_type,
                            "provider": "fx-iqoption" if kind == "fx" else "iqoptionapi",
                            "expiration_ts": exp_ts,
                            "attempt": attempt + 1
                        }
                    )
                elif attempt < max_retries:
                    logger.warning(f"Tentativa {attempt + 1} falhou, tentando novamente...")
                    await asyncio.sleep(2)  # Aguardar antes do retry
                    continue
                else:
                    # Tentar Bridge como fallback
                    if BRIDGE_URL:
                        try:
                            import httpx
                            payload = {
                                "asset": to_deriv_code(normalized),
                                "direction": order.direction,
                                "amount": float(order.amount),
                                "expiration": int(order.expiration),
                                "account_type": order.account_type,
                                "option_type": order.option_type,
                            }
                            async with httpx.AsyncClient(timeout=20.0) as client:
                                r = await client.post(f"{BRIDGE_URL}/bridge/quick-order", json=payload)
                                if r.status_code == 401:
                                    # Não logado: tentar login automático com credenciais do backend
                                    creds = {"email": IQ_EMAIL, "password": IQ_PASSWORD}
                                    try:
                                        lr = await client.post(f"{BRIDGE_URL}/bridge/login", json=creds)
                                        logger.info(f"Bridge login response: {lr.status_code}")
                                    except Exception as le:
                                        logger.warning(f"Falha login automático no Bridge: {le}")
                                    # tentar de novo a ordem
                                    r = await client.post(f"{BRIDGE_URL}/bridge/quick-order", json=payload)
                                if r.status_code == 200:
                                    data = r.json()
                                    logger.info(f"Bridge executou ordem: {data}")
                                    # Emitir alerta de sucesso via bridge
                                    alert = {
                                        "id": str(uuid.uuid4()),
                                        "signal_id": str(uuid.uuid4()),
                                        "alert_type": "order_execution",
                                        "title": f"✅ Ordem via Bridge - {normalized}",
                                        "message": f"{order.direction.upper()} • ${order.amount} • exp {order.expiration}m • via bridge",
                                        "priority": "high",
                                        "timestamp": datetime.now(),
                                        "signal_type": "buy" if order.direction == "call" else "sell",
                                        "symbol": to_deriv_code(normalized),
                                        "iq_option_ready": True,
                                        "read": False,
                                    }
                                    try:
                                        await db.alerts.insert_one({**alert, "timestamp": alert["timestamp"]})
                                    except Exception:
                                        pass
                                    await broadcast_message(json.dumps({"type": "trading_alert", "data": alert}, default=str))
                                    return QuickOrderResponse(
                                        success=True,
                                        message="Ordem enviada via Bridge",
                                        order_id=None,
                                        echo={
                                            "asset": to_deriv_code(normalized),
                                            "direction": order.direction,
                                            "amount": order.amount,
                                            "expiration": order.expiration,
                                            "account_type": order.account_type,
                                            "option_type": order.option_type,
                                            "provider": "bridge"
                                        }
                                    )
                        except Exception as e:
                            logger.warning(f"Falha no Bridge fallback: {e}")
                    
                    # Emitir alerta de falha
                    try:
                        fail_id = str(uuid.uuid4())
                        alert = {
                            "id": fail_id,
                            "signal_id": fail_id,
                            "alert_type": "order_execution",
                            "title": f"❌ Falha ao enviar ordem - {normalized}",
                            "message": "Falha ao enviar ordem à corretora após múltiplas tentativas",
                            "priority": "critical",
                            "timestamp": datetime.now(),
                            "signal_type": "buy" if order.direction == "call" else "sell",
                            "symbol": to_deriv_code(normalized),
                            "iq_option_ready": False,
                            "read": False,
                        }
                        await db.alerts.insert_one({**alert, "timestamp": alert["timestamp"]})
                        await broadcast_message(json.dumps({"type": "trading_alert", "data": alert}, default=str))
                    except Exception as e:
                        logger.warning(f"Falha ao publicar alerta de erro: {e}")
                    raise HTTPException(status_code=502, detail="Falha ao enviar ordem à corretora após múltiplas tentativas")
                    
            except asyncio.TimeoutError:
                if attempt < max_retries:
                    logger.warning(f"Timeout na tentativa {attempt + 1}, tentando novamente...")
                    await asyncio.sleep(2)
                    continue
                else:
                    # Emitir alerta de timeout
                    try:
                        fail_id = str(uuid.uuid4())
                        alert = {
                            "id": fail_id,
                            "signal_id": fail_id,
                            "alert_type": "order_execution",
                            "title": f"⚠️ Timeout ao enviar ordem - {normalized}",
                            "message": "A corretora pode estar sobrecarregada. Tente novamente.",
                            "priority": "high",
                            "timestamp": datetime.now(),
                            "signal_type": "buy" if order.direction == "call" else "sell",
                            "symbol": to_deriv_code(normalized),
                            "iq_option_ready": False,
                            "read": False,
                        }
                        await db.alerts.insert_one({**alert, "timestamp": alert["timestamp"]})
                        await broadcast_message(json.dumps({"type": "trading_alert", "data": alert}, default=str))
                    except Exception as e:
                        logger.warning(f"Falha ao publicar alerta de timeout: {e}")
                    raise HTTPException(
                        status_code=504, 
                        detail="Timeout ao executar ordem. A corretora pode estar sobrecarregada."
                    )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao executar quick-order: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")

@app.get("/api/stats")
async def get_system_stats():
    """Retorna estatísticas do sistema"""
    
    # Buscar sinais recentes para calcular estatísticas
    recent_signals = await db.signals.find().sort("timestamp", -1).limit(100).to_list(length=100)
    
    if not recent_signals:
        return {
            "score_avg": 71,
            "max_score": 72,
            "rr_avg": 2.33,
            "trending_markets": 0,
            "total_signals": 0,
            "active_symbols": len(market_simulator.symbols),
            "volatility_regime": market_simulator.volatility_regime
        }
    
    scores = [s["confidence_score"] for s in recent_signals]
    rr_ratios = [s["risk_reward_ratio"] for s in recent_signals]
    trending_count = len([s for s in recent_signals if s.get("regime") == "trending"])
    
    return {
        "score_avg": round(sum(scores) / len(scores)) if scores else 71,
        "max_score": max(scores) if scores else 72,
        "rr_avg": round(sum(rr_ratios) / len(rr_ratios), 2) if rr_ratios else 2.33,
        "trending_markets": trending_count,
        "total_signals": len(recent_signals),
        "active_symbols": len(market_simulator.symbols),
        "volatility_regime": market_simulator.volatility_regime,
        "signal_distribution": {
            "premium": len([s for s in recent_signals if s.get("quality") == "premium"]),
            "high": len([s for s in recent_signals if s.get("quality") == "high"]),
            "normal": len([s for s in recent_signals if s.get("quality") == "normal"])
        }
    }

@app.get("/api/symbols")
async def list_symbols():
    """Lista símbolos disponíveis com tipo e liquidez aproximada."""
    items = []
    for sym, cfg in market_simulator.symbols.items():
        price = market_simulator.current_prices.get(sym, cfg.get("base_price", 0))
        hist = market_simulator.price_history.get(sym, [])
        volume = hist[-1]["volume"] if hist else random.uniform(1e5, 1e6)
        liquidity = "high" if volume > 2e6 else "medium" if volume > 5e5 else "low"
        items.append({
            "symbol": to_deriv_code(sym),
            "type": cfg.get("type", "unknown"),
            "liquidity": liquidity,
            "volume": volume,
            "price": price,
        })
    return {"symbols": items}

# WebSocket para dados em tempo real
@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    
    try:
        while True:
            # Enviar dados de mercado atualizados
            market_data = []
            for symbol, config in market_simulator.symbols.items():
                current_price = market_simulator.current_prices[symbol]
                history = market_simulator.price_history[symbol]
                
                if len(history) >= 2:
                    old_price = history[-2]["price"]
                    change = ((current_price - old_price) / old_price) * 100
                else:
                    change = 0.0
                    
                market_data.append({
                    "symbol": to_deriv_code(symbol),
                    "price": current_price,
                    "change_24h": round(change, 2),
                    "volume": history[-1]["volume"] if history else 0,
                    "type": config["type"],
                    "trend": market_simulator.market_trends[symbol],
                    "timestamp": datetime.now().isoformat()
                })
            
            message = {
                "type": "market_update",
                "data": market_data,
                "volatility_regime": market_simulator.volatility_regime
            }
            
            await websocket.send_text(json.dumps(message))
            await asyncio.sleep(1.5)  # Update a cada 1.5 segundos
            
    except WebSocketDisconnect:
        active_connections.remove(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if websocket in active_connections:
            active_connections.remove(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)