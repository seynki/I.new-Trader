import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from './components/ui/card';
import { Badge } from './components/ui/badge';
import { Button } from './components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './components/ui/tabs';
import { Progress } from './components/ui/progress';
import { Switch } from './components/ui/switch';
import { 
  TrendingUp, 
  TrendingDown, 
  Activity, 
  Target, 
  Shield, 
  Eye, 
  Zap,
  DollarSign,
  BarChart3,
  Settings,
  PlayCircle,
  PauseCircle,
  Wifi,
  WifiOff,
  ArrowUpRight,
  ArrowDownRight,
  Bell,
  BellOff,
  AlertTriangle,
  CheckCircle,
  Info
} from 'lucide-react';
import './App.css';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8001';

function App() {
  const [marketData, setMarketData] = useState([]);
  const [signals, setSignals] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [activeMode, setActiveMode] = useState('observador');
  const [isConnected, setIsConnected] = useState(false);
  const [isStreaming, setIsStreaming] = useState(true);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [selectedTimeframe, setSelectedTimeframe] = useState('1m');
  const [selectedAssets, setSelectedAssets] = useState('All');
  const [showNotifications, setShowNotifications] = useState(false);
  const [notificationSettings, setNotificationSettings] = useState({
    notifications_enabled: true,
    min_score_threshold: 70,
    min_rr_threshold: 1.5,
    notification_types: ["websocket"],
    timeframes: ["1m", "5m", "15m"]
  });
  const [iqOptionStatus, setIqOptionStatus] = useState(null);
  const wsRef = useRef(null);

  // Configuração do WebSocket
  useEffect(() => {
    if (isStreaming) {
      connectWebSocket();
    } else {
      disconnectWebSocket();
    }
    fetchInitialData();
    
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [isStreaming]);

  const connectWebSocket = () => {
    const wsUrl = BACKEND_URL.replace('http', 'ws') + '/api/ws';
    wsRef.current = new WebSocket(wsUrl);
    
    wsRef.current.onopen = () => {
      setIsConnected(true);
      console.log('WebSocket conectado');
    };
    
    wsRef.current.onmessage = (event) => {
      const message = JSON.parse(event.data);
      
      if (message.type === 'market_update') {
        setMarketData(message.data);
        setLastUpdate(new Date());
      } else if (message.type === 'new_signal') {
        setSignals(prev => [message.data, ...prev.slice(0, 19)]);
      }
    };
    
    wsRef.current.onclose = () => {
      setIsConnected(false);
      if (isStreaming) {
        setTimeout(connectWebSocket, 3000);
      }
    };
    
    wsRef.current.onerror = (error) => {
      console.error('WebSocket error:', error);
      setIsConnected(false);
    };
  };

  const disconnectWebSocket = () => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsConnected(false);
  };

  const fetchInitialData = async () => {
    try {
      const [marketResponse, signalsResponse] = await Promise.all([
        axios.get(`${BACKEND_URL}/api/market-data`),
        axios.get(`${BACKEND_URL}/api/signals?limit=20`)
      ]);
      
      setMarketData(marketResponse.data.data);
      setSignals(signalsResponse.data.signals);
    } catch (error) {
      console.error('Erro ao buscar dados iniciais:', error);
    }
  };

  const formatPrice = (price, symbol) => {
    if (symbol.includes('USD')) {
      return price.toFixed(4);
    }
    return price.toLocaleString(undefined, { maximumFractionDigits: 2 });
  };

  const formatChange = (change) => {
    const sign = change >= 0 ? '+' : '';
    return `${sign}${change.toFixed(2)}%`;
  };

  const getSignalTypeColor = (signalType) => {
    return signalType === 'BUY' ? 'text-green-400' : 'text-red-400';
  };

  const getConfidenceColor = (score) => {
    if (score >= 80) return 'text-green-400';
    if (score >= 65) return 'text-yellow-400';
    return 'text-red-400';
  };

  const getModeConfig = (mode) => {
    const configs = {
      observador: {
        icon: Eye,
        label: 'Observador',
        description: 'Apenas monitoramento e alertas',
        color: 'bg-blue-600 hover:bg-blue-700'
      },
      sugerir: {
        icon: Target,
        label: 'Sugerir entrada',
        description: 'Indica operações possíveis',
        color: 'bg-yellow-600 hover:bg-yellow-700'
      },
      automatico: {
        icon: Zap,
        label: 'Automático',
        description: 'Execução automática de ordens',
        color: 'bg-green-600 hover:bg-green-700'
      }
    };
    return configs[mode];
  };

  // Estatísticas simuladas
  const stats = {
    scoreAvg: 71,
    maxScore: 72,
    rrAvg: 2.33,
    trending: 0,
    riskMinimo: 1.15,
    riscoPorTrade: 5,
    limiteDiario: 3
  };

  return (
    <div className="min-h-screen bg-gray-950 text-green-50">
      {/* Header */}
      <header className="bg-gray-900/80 backdrop-blur-sm border-b border-gray-800/50 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-4">
                <div className="w-3 h-3 bg-green-500 rounded-full shadow-lg shadow-green-500/50 animate-pulse"></div>
                <div>
                  <h1 className="text-xl font-bold text-green-400">
                    TypeIA-Trading
                  </h1>
                  <p className="text-xs text-gray-400">AI Trading System</p>
                </div>
              </div>
              
              {/* Mode Selector */}
              <div className="flex items-center space-x-2 bg-gray-800/50 rounded-xl px-4 py-2 border border-gray-700/50">
                {['observador', 'sugerir', 'automatico'].map((mode) => {
                  const config = getModeConfig(mode);
                  const Icon = config.icon;
                  return (
                    <Button
                      key={mode}
                      variant={activeMode === mode ? "default" : "ghost"}
                      size="sm"
                      onClick={() => setActiveMode(mode)}
                      className={`flex items-center space-x-2 text-xs ${
                        activeMode === mode 
                          ? `${config.color} text-white shadow-lg` 
                          : 'text-gray-400 hover:text-green-400 hover:bg-gray-700/50'
                      }`}
                    >
                      <Icon className="h-3 w-3" />
                      <span className="hidden sm:inline">{config.label}</span>
                    </Button>
                  );
                })}
              </div>
            </div>
            
            {/* Controls */}
            <div className="flex items-center space-x-6">
              {/* Asset Filter */}
              <div className="flex items-center space-x-2">
                <select 
                  value={selectedAssets}
                  onChange={(e) => setSelectedAssets(e.target.value)}
                  className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1 text-sm text-green-400 focus:ring-2 focus:ring-green-500 focus:border-transparent"
                >
                  <option value="All">All</option>
                  <option value="Crypto">Crypto</option>
                  <option value="Forex">Forex</option>
                  <option value="Indices">Indices</option>
                </select>
                
                <select 
                  value={selectedTimeframe}
                  onChange={(e) => setSelectedTimeframe(e.target.value)}
                  className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1 text-sm text-green-400 focus:ring-2 focus:ring-green-500 focus:border-transparent"
                >
                  <option value="1m">1m</option>
                  <option value="5m">5m</option>
                  <option value="15m">15m</option>
                  <option value="1h">1h</option>
                  <option value="4h">4h</option>
                  <option value="1d">1d</option>
                </select>
              </div>
              
              {/* Streaming Toggle */}
              <div className="flex items-center space-x-2">
                <Switch
                  checked={isStreaming}
                  onCheckedChange={setIsStreaming}
                  className="data-[state=checked]:bg-green-600"
                />
                <span className="text-sm text-gray-400">Streaming</span>
                {isConnected ? (
                  <Wifi className="h-4 w-4 text-green-400" />
                ) : (
                  <WifiOff className="h-4 w-4 text-red-400" />
                )}
              </div>
              
              {lastUpdate && (
                <span className="text-xs text-gray-500">
                  {lastUpdate.toLocaleTimeString()}
                </span>
              )}
            </div>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-6 py-6">
        {/* Stats Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <Card className="bg-gray-900/50 border-gray-800/50 backdrop-blur-sm">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-gray-400 mb-1">Score médio</p>
                  <p className="text-2xl font-bold text-green-400">{stats.scoreAvg}</p>
                </div>
                <TrendingUp className="h-5 w-5 text-green-400" />
              </div>
            </CardContent>
          </Card>
          
          <Card className="bg-gray-900/50 border-gray-800/50 backdrop-blur-sm">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-gray-400 mb-1">Maior score</p>
                  <p className="text-2xl font-bold text-blue-400">{stats.maxScore}</p>
                </div>
                <Target className="h-5 w-5 text-blue-400" />
              </div>
            </CardContent>
          </Card>
          
          <Card className="bg-gray-900/50 border-gray-800/50 backdrop-blur-sm">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-gray-400 mb-1">RR médio</p>
                  <p className="text-2xl font-bold text-green-400">{stats.rrAvg}</p>
                </div>
                <ArrowUpRight className="h-5 w-5 text-green-400" />
              </div>
            </CardContent>
          </Card>
          
          <Card className="bg-gray-900/50 border-gray-800/50 backdrop-blur-sm">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-gray-400 mb-1">Em tendência</p>
                  <p className="text-2xl font-bold text-orange-400">{stats.trending}</p>
                </div>
                <Activity className="h-5 w-5 text-orange-400" />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Main Content */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left Column - Opportunities */}
          <div className="lg:col-span-2 space-y-6">
            <Card className="bg-gray-900/50 border-gray-800/50 backdrop-blur-sm">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-lg text-green-400">Oportunidades ao vivo</CardTitle>
                  <Badge variant="outline" className="text-green-400 border-green-400/50">
                    Score ≥ 55, RR ≥ 1.5 risco ≤ 1%
                  </Badge>
                </div>
              </CardHeader>
              <CardContent>
                {/* Table Header */}
                <div className="grid grid-cols-12 gap-3 text-xs text-gray-400 mb-4 px-3 py-2">
                  <div className="col-span-2 font-semibold">Mercado</div>
                  <div className="font-semibold">Ativo</div>
                  <div className="font-semibold">TF</div>
                  <div className="font-semibold">Score</div>
                  <div className="font-semibold">RR</div>
                  <div className="font-semibold">Risco%</div>
                  <div className="font-semibold">Lado</div>
                  <div className="font-semibold">Entrada</div>
                  <div className="font-semibold">Stop</div>
                  <div className="font-semibold">Alvo</div>
                  <div className="font-semibold">Regime</div>
                  <div className="font-semibold">Qualidade</div>
                </div>
                
                {/* Opportunities List */}
                <div className="space-y-3 max-h-96 overflow-y-auto">
                  {signals.slice(0, 10).map((signal, index) => (
                    <div 
                      key={signal.id || index} 
                      className="grid grid-cols-12 gap-3 items-center bg-gray-800/30 rounded-lg p-4 hover:bg-gray-800/50 transition-colors border border-gray-700/30"
                    >
                      <div className="col-span-2 flex items-center space-x-3">
                        <div className="w-10 h-10 bg-orange-500 rounded-lg flex items-center justify-center text-sm font-bold text-white">
                          {signal.symbol?.substring(0, 3) || 'BTC'}
                        </div>
                        <span className="text-sm text-gray-300 font-medium">{signal.symbol?.replace('USDT', '/USDT') || 'BTC/USDT'}</span>
                      </div>
                      <div className="text-sm text-green-400 font-mono">{selectedTimeframe}</div>
                      <div className="flex items-center space-x-2">
                        <div className="w-14 h-3 bg-gray-700 rounded-full overflow-hidden">
                          <div 
                            className="h-full bg-green-500 rounded-full transition-all duration-300"
                            style={{ width: `${signal.confidence_score || 72}%` }}
                          />
                        </div>
                        <span className="text-xs text-green-400 font-mono min-w-[2rem]">{signal.confidence_score || 72}</span>
                      </div>
                      <div className="text-sm text-green-400 font-mono">{signal.risk_reward_ratio || '2.30'}</div>
                      <div className="text-sm text-blue-400 font-mono">0.69</div>
                      <div className={`text-sm font-semibold ${signal.signal_type === 'BUY' ? 'text-green-400' : 'text-red-400'}`}>
                        {signal.signal_type === 'BUY' ? 'buy' : 'sell'}
                      </div>
                      <div className="text-sm text-gray-300 font-mono">{formatPrice(signal.entry_price || 114988.93, signal.symbol)}</div>
                      <div className="text-sm text-red-400 font-mono">{formatPrice(signal.stop_loss || 114965.91, signal.symbol)}</div>
                      <div className="text-sm text-green-400 font-mono">{formatPrice(signal.take_profit || 115053.58, signal.symbol)}</div>
                      <div className="text-xs">
                        <div className="text-yellow-400 font-medium">High-vol</div>
                        <div className="text-gray-400">EMA9/21</div>
                      </div>
                      <div className="text-xs text-gray-400">normal</div>
                    </div>
                  ))}
                  
                  {signals.length === 0 && (
                    <div className="text-center py-8 text-gray-500">
                      <Target className="h-12 w-12 mx-auto mb-3 opacity-50" />
                      <p>Aguardando oportunidades...</p>
                      <p className="text-sm mt-1">Sistema analisando mercados em tempo real</p>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Right Column - Rules & Logs */}
          <div className="space-y-6">
            {/* Rules & Limits */}
            <Card className="bg-gray-900/50 border-gray-800/50 backdrop-blur-sm">
              <CardHeader>
                <CardTitle className="text-lg text-green-400">Regras e limites</CardTitle>
                <p className="text-xs text-gray-400">Gestão de risco ativa</p>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-300">RR mínimo</span>
                  <span className="text-sm text-green-400">1:1.5</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-300">Risco por trade</span>
                  <span className="text-sm text-blue-400">≤ 1%</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-300">Pausa em notícias de</span>
                  <span className="text-sm text-orange-400">alto impacto</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-300">Limite diário</span>
                  <span className="text-sm text-red-400">3% de drawdown</span>
                </div>
              </CardContent>
            </Card>

            {/* Logs */}
            <Card className="bg-gray-900/50 border-gray-800/50 backdrop-blur-sm">
              <CardHeader>
                <CardTitle className="text-lg text-green-400">Logs em tempo real</CardTitle>
                <p className="text-xs text-gray-400">Sinal, score, regime e ação</p>
              </CardHeader>
              <CardContent>
                <div className="space-y-2 max-h-64 overflow-y-auto text-xs">
                  <div className="bg-gray-800/50 rounded p-2">
                    <div className="text-green-400">00:59:26 - [Forex USDJPY]</div>
                    <div className="text-gray-300">rr=3.49 risco=0.54% sinal=RSI|Stochastic rejection</div>
                  </div>
                  <div className="bg-gray-800/50 rounded p-2">
                    <div className="text-blue-400">00:58:15 - [Crypto BTC]</div>
                    <div className="text-gray-300">score=72 ema_cross=true breakout_conf=85%</div>
                  </div>
                  <div className="bg-gray-800/50 rounded p-2">
                    <div className="text-yellow-400">00:57:42 - [Index SP500]</div>
                    <div className="text-gray-300">trend_change detected, volatility=high</div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>

        {/* Market Data Grid */}
        <div className="mt-6">
          <Card className="bg-gray-900/50 border-gray-800/50 backdrop-blur-sm">
            <CardHeader>
              <CardTitle className="text-lg text-green-400">Dados de Mercado</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {marketData.map((market) => (
                  <div key={market.symbol} className="bg-gray-800/30 rounded-lg p-4 border border-gray-700/30">
                    <div className="flex items-center justify-between mb-2">
                      <h3 className="font-semibold text-green-400">{market.symbol}</h3>
                      <Badge 
                        variant={market.change_24h >= 0 ? "default" : "destructive"} 
                        className={`text-xs ${market.change_24h >= 0 ? 'bg-green-600 text-white' : 'bg-red-600 text-white'}`}
                      >
                        {formatChange(market.change_24h)}
                      </Badge>
                    </div>
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-2xl font-bold text-gray-100">
                          {formatPrice(market.price, market.symbol)}
                        </span>
                        {market.change_24h >= 0 ? (
                          <TrendingUp className="h-5 w-5 text-green-400" />
                        ) : (
                          <TrendingDown className="h-5 w-5 text-red-400" />
                        )}
                      </div>
                      <div className="flex items-center space-x-2 text-sm text-gray-400">
                        <Activity className="h-4 w-4" />
                        <span>Vol: {(market.volume || 0).toLocaleString()}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

export default App;