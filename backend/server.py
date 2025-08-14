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

load_dotenv()

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Trading System", version="1.0.0")

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
db = client.trading_ai

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
    timestamp: datetime
    status: str = "ACTIVE"

class TradePosition(BaseModel):
    id: str
    symbol: str
    side: str
    entry_price: float
    quantity: float
    stop_loss: float
    take_profit: float
    current_pnl: float
    timestamp: datetime

# Sistema de dados em tempo real
class MarketSimulator:
    def __init__(self):
        self.symbols = ["BTCUSDT", "ETHUSDT", "EURUSD", "GBPUSD", "SP500", "NAS100"]
        self.current_prices = {
            "BTCUSDT": 95000.0,
            "ETHUSDT": 3500.0,
            "EURUSD": 1.0850,
            "GBPUSD": 1.2650,
            "SP500": 5800.0,
            "NAS100": 20000.0
        }
        self.price_history = {symbol: [] for symbol in self.symbols}
        self.running = False
        
    async def generate_market_data(self):
        """Gera dados de mercado simulados em tempo real"""
        while self.running:
            for symbol in self.symbols:
                # Simulação de movimento de preço realista
                base_price = self.current_prices[symbol]
                volatility = 0.001 if "USD" in symbol else 0.002
                
                # Movimento browniano com tendência
                trend = random.uniform(-0.0005, 0.0005)
                noise = random.gauss(0, volatility)
                price_change = trend + noise
                
                new_price = base_price * (1 + price_change)
                self.current_prices[symbol] = new_price
                
                # Manter histórico dos últimos 200 pontos
                timestamp = datetime.now()
                self.price_history[symbol].append({
                    "price": new_price,
                    "timestamp": timestamp,
                    "volume": random.uniform(1000, 10000)
                })
                
                if len(self.price_history[symbol]) > 200:
                    self.price_history[symbol].pop(0)
                    
            await asyncio.sleep(1)  # Update a cada segundo

