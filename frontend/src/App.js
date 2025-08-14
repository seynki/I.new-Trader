import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from './components/ui/card';
import { Badge } from './components/ui/badge';
import { Button } from './components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './components/ui/tabs';
import { Alert, AlertDescription } from './components/ui/alert';
import { Progress } from './components/ui/progress';
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
  Brain,
  AlertTriangle
} from 'lucide-react';
import './App.css';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8001';

function App() {
  const [marketData, setMarketData] = useState([]);
  const [signals, setSignals] = useState([]);
  const [activeMode, setActiveMode] = useState('observer');
  const [isConnected, setIsConnected] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(null);
  const wsRef = useRef(null);

  // Configuração do WebSocket
  useEffect(() => {
    connectWebSocket();
    fetchInitialData();
    
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

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
        setSignals(prev => [message.data, ...prev.slice(0, 9)]);
      }
    };
    
    wsRef.current.onclose = () => {
      setIsConnected(false);
      // Reconectar após 3 segundos
      setTimeout(connectWebSocket, 3000);
    };
    
    wsRef.current.onerror = (error) => {
      console.error('WebSocket error:', error);
      setIsConnected(false);
    };
  };

  const fetchInitialData = async () => {
    try {
      const [marketResponse, signalsResponse] = await Promise.all([
        axios.get(`${BACKEND_URL}/api/market-data`),
        axios.get(`${BACKEND_URL}/api/signals?limit=10`)
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

  const getSignalColor = (signalType) => {
    return signalType === 'BUY' ? 'text-green-600' : 'text-red-600';
  };

  const getConfidenceColor = (score) => {
    if (score >= 80) return 'text-green-600';
    if (score >= 65) return 'text-yellow-600';
    return 'text-red-600';
  };

  const getModeConfig = (mode) => {
    const configs = {
      observer: {
        icon: Eye,
        label: 'Observador',
        description: 'Apenas monitoramento e alertas',
        color: 'bg-blue-500'
      },
      suggest: {
        icon: Target,
        label: 'Sugestões',
        description: 'Indica operações possíveis',
        color: 'bg-yellow-500'
      },
      automatic: {
        icon: Zap,
        label: 'Automático',
        description: 'Execução automática de ordens',
        color: 'bg-red-500'
      }
    };
    return configs[mode];
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100">
      {/* Header */}
      <header className="bg-white/80 backdrop-blur-md border-b border-slate-200/50 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="p-2 bg-gradient-to-r from-blue-600 to-purple-600 rounded-xl">
                <Brain className="h-8 w-8 text-white" />
              </div>
              <div>
                <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
                  AI Trading System
                </h1>
                <p className="text-sm text-slate-600">Inteligência Artificial para Trading</p>
              </div>
            </div>
            
            <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-2">
                <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`}></div>
                <span className="text-sm text-slate-600">
                  {isConnected ? 'Conectado' : 'Desconectado'}
                </span>
              </div>
              
              {lastUpdate && (
                <span className="text-xs text-slate-500">
                  Atualizado: {lastUpdate.toLocaleTimeString()}
                </span>
              )}
            </div>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 py-6">
        {/* Mode Selector */}
        <div className="mb-6">
          <div className="flex items-center space-x-4 bg-white/60 backdrop-blur-sm rounded-2xl p-4 border border-slate-200/50">
            <span className="text-sm font-medium text-slate-700">Modo de Operação:</span>
            <div className="flex space-x-2">
              {['observer', 'suggest', 'automatic'].map((mode) => {
                const config = getModeConfig(mode);
                const Icon = config.icon;
                return (
                  <Button
                    key={mode}
                    variant={activeMode === mode ? "default" : "outline"}
                    onClick={() => setActiveMode(mode)}
                    className={`flex items-center space-x-2 ${
                      activeMode === mode 
                        ? `${config.color} text-white shadow-lg` 
                        : 'bg-white hover:bg-slate-50'
                    }`}
                  >
                    <Icon className="h-4 w-4" />
                    <span className="hidden sm:inline">{config.label}</span>
                  </Button>
                );
              })}
            </div>
          </div>
        </div>

        <Tabs defaultValue="dashboard" className="space-y-6">
          <TabsList className="grid w-full grid-cols-4 bg-white/60 backdrop-blur-sm rounded-2xl p-1 border border-slate-200/50">
            <TabsTrigger value="dashboard" className="flex items-center space-x-2">
              <BarChart3 className="h-4 w-4" />
              <span>Dashboard</span>
            </TabsTrigger>
            <TabsTrigger value="signals" className="flex items-center space-x-2">
              <Target className="h-4 w-4" />
              <span>Sinais</span>
            </TabsTrigger>
            <TabsTrigger value="positions" className="flex items-center space-x-2">
              <DollarSign className="h-4 w-4" />
              <span>Posições</span>
            </TabsTrigger>
            <TabsTrigger value="risk" className="flex items-center space-x-2">
              <Shield className="h-4 w-4" />
              <span>Risco</span>
            </TabsTrigger>
          </TabsList>

          <TabsContent value="dashboard" className="space-y-6">
            {/* Market Overview */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {marketData.map((market) => (
                <Card key={market.symbol} className="bg-white/70 backdrop-blur-sm border-slate-200/50 hover:shadow-lg transition-all duration-300">
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-lg font-semibold">{market.symbol}</CardTitle>
                      <Badge variant={market.change_24h >= 0 ? "default" : "destructive"} className="text-xs">
                        {formatChange(market.change_24h)}
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-2xl font-bold">
                          {formatPrice(market.price, market.symbol)}
                        </span>
                        {market.change_24h >= 0 ? (
                          <TrendingUp className="h-5 w-5 text-green-600" />
                        ) : (
                          <TrendingDown className="h-5 w-5 text-red-600" />
                        )}
                      </div>
                      <div className="flex items-center space-x-2 text-sm text-slate-600">
                        <Activity className="h-4 w-4" />
                        <span>Volume: {(market.volume || 0).toLocaleString()}</span>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>

            {/* Active Mode Info */}
            <Card className="bg-white/70 backdrop-blur-sm border-slate-200/50">
              <CardHeader>
                <CardTitle className="flex items-center space-x-2">
                  {React.createElement(getModeConfig(activeMode).icon, { className: "h-5 w-5" })}
                  <span>Modo: {getModeConfig(activeMode).label}</span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-slate-600">{getModeConfig(activeMode).description}</p>
                
                {activeMode === 'automatic' && (
                  <Alert className="mt-4 border-amber-200 bg-amber-50">
                    <AlertTriangle className="h-4 w-4 text-amber-600" />
                    <AlertDescription className="text-amber-800">
                      Modo automático ativo. O sistema pode executar operações automaticamente.
                    </AlertDescription>
                  </Alert>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="signals" className="space-y-6">
            <div className="space-y-4">
              {signals.length === 0 ? (
                <Card className="bg-white/70 backdrop-blur-sm border-slate-200/50">
                  <CardContent className="py-8 text-center">
                    <Target className="h-12 w-12 text-slate-400 mx-auto mb-4" />
                    <p className="text-slate-600">Aguardando sinais de trading...</p>
                    <p className="text-sm text-slate-500 mt-2">
                      O sistema está analisando os mercados em tempo real
                    </p>
                  </CardContent>
                </Card>
              ) : (
                signals.map((signal) => (
                  <Card key={signal.id} className="bg-white/70 backdrop-blur-sm border-slate-200/50 hover:shadow-lg transition-all duration-300">
                    <CardHeader>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-3">
                          <CardTitle className="text-lg">{signal.symbol}</CardTitle>
                          <Badge 
                            variant={signal.signal_type === 'BUY' ? "default" : "destructive"}
                            className="font-semibold"
                          >
                            {signal.signal_type}
                          </Badge>
                          <div className="flex items-center space-x-1">
                            <Progress 
                              value={signal.confidence_score} 
                              className="w-16 h-2" 
                            />
                            <span className={`text-sm font-medium ${getConfidenceColor(signal.confidence_score)}`}>
                              {signal.confidence_score}%
                            </span>
                          </div>
                        </div>
                        <span className="text-sm text-slate-500">
                          {new Date(signal.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-3">
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                          <div>
                            <span className="text-slate-600">Entrada:</span>
                            <p className="font-semibold">{formatPrice(signal.entry_price, signal.symbol)}</p>
                          </div>
                          <div>
                            <span className="text-slate-600">Stop Loss:</span>
                            <p className="font-semibold text-red-600">{formatPrice(signal.stop_loss, signal.symbol)}</p>
                          </div>
                          <div>
                            <span className="text-slate-600">Take Profit:</span>
                            <p className="font-semibold text-green-600">{formatPrice(signal.take_profit, signal.symbol)}</p>
                          </div>
                          <div>
                            <span className="text-slate-600">R/R:</span>
                            <p className="font-semibold">{signal.risk_reward_ratio}:1</p>
                          </div>
                        </div>
                        
                        <div className="bg-slate-50 rounded-lg p-3">
                          <h4 className="font-medium text-slate-700 mb-2">Justificativa:</h4>
                          <p className="text-sm text-slate-600">{signal.justification}</p>
                        </div>
                        
                        {activeMode !== 'observer' && (
                          <div className="flex space-x-2">
                            <Button size="sm" className="bg-green-600 hover:bg-green-700">
                              Executar Trade
                            </Button>
                            <Button size="sm" variant="outline">
                              Ignorar
                            </Button>
                          </div>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                ))
              )}
            </div>
          </TabsContent>

          <TabsContent value="positions" className="space-y-6">
            <Card className="bg-white/70 backdrop-blur-sm border-slate-200/50">
              <CardContent className="py-8 text-center">
                <DollarSign className="h-12 w-12 text-slate-400 mx-auto mb-4" />
                <p className="text-slate-600">Nenhuma posição ativa</p>
                <p className="text-sm text-slate-500 mt-2">
                  Posições aparecerão aqui quando trades forem executados
                </p>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="risk" className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <Card className="bg-white/70 backdrop-blur-sm border-slate-200/50">
                <CardHeader>
                  <CardTitle className="flex items-center space-x-2">
                    <Shield className="h-5 w-5" />
                    <span>Gestão de Risco</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span>Risco por Trade:</span>
                      <span className="font-semibold">0.5%</span>
                    </div>
                    <Progress value={50} className="h-2" />
                  </div>
                  
                  <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span>Risco Diário:</span>
                      <span className="font-semibold">0.0%</span>
                    </div>
                    <Progress value={0} className="h-2" />
                  </div>
                  
                  <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span>Drawdown Máximo:</span>
                      <span className="font-semibold">5%</span>
                    </div>
                    <Progress value={25} className="h-2" />
                  </div>
                </CardContent>
              </Card>

              <Card className="bg-white/70 backdrop-blur-sm border-slate-200/50">
                <CardHeader>
                  <CardTitle>Estatísticas</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex justify-between">
                    <span className="text-slate-600">Win Rate:</span>
                    <span className="font-semibold">--%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-600">Trades Totais:</span>
                    <span className="font-semibold">0</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-600">P&L Total:</span>
                    <span className="font-semibold">$0.00</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-600">Sharpe Ratio:</span>
                    <span className="font-semibold">-</span>
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}

export default App;