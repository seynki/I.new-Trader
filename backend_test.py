import requests
import sys
import json
import time
import websocket
import threading
from datetime import datetime

class AITradingSystemTester:
    def __init__(self, base_url="https://multi-market-scout.preview.emergentagent.com"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.ws_messages = []
        self.ws_connected = False

    def run_test(self, name, method, endpoint, expected_status, data=None, timeout=10):
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}"
        headers = {'Content-Type': 'application/json'}

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=timeout)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=timeout)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    response_data = response.json()
                    print(f"   Response keys: {list(response_data.keys()) if isinstance(response_data, dict) else 'Non-dict response'}")
                    return True, response_data
                except:
                    return True, response.text
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                print(f"   Response: {response.text[:200]}...")
                return False, {}

        except requests.exceptions.Timeout:
            print(f"❌ Failed - Request timeout after {timeout}s")
            return False, {}
        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def test_health_endpoint(self):
        """Test health check endpoint"""
        success, response = self.run_test(
            "Health Check",
            "GET",
            "api/health",
            200
        )
        if success and isinstance(response, dict):
            if 'status' in response and response['status'] == 'healthy':
                print("   ✓ Health status is healthy")
                return True
            else:
                print("   ⚠️ Health status not as expected")
        return success

    def test_market_data_endpoint(self):
        """Test market data endpoint"""
        success, response = self.run_test(
            "Market Data",
            "GET",
            "api/market-data",
            200
        )
        if success and isinstance(response, dict):
            if 'data' in response and isinstance(response['data'], list):
                market_data = response['data']
                print(f"   ✓ Found {len(market_data)} markets")
                
                expected_symbols = ["BTCUSDT", "ETHUSDT", "EURUSD", "GBPUSD", "SP500", "NAS100"]
                found_symbols = [item['symbol'] for item in market_data if 'symbol' in item]
                
                for symbol in expected_symbols:
                    if symbol in found_symbols:
                        print(f"   ✓ {symbol} data available")
                    else:
                        print(f"   ⚠️ {symbol} data missing")
                
                # Check data structure
                if market_data:
                    sample = market_data[0]
                    required_fields = ['symbol', 'price', 'change_24h', 'volume', 'timestamp']
                    for field in required_fields:
                        if field in sample:
                            print(f"   ✓ Field '{field}' present")
                        else:
                            print(f"   ⚠️ Field '{field}' missing")
                
                return True
        return success

    def test_signals_endpoint(self):
        """Test signals endpoint"""
        success, response = self.run_test(
            "Trading Signals",
            "GET",
            "api/signals?limit=10",
            200
        )
        if success and isinstance(response, dict):
            if 'signals' in response:
                signals = response['signals']
                print(f"   ✓ Found {len(signals)} signals")
                
                if signals:
                    sample_signal = signals[0]
                    required_fields = ['id', 'symbol', 'signal_type', 'confidence_score', 
                                     'entry_price', 'stop_loss', 'take_profit', 'risk_reward_ratio']
                    for field in required_fields:
                        if field in sample_signal:
                            print(f"   ✓ Signal field '{field}' present")
                        else:
                            print(f"   ⚠️ Signal field '{field}' missing")
                    
                    # Check signal validation
                    if 'confidence_score' in sample_signal:
                        score = sample_signal['confidence_score']
                        if 0 <= score <= 100:
                            print(f"   ✓ Confidence score valid: {score}")
                        else:
                            print(f"   ⚠️ Confidence score invalid: {score}")
                    
                    if 'risk_reward_ratio' in sample_signal:
                        rr = sample_signal['risk_reward_ratio']
                        if rr >= 1.5:
                            print(f"   ✓ Risk/Reward ratio valid: {rr}")
                        else:
                            print(f"   ⚠️ Risk/Reward ratio below 1.5: {rr}")
                
                return True
        return success

    def test_indicators_endpoint(self):
        """Test technical indicators endpoint"""
        test_symbols = ["BTCUSDT", "ETHUSDT"]
        all_passed = True
        
        for symbol in test_symbols:
            success, response = self.run_test(
                f"Technical Indicators - {symbol}",
                "GET",
                f"api/indicators/{symbol}",
                200
            )
            if success and isinstance(response, dict):
                required_indicators = ['symbol', 'rsi', 'macd', 'ema_9', 'ema_21', 'ema_200', 'bollinger']
                for indicator in required_indicators:
                    if indicator in response:
                        print(f"   ✓ {symbol} - {indicator} present")
                    else:
                        print(f"   ⚠️ {symbol} - {indicator} missing")
                        all_passed = False
            else:
                all_passed = False
        
        return all_passed

    def test_websocket_connection(self):
        """Test WebSocket connection"""
        print(f"\n🔍 Testing WebSocket Connection...")
        
        ws_url = self.base_url.replace('https', 'wss') + '/api/ws'
        print(f"   WebSocket URL: {ws_url}")
        
        def on_message(ws, message):
            try:
                data = json.loads(message)
                self.ws_messages.append(data)
                print(f"   📨 Received: {data.get('type', 'unknown')} message")
            except:
                print(f"   📨 Received non-JSON message")

        def on_error(ws, error):
            print(f"   ❌ WebSocket error: {error}")

        def on_close(ws, close_status_code, close_msg):
            print(f"   🔌 WebSocket closed")
            self.ws_connected = False

        def on_open(ws):
            print(f"   ✅ WebSocket connected")
            self.ws_connected = True

        try:
            ws = websocket.WebSocketApp(ws_url,
                                      on_open=on_open,
                                      on_message=on_message,
                                      on_error=on_error,
                                      on_close=on_close)
            
            # Run WebSocket in a separate thread
            wst = threading.Thread(target=ws.run_forever)
            wst.daemon = True
            wst.start()
            
            # Wait for connection and messages
            time.sleep(5)
            
            if self.ws_connected:
                self.tests_passed += 1
                print(f"   ✅ WebSocket connection successful")
                print(f"   📊 Received {len(self.ws_messages)} messages")
                
                # Check message types
                message_types = set()
                for msg in self.ws_messages:
                    if isinstance(msg, dict) and 'type' in msg:
                        message_types.add(msg['type'])
                
                print(f"   📋 Message types: {list(message_types)}")
                
                ws.close()
                return True
            else:
                print(f"   ❌ WebSocket connection failed")
                return False
                
        except Exception as e:
            print(f"   ❌ WebSocket test failed: {str(e)}")
            return False
        finally:
            self.tests_run += 1

    def test_signal_generation_logic(self):
        """Test signal generation and validation"""
        print(f"\n🔍 Testing Signal Generation Logic...")
        
        # Get some signals to analyze
        success, response = self.run_test(
            "Signal Analysis",
            "GET",
            "api/signals?limit=5",
            200
        )
        
        if success and isinstance(response, dict) and 'signals' in response:
            signals = response['signals']
            
            if not signals:
                print("   ⚠️ No signals available for analysis")
                return False
            
            print(f"   📊 Analyzing {len(signals)} signals...")
            
            valid_signals = 0
            for signal in signals:
                is_valid = True
                
                # Check confidence score
                if 'confidence_score' in signal:
                    score = signal['confidence_score']
                    if not (0 <= score <= 100):
                        print(f"   ❌ Invalid confidence score: {score}")
                        is_valid = False
                else:
                    print(f"   ❌ Missing confidence score")
                    is_valid = False
                
                # Check risk/reward ratio
                if 'risk_reward_ratio' in signal:
                    rr = signal['risk_reward_ratio']
                    if rr < 1.5:
                        print(f"   ❌ Risk/Reward ratio below 1.5: {rr}")
                        is_valid = False
                else:
                    print(f"   ❌ Missing risk/reward ratio")
                    is_valid = False
                
                # Check signal type
                if 'signal_type' in signal:
                    if signal['signal_type'] not in ['BUY', 'SELL']:
                        print(f"   ❌ Invalid signal type: {signal['signal_type']}")
                        is_valid = False
                else:
                    print(f"   ❌ Missing signal type")
                    is_valid = False
                
                # Check justification
                if 'justification' in signal and signal['justification']:
                    print(f"   ✓ Signal has justification")
                else:
                    print(f"   ⚠️ Signal missing justification")
                
                if is_valid:
                    valid_signals += 1
            
            print(f"   📈 Valid signals: {valid_signals}/{len(signals)}")
            
            if valid_signals > 0:
                self.tests_passed += 1
                return True
        
        return False

def main():
    print("🚀 Starting AI Trading System Backend Tests")
    print("=" * 50)
    
    tester = AITradingSystemTester()
    
    # Run all tests
    tests = [
        tester.test_health_endpoint,
        tester.test_market_data_endpoint,
        tester.test_signals_endpoint,
        tester.test_indicators_endpoint,
        tester.test_websocket_connection,
        tester.test_signal_generation_logic
    ]
    
    for test in tests:
        try:
            test()
        except Exception as e:
            print(f"❌ Test failed with exception: {str(e)}")
            tester.tests_run += 1
    
    # Print final results
    print("\n" + "=" * 50)
    print(f"📊 BACKEND TEST RESULTS")
    print(f"Tests Run: {tester.tests_run}")
    print(f"Tests Passed: {tester.tests_passed}")
    print(f"Success Rate: {(tester.tests_passed/tester.tests_run*100):.1f}%" if tester.tests_run > 0 else "0%")
    
    if tester.tests_passed == tester.tests_run:
        print("🎉 All backend tests passed!")
        return 0
    else:
        print("⚠️ Some backend tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())