# Motor de Indicadores Técnicos
class TechnicalAnalyzer:
    def __init__(self):
        pass
    
    def calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """Calcula RSI (Relative Strength Index)"""
        if len(prices) < period + 1:
            return 50.0
            
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100.0
            
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return round(rsi, 2)
    
    def calculate_ema(self, prices: List[float], period: int) -> float:
        """Calcula EMA (Exponential Moving Average)"""
        if len(prices) < period:
            return sum(prices) / len(prices)
            
        multiplier = 2 / (period + 1)
        ema = prices[0]
        
        for price in prices[1:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
            
        return round(ema, 4)
    
    def calculate_macd(self, prices: List[float]) -> Dict[str, float]:
        """Calcula MACD"""
        if len(prices) < 26:
            return {"macd": 0.0, "signal": 0.0, "histogram": 0.0}
            
        ema_12 = self.calculate_ema(prices, 12)
        ema_26 = self.calculate_ema(prices, 26)
        macd_line = ema_12 - ema_26
        
        # Simular signal line (EMA de 9 períodos do MACD)
        signal_line = macd_line * 0.8  # Simplificado
        histogram = macd_line - signal_line
        
        return {
            "macd": round(macd_line, 4),
            "signal": round(signal_line, 4),
            "histogram": round(histogram, 4)
        }
    
    def calculate_bollinger_bands(self, prices: List[float], period: int = 20) -> Dict[str, float]:
        """Calcula Bandas de Bollinger"""
        if len(prices) < period:
            avg = sum(prices) / len(prices)
            return {"upper": avg * 1.02, "middle": avg, "lower": avg * 0.98}
            
        recent_prices = prices[-period:]
        sma = sum(recent_prices) / period
        variance = sum((x - sma) ** 2 for x in recent_prices) / period
        std_dev = math.sqrt(variance)
        
        return {
            "upper": round(sma + (std_dev * 2), 4),
            "middle": round(sma, 4),
            "lower": round(sma - (std_dev * 2), 4)
        }
    
    def calculate_atr(self, highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
        """Calcula ATR (Average True Range)"""
        if len(closes) < 2:
            return 0.1
            
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

# Sistema de Geração de Sinais
class SignalGenerator:
    def __init__(self):
        self.analyzer = TechnicalAnalyzer()
    
    def generate_signal(self, symbol: str, price_history: List[Dict]) -> Optional[TradingSignal]:
        """Gera sinal de trading baseado em confluência de indicadores"""
        if len(price_history) < 50:
            return None
            
        prices = [p["price"] for p in price_history]
        current_price = prices[-1]
        
        # Calcular indicadores
        rsi = self.analyzer.calculate_rsi(prices)
        macd_data = self.analyzer.calculate_macd(prices)
        ema_9 = self.analyzer.calculate_ema(prices, 9)
        ema_21 = self.analyzer.calculate_ema(prices, 21)
        ema_200 = self.analyzer.calculate_ema(prices, 200)
        bollinger = self.analyzer.calculate_bollinger_bands(prices)
        
        # Simular highs e lows para ATR
        highs = [p * 1.001 for p in prices]
        lows = [p * 0.999 for p in prices]
        atr = self.analyzer.calculate_atr(highs, lows, prices)
        
        # Sistema de pontuação (0-100)
        score = 0
        justifications = []
        
        # Análise de tendência
        trend_score = 0
        if ema_9 > ema_21 > ema_200:
            trend_score += 20
            justifications.append("Tendência de alta confirmada (EMAs alinhadas)")
        elif ema_9 < ema_21 < ema_200:
            trend_score -= 20
            justifications.append("Tendência de baixa confirmada (EMAs alinhadas)")
            
        # Análise de momentum
        momentum_score = 0
        if rsi < 30:
            momentum_score += 15
            justifications.append(f"RSI oversold ({rsi:.1f}) - potencial reversão")
        elif rsi > 70:
            momentum_score -= 15
            justifications.append(f"RSI overbought ({rsi:.1f}) - potencial correção")
            
        # MACD
        if macd_data["macd"] > macd_data["signal"]:
            momentum_score += 10
            justifications.append("MACD acima da signal line")
        else:
            momentum_score -= 10
            justifications.append("MACD abaixo da signal line")
            
        # Bandas de Bollinger
        volatility_score = 0
        if current_price <= bollinger["lower"]:
            volatility_score += 15
            justifications.append("Preço na banda inferior de Bollinger")
        elif current_price >= bollinger["upper"]:
            volatility_score -= 15
            justifications.append("Preço na banda superior de Bollinger")
            
        # Score total
        total_score = trend_score + momentum_score + volatility_score + 50  # Base 50
        confidence = max(0, min(100, total_score))
        
        # Gerar sinal apenas se confiança > 60
        if confidence < 60:
            return None
            
        # Determinar direção
        signal_type = "BUY" if total_score > 50 else "SELL"
        
        # Calcular níveis
        stop_loss = current_price - (atr * 2) if signal_type == "BUY" else current_price + (atr * 2)
        take_profit = current_price + (atr * 3) if signal_type == "BUY" else current_price - (atr * 3)
        rr_ratio = abs(take_profit - current_price) / abs(current_price - stop_loss)
        
        # Só gerar se RR >= 1.5
        if rr_ratio < 1.5:
            return None
            
        signal = TradingSignal(
            id=str(uuid.uuid4()),
            symbol=symbol,
            signal_type=signal_type,
            confidence_score=int(confidence),
            entry_price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward_ratio=round(rr_ratio, 2),
            justification=" | ".join(justifications),
            indicators_confluence={
                "rsi": rsi,
                "macd": macd_data["macd"],
                "ema_9": ema_9,
                "ema_21": ema_21,
                "ema_200": ema_200,
                "bollinger_position": "lower" if current_price <= bollinger["lower"] else "upper" if current_price >= bollinger["upper"] else "middle"
            },
            timestamp=datetime.now()
        )
        
        return signal

# Instâncias globais
market_simulator = MarketSimulator()
signal_generator = SignalGenerator()
active_connections: List[WebSocket] = []

@app.on_event("startup")
async def startup_event():
    """Inicializa o sistema ao iniciar o servidor"""
    market_simulator.running = True
    asyncio.create_task(market_simulator.generate_market_data())
    asyncio.create_task(signal_monitoring_task())
    logger.info("Sistema de trading AI iniciado")

@app.on_event("shutdown")
async def shutdown_event():
    """Para o sistema ao desligar o servidor"""
    market_simulator.running = False

async def signal_monitoring_task():
    """Task para monitorar e gerar sinais"""
    while True:
        try:
            for symbol in market_simulator.symbols:
                price_history = market_simulator.price_history[symbol]
                signal = signal_generator.generate_signal(symbol, price_history)
                
                if signal:
                    # Salvar no banco
                    await db.signals.insert_one(signal.dict())
                    
                    # Enviar para clientes conectados
                    message = {
                        "type": "new_signal",
                        "data": signal.dict()
                    }
                    await broadcast_message(json.dumps(message, default=str))
                    
            await asyncio.sleep(10)  # Verificar a cada 10 segundos
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
    return {"status": "healthy", "timestamp": datetime.now()}

@app.get("/api/market-data")
async def get_market_data():
    """Retorna dados atuais do mercado"""
    data = []
    for symbol in market_simulator.symbols:
        current_price = market_simulator.current_prices[symbol]
        history = market_simulator.price_history[symbol]
        
        if len(history) >= 2:
            change_24h = ((current_price - history[0]["price"]) / history[0]["price"]) * 100
        else:
            change_24h = 0.0
            
        data.append({
            "symbol": symbol,
            "price": current_price,
            "change_24h": round(change_24h, 2),
            "volume": random.uniform(1000000, 10000000),
            "timestamp": datetime.now()
        })
    
    return {"data": data}

@app.get("/api/signals")
async def get_signals(symbol: Optional[str] = None, limit: int = 20):
    """Retorna sinais recentes"""
    query = {}
    if symbol:
        query["symbol"] = symbol
        
    cursor = db.signals.find(query).sort("timestamp", -1).limit(limit)
    signals = await cursor.to_list(length=limit)
    
    # Convert ObjectId to string for JSON serialization
    for signal in signals:
        if "_id" in signal:
            signal["_id"] = str(signal["_id"])
    
    return {"signals": signals}

@app.get("/api/indicators/{symbol}")
async def get_indicators(symbol: str):
    """Retorna indicadores técnicos para um símbolo"""
    if symbol not in market_simulator.symbols:
        raise HTTPException(status_code=404, detail="Symbol not found")
        
    price_history = market_simulator.price_history[symbol]
    if len(price_history) < 20:
        raise HTTPException(status_code=400, detail="Insufficient data")
        
    prices = [p["price"] for p in price_history]
    analyzer = TechnicalAnalyzer()
    
    indicators = {
        "symbol": symbol,
        "rsi": analyzer.calculate_rsi(prices),
        "macd": analyzer.calculate_macd(prices),
        "ema_9": analyzer.calculate_ema(prices, 9),
        "ema_21": analyzer.calculate_ema(prices, 21),
        "ema_200": analyzer.calculate_ema(prices, 200),
        "bollinger": analyzer.calculate_bollinger_bands(prices),
        "timestamp": datetime.now()
    }
    
    return indicators

# WebSocket para dados em tempo real
@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    
    try:
        while True:
            # Enviar dados de mercado atualizados
            market_data = []
            for symbol in market_simulator.symbols:
                current_price = market_simulator.current_prices[symbol]
                history = market_simulator.price_history[symbol]
                
                if len(history) >= 2:
                    change_24h = ((current_price - history[-2]["price"]) / history[-2]["price"]) * 100
                else:
                    change_24h = 0.0
                    
                market_data.append({
                    "symbol": symbol,
                    "price": current_price,
                    "change_24h": round(change_24h, 2),
                    "timestamp": datetime.now().isoformat()
                })
            
            message = {
                "type": "market_update",
                "data": market_data
            }
            
            await websocket.send_text(json.dumps(message))
            await asyncio.sleep(2)  # Update a cada 2 segundos
            
    except WebSocketDisconnect:
        active_connections.remove(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if websocket in active_connections:
            active_connections.remove(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)