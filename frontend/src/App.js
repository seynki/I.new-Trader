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
      } else if (message.type === 'trading_alert') {
        setAlerts(prev => [message.data, ...prev.slice(0, 9)]);
        // Show notification toast or popup here
        showTradingAlertNotification(message.data);
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
      const [marketResponse, signalsResponse, alertsResponse] = await Promise.all([
        axios.get(`${BACKEND_URL}/api/market-data`),
        axios.get(`${BACKEND_URL}/api/signals?limit=20`),
        axios.get(`${BACKEND_URL}/api/alerts?limit=10`)
      ]);
      
      setMarketData(marketResponse.data.data);
      setSignals(signalsResponse.data.signals);
      setAlerts(alertsResponse.data.alerts);
    } catch (error) {
      console.error('Erro ao buscar dados iniciais:', error);
    }
  };

  const showTradingAlertNotification = (alertData) => {
    // Create browser notification if permission granted
    if (Notification.permission === "granted") {
      new Notification(alertData.title, {
        body: alertData.message,
        icon: '/favicon.ico',
        tag: alertData.id
      });
    }
  };

  const testIQOptionConnection = async () => {
    try {
      const response = await axios.post(`${BACKEND_URL}/api/iq-option/test-connection`);
      setIqOptionStatus(response.data);
    } catch (error) {
      console.error('Erro ao testar conexão IQ Option:', error);
      setIqOptionStatus({ status: 'error', message: 'Connection failed' });
    }
  };

  const updateNotificationSettings = async (newSettings) => {
    try {
      await axios.post(`${BACKEND_URL}/api/notifications/settings`, newSettings);
      setNotificationSettings(newSettings);
    } catch (error) {
      console.error('Erro ao atualizar configurações:', error);
    }
  };

  // Request notification permission
  useEffect(() => {
    if (Notification.permission === "default") {
      Notification.requestPermission();
    }
  }, []);

  const formatPrice = (price, symbol) => {
    if (!price) return '0.00';
    
    // Para números muito grandes (índices como US30, NAS100)
    if (price >= 10000) {
      return Math.round(price).toLocaleString();
    }
    // Para preços médios (BTC, etc)
    else if (price >= 1000) {
      return Math.round(price).toLocaleString();
    }
    // Para preços forex (JPY, EUR, etc)
    else if (price >= 100) {
      return price.toFixed(1);
    }
    else if (price >= 10) {
      return price.toFixed(2);
    }
    // Para preços muito pequenos
    else {
      return price.toFixed(4);
    }
  };

  // Função para formatar símbolos no estilo IQ Option
  const formatIQOptionSymbol = (symbol) => {
    if (!symbol) return 'BTC/USD (OTC)';
    
    // Se termina com T (como BTCUSDT), remove o T e adiciona (OTC)
    if (symbol.endsWith('T')) {
      const base = symbol.slice(0, -1); // Remove o T
      if (base.includes('USD')) {
        // BTCUSD → BTC/USD
        const crypto = base.replace('USD', '');
        return `${crypto}/USD (OTC)`;
      } else if (base.includes('USDT')) {
        // BTCUSDT → BTC/USD (mas já foi removido o T)
        const crypto = base.replace('USDT', '');
        return `${crypto}/USD (OTC)`;
      }
    }
    
    // Outros formatos
    if (symbol.includes('USDT')) {
      const crypto = symbol.replace('USDT', '');
      return `${crypto}/USD (OTC)`;
    } else if (symbol.includes('USD')) {
      const crypto = symbol.replace('USD', '');
      return `${crypto}/USD (OTC)`;
    }
    
    return symbol;
  };

  // Função para obter sigla do símbolo para o ícone
  const getSymbolShort = (symbol) => {
    if (!symbol) return 'BTC';
    
    if (symbol.endsWith('T')) {
      const base = symbol.slice(0, -1);
      if (base.includes('USD')) {
        return base.replace('USD', '').substring(0, 3);
      }
    }
    
    if (symbol.includes('USDT')) {
      return symbol.replace('USDT', '').substring(0, 3);
    } else if (symbol.includes('USD')) {
      return symbol.replace('USD', '').substring(0, 3);
    }
    
    return symbol.substring(0, 3);
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
              {/* Notifications */}
              <div className="relative">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowNotifications(!showNotifications)}
                  className={`p-2 ${showNotifications ? 'bg-gray-700' : 'hover:bg-gray-700/50'}`}
                >
                  {notificationSettings.notifications_enabled ? (
                    <Bell className="h-4 w-4 text-green-400" />
                  ) : (
                    <BellOff className="h-4 w-4 text-gray-400" />
                  )}
                  {alerts.length > 0 && (
                    <span className="absolute -top-1 -right-1 bg-red-500 text-white text-xs rounded-full h-5 w-5 flex items-center justify-center">
                      {alerts.length}
                    </span>
                  )}
                </Button>

                {/* Notifications Dropdown */}
                {showNotifications && (
                  <div className="absolute right-0 top-12 w-80 bg-gray-900 border border-gray-700 rounded-lg shadow-xl z-50">
                    <div className="p-4 border-b border-gray-700">
                      <h3 className="text-sm font-semibold text-green-400">Alertas de Trading</h3>
                    </div>
                    <div className="max-h-64 overflow-y-auto">
                      {alerts.length > 0 ? (
                        alerts.slice(0, 5).map((alert, index) => (
                          <div key={alert.id || index} className="p-3 border-b border-gray-800 hover:bg-gray-800/50">
                            <div className="flex items-start space-x-3">
                              <div className={`mt-1 w-2 h-2 rounded-full ${
                                alert.priority === 'high' ? 'bg-red-400' : 
                                alert.priority === 'medium' ? 'bg-yellow-400' : 'bg-blue-400'
                              }`} />
                              <div className="flex-1">
                                <div className="flex items-center space-x-2 mb-1">
                                  {alert.symbol && (
                                    <div className="w-6 h-6 bg-black/40 backdrop-blur-sm border border-gray-600/30 rounded flex items-center justify-center text-xs font-bold text-green-400">
                                      {getSymbolShort(alert.symbol)}
                                    </div>
                                  )}
                                  <p className="text-xs font-medium text-gray-200">
                                    {alert.symbol ? formatIQOptionSymbol(alert.symbol) : alert.title}
                                  </p>
                                </div>
                                <p className="text-xs text-gray-400 mt-1">{alert.message?.substring(0, 100)}...</p>
                                <p className="text-xs text-gray-500 mt-1">
                                  {new Date(alert.timestamp).toLocaleTimeString()}
                                </p>
                              </div>
                            </div>
                          </div>
                        ))
                      ) : (
                        <div className="p-4 text-center text-gray-500">
                          <Bell className="h-8 w-8 mx-auto mb-2 opacity-50" />
                          <p className="text-sm">Nenhum alerta recente</p>
                        </div>
                      )}
                    </div>
                    <div className="p-3 border-t border-gray-700">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setShowNotifications(false)}
                        className="w-full text-xs text-gray-400 hover:text-green-400"
                      >
                        Fechar
                      </Button>
                    </div>
                  </div>
                )}
              </div>

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
                <div className="grid grid-cols-12 gap-2 text-xs text-gray-400 mb-4 px-3 py-2">
                  <div className="col-span-2 font-semibold">Ativo</div>
                  <div className="font-semibold">TF</div>
                  <div className="font-semibold text-center">Score</div>
                  <div className="font-semibold text-center">RR</div>
                  <div className="font-semibold text-center">Risco%</div>
                  <div className="font-semibold">Lado</div>
                  <div className="col-span-1 font-semibold text-right">Entrada</div>
                  <div className="col-span-1 font-semibold text-right">Stop</div>
                  <div className="col-span-1 font-semibold text-right">Alvo</div>
                  <div className="font-semibold text-center">Regime</div>
                  <div className="font-semibold text-center">Qualidade</div>
                </div>
                
                {/* Opportunities List */}
                <div className="space-y-3 max-h-96 overflow-y-auto">
                  {signals.slice(0, 10).map((signal, index) => (
                    <div 
                      key={signal.id || index} 
                      className="grid grid-cols-12 gap-2 items-center bg-gray-800/30 rounded-lg p-3 hover:bg-gray-800/50 transition-colors border border-gray-700/30"
                    >
                      <div className="col-span-2 flex items-center space-x-2">
                        <div className="w-8 h-8 bg-black/40 backdrop-blur-sm border border-gray-600/30 rounded-lg flex items-center justify-center text-xs font-bold text-green-400">
                          {getSymbolShort(signal.symbol)}
                        </div>
                        <div className="flex flex-col">
                          <span className="text-xs text-gray-300 font-medium leading-tight">
                            {formatIQOptionSymbol(signal.symbol)}
                          </span>
                        </div>
                      </div>
                      <div className="text-xs text-green-400 font-mono">{selectedTimeframe}</div>
                      <div className="flex items-center justify-center">
                        <div className="w-12 h-2 bg-gray-700 rounded-full overflow-hidden">
                          <div 
                            className="h-full bg-green-500 rounded-full transition-all duration-300"
                            style={{ width: `${signal.confidence_score || 72}%` }}
                          />
                        </div>
                        <span className="text-xs text-green-400 font-mono ml-1 min-w-[1.5rem] text-center">{signal.confidence_score || 72}</span>
                      </div>
                      <div className="text-xs text-green-400 font-mono text-center">{signal.risk_reward_ratio || '2.30'}</div>
                      <div className="text-xs text-blue-400 font-mono text-center">0.69</div>
                      <div className={`text-xs font-semibold ${signal.signal_type === 'BUY' ? 'text-green-400' : 'text-red-400'}`}>
                        {signal.signal_type === 'BUY' ? 'buy' : 'sell'}
                      </div>
                      <div className="col-span-1 text-xs text-gray-300 font-mono text-right">{formatPrice(signal.entry_price || 114988.93, signal.symbol)}</div>
                      <div className="col-span-1 text-xs text-red-400 font-mono text-right">{formatPrice(signal.stop_loss || 114965.91, signal.symbol)}</div>
                      <div className="col-span-1 text-xs text-green-400 font-mono text-right">{formatPrice(signal.take_profit || 115053.58, signal.symbol)}</div>
                      <div className="text-xs">
                        <div className="text-yellow-400 font-medium text-center">High-vol</div>
                        <div className="text-gray-400 text-center">EMA9/21</div>
                      </div>
                      <div className="text-xs text-gray-400 text-center">normal</div>
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

          {/* Right Column - Notifications & Rules */}
          <div className="space-y-6">
            {/* IQ Option Status */}
            <Card className="bg-gray-900/50 border-gray-800/50 backdrop-blur-sm">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-lg text-green-400">IQ Option Status</CardTitle>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={testIQOptionConnection}
                    className="text-xs"
                  >
                    Testar Conexão
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                {iqOptionStatus ? (
                  <>
                    <div className="flex items-center space-x-2">
                      {iqOptionStatus.status === 'success' ? (
                        <CheckCircle className="h-4 w-4 text-green-400" />
                      ) : (
                        <AlertTriangle className="h-4 w-4 text-red-400" />
                      )}
                      <span className="text-sm text-gray-300">{iqOptionStatus.message}</span>
                    </div>
                    {iqOptionStatus.email && (
                      <div className="text-xs text-gray-400">
                        <span>Email: {iqOptionStatus.email}</span>
                      </div>
                    )}
                    {iqOptionStatus.balance && (
                      <div className="text-xs text-gray-400">
                        <span>Saldo: ${iqOptionStatus.balance}</span>
                      </div>
                    )}
                    <div className="text-xs text-blue-400">
                      <Info className="h-3 w-3 inline mr-1" />
                      Apenas notificações ativadas
                    </div>
                  </>
                ) : (
                  <div className="text-sm text-gray-400">
                    Clique para testar conexão
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Notification Settings */}
            <Card className="bg-gray-900/50 border-gray-800/50 backdrop-blur-sm">
              <CardHeader>
                <CardTitle className="text-lg text-green-400">Configurações de Alerta</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-300">Notificações ativas</span>
                  <Switch
                    checked={notificationSettings.notifications_enabled}
                    onCheckedChange={(checked) => updateNotificationSettings({
                      ...notificationSettings,
                      notifications_enabled: checked
                    })}
                    className="data-[state=checked]:bg-green-600"
                  />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-300">Score mínimo</span>
                  <span className="text-sm text-green-400">{notificationSettings.min_score_threshold}%</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-300">RR mínimo</span>
                  <span className="text-sm text-green-400">{notificationSettings.min_rr_threshold}:1</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-300">Timeframes</span>
                  <span className="text-sm text-blue-400">{notificationSettings.timeframes.join(', ')}</span>
                </div>
              </CardContent>
            </Card>

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
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center space-x-3">
                        <div className="w-8 h-8 bg-black/40 backdrop-blur-sm border border-gray-600/30 rounded-lg flex items-center justify-center text-xs font-bold text-green-400">
                          {getSymbolShort(market.symbol)}
                        </div>
                        <h3 className="font-semibold text-green-400 text-sm">{formatIQOptionSymbol(market.symbol)}</h3>
                      </div>
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