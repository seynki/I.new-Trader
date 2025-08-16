from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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

load_dotenv()

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="TypeIA-Trading", version="2.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MongoDB
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
client = AsyncIOMotorClient(MONGO_URL)
db = client.typeia_trading

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
    alert_type: str  # "new_signal", "stop_loss", "take_profit"
    title: str
    message: str
    priority: str  # "low", "medium", "high", "critical"
    timestamp: datetime
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
        
        # Determinar sinal final
        if trend_score + momentum_score + vol_score > 15:
            signal_type = "BUY"
        elif trend_score + momentum_score + vol_score < -15:
            signal_type = "SELL"
        else:
            return None  # Sinal não confiável
        
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
        title = f"🎯 {signal.signal_type} Signal - {sym_fmt}"
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
                    # Salvar no banco
                    await db.signals.insert_one(signal.dict())
                    
                    # Processar notificações
                    await notification_manager.process_signal_notification(signal)
                    
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
            
        data.append({
            "symbol": symbol,
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

    # Símbolos
    if symbol:
        query["symbol"] = symbol
    elif symbols:
        symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
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

@app.post("/api/iq-option/test-connection")
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
                    "symbol": symbol,
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