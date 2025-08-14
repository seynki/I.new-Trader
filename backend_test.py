import requests
import sys
import json
import time
import websocket
import threading
from datetime import datetime

class AITradingSystemTester:
    def __init__(self, base_url="https://live-trading-notify.preview.emergentagent.com"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.ws_messages = []
        self.ws_connected = False
        self.notification_alerts_received = []

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

    def test_notification_settings_endpoints(self):
        """Test notification settings endpoints"""
        print(f"\n🔍 Testing Notification Settings Endpoints...")
        
        # Test GET notification settings
        success_get, response_get = self.run_test(
            "Get Notification Settings",
            "GET",
            "api/notifications/settings",
            200
        )
        
        if not success_get:
            return False
            
        # Verify default settings structure
        if isinstance(response_get, dict):
            expected_fields = ['user_id', 'notifications_enabled', 'min_score_threshold', 
                             'min_rr_threshold', 'notification_types', 'timeframes']
            for field in expected_fields:
                if field in response_get:
                    print(f"   ✓ Settings field '{field}' present")
                else:
                    print(f"   ⚠️ Settings field '{field}' missing")
        
        # Test POST notification settings
        test_settings = {
            "user_id": "test_user",
            "iq_option_email": "test@example.com",
            "notifications_enabled": True,
            "min_score_threshold": 75,
            "min_rr_threshold": 2.0,
            "max_risk_threshold": 0.8,
            "notification_types": ["desktop", "websocket"],
            "timeframes": ["5m", "15m"]
        }
        
        success_post, response_post = self.run_test(
            "Update Notification Settings",
            "POST",
            "api/notifications/settings",
            200,
            test_settings
        )
        
        if success_post and isinstance(response_post, dict):
            if response_post.get('status') == 'success':
                print(f"   ✓ Settings updated successfully")
                return True
            else:
                print(f"   ⚠️ Settings update response unexpected: {response_post}")
        
        return success_get and success_post

    def test_alerts_endpoint(self):
        """Test alerts endpoint"""
        print(f"\n🔍 Testing Alerts Endpoint...")
        
        success, response = self.run_test(
            "Get Trading Alerts",
            "GET",
            "api/alerts?limit=10",
            200
        )
        
        if success and isinstance(response, dict):
            if 'alerts' in response:
                alerts = response['alerts']
                print(f"   ✓ Found {len(alerts)} alerts")
                
                if alerts:
                    sample_alert = alerts[0]
                    required_fields = ['id', 'signal_id', 'alert_type', 'title', 
                                     'message', 'priority', 'timestamp']
                    for field in required_fields:
                        if field in sample_alert:
                            print(f"   ✓ Alert field '{field}' present")
                        else:
                            print(f"   ⚠️ Alert field '{field}' missing")
                    
                    # Check alert priorities
                    priorities = set()
                    for alert in alerts[:5]:  # Check first 5 alerts
                        if 'priority' in alert:
                            priorities.add(alert['priority'])
                    
                    valid_priorities = {'low', 'medium', 'high', 'critical'}
                    if priorities.issubset(valid_priorities):
                        print(f"   ✓ Alert priorities valid: {priorities}")
                    else:
                        print(f"   ⚠️ Invalid alert priorities found: {priorities - valid_priorities}")
                
                return True
            else:
                print(f"   ❌ 'alerts' key missing in response")
        
        return success

    def test_iq_option_endpoints(self):
        """Test IQ Option integration endpoints"""
        print(f"\n🔍 Testing IQ Option Integration Endpoints...")
        
        # Test connection test endpoint
        success_conn, response_conn = self.run_test(
            "IQ Option Connection Test",
            "POST",
            "api/iq-option/test-connection",
            200
        )
        
        if success_conn and isinstance(response_conn, dict):
            expected_fields = ['status', 'message', 'email', 'connected', 'account_type', 'balance']
            for field in expected_fields:
                if field in response_conn:
                    print(f"   ✓ Connection test field '{field}' present")
                else:
                    print(f"   ⚠️ Connection test field '{field}' missing")
            
            if response_conn.get('status') == 'success' and response_conn.get('connected'):
                print(f"   ✓ IQ Option connection test successful")
            else:
                print(f"   ⚠️ IQ Option connection test failed")
        
        # Test signal formatting (need to get a signal ID first)
        signals_success, signals_response = self.run_test(
            "Get Signals for IQ Option Test",
            "GET",
            "api/signals?limit=1",
            200
        )
        
        if signals_success and isinstance(signals_response, dict) and 'signals' in signals_response:
            signals = signals_response['signals']
            if signals and 'id' in signals[0]:
                signal_id = signals[0]['id']
                
                success_format, response_format = self.run_test(
                    "Format Signal for IQ Option",
                    "POST",
                    f"api/iq-option/format-signal/{signal_id}",
                    200
                )
                
                if success_format and isinstance(response_format, dict):
                    if 'iq_option_format' in response_format:
                        iq_format = response_format['iq_option_format']
                        expected_iq_fields = ['asset', 'action', 'amount', 'expiration', 
                                            'entry_price', 'confidence']
                        for field in expected_iq_fields:
                            if field in iq_format:
                                print(f"   ✓ IQ Option format field '{field}' present")
                            else:
                                print(f"   ⚠️ IQ Option format field '{field}' missing")
                        
                        return success_conn and success_format
                    else:
                        print(f"   ❌ 'iq_option_format' missing in response")
            else:
                print(f"   ⚠️ No signals available for IQ Option format test")
        
        return success_conn

    def test_stats_endpoint(self):
        """Test system statistics endpoint"""
        print(f"\n🔍 Testing System Statistics Endpoint...")
        
        success, response = self.run_test(
            "System Statistics",
            "GET",
            "api/stats",
            200
        )
        
        if success and isinstance(response, dict):
            expected_fields = ['score_avg', 'max_score', 'rr_avg', 'trending_markets', 
                             'total_signals', 'active_symbols', 'volatility_regime']
            for field in expected_fields:
                if field in response:
                    print(f"   ✓ Stats field '{field}' present: {response[field]}")
                else:
                    print(f"   ⚠️ Stats field '{field}' missing")
            
            # Validate data ranges
            if 'score_avg' in response:
                score_avg = response['score_avg']
                if 0 <= score_avg <= 100:
                    print(f"   ✓ Average score in valid range: {score_avg}")
                else:
                    print(f"   ⚠️ Average score out of range: {score_avg}")
            
            if 'rr_avg' in response:
                rr_avg = response['rr_avg']
                if rr_avg >= 1.0:
                    print(f"   ✓ Average RR ratio valid: {rr_avg}")
                else:
                    print(f"   ⚠️ Average RR ratio below 1.0: {rr_avg}")
            
            return True
        
        return success

    def test_websocket_notifications(self):
        """Test WebSocket notifications and alerts"""
        print(f"\n🔍 Testing WebSocket Notifications...")
        
        ws_url = self.base_url.replace('https', 'wss') + '/api/ws'
        print(f"   WebSocket URL: {ws_url}")
        
        def on_message(ws, message):
            try:
                data = json.loads(message)
                self.ws_messages.append(data)
                
                # Check for trading alerts
                if data.get('type') == 'trading_alert':
                    self.notification_alerts_received.append(data)
                    print(f"   🚨 Trading alert received: {data.get('data', {}).get('title', 'Unknown')}")
                elif data.get('type') == 'new_signal':
                    print(f"   📈 New signal received: {data.get('data', {}).get('symbol', 'Unknown')}")
                elif data.get('type') == 'market_update':
                    print(f"   📊 Market update received")
                else:
                    print(f"   📨 Message received: {data.get('type', 'unknown')}")
                    
            except Exception as e:
                print(f"   ❌ Error parsing WebSocket message: {e}")

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
            
            # Wait longer for notifications
            print(f"   ⏳ Waiting 10 seconds for notifications...")
            time.sleep(10)
            
            if self.ws_connected:
                self.tests_passed += 1
                print(f"   ✅ WebSocket connection successful")
                print(f"   📊 Total messages received: {len(self.ws_messages)}")
                print(f"   🚨 Trading alerts received: {len(self.notification_alerts_received)}")
                
                # Analyze message types
                message_types = {}
                for msg in self.ws_messages:
                    if isinstance(msg, dict) and 'type' in msg:
                        msg_type = msg['type']
                        message_types[msg_type] = message_types.get(msg_type, 0) + 1
                
                print(f"   📋 Message type breakdown: {message_types}")
                
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

    def test_notification_system_integration(self):
        """Test complete notification system integration"""
        print(f"\n🔍 Testing Notification System Integration...")
        
        # First, update notification settings to ensure notifications are enabled
        test_settings = {
            "user_id": "integration_test",
            "notifications_enabled": True,
            "min_score_threshold": 60,  # Lower threshold to catch more signals
            "min_rr_threshold": 1.5,
            "notification_types": ["websocket"],
            "timeframes": ["1m", "5m", "15m"]
        }
        
        settings_success, _ = self.run_test(
            "Setup Notification Settings for Integration Test",
            "POST",
            "api/notifications/settings",
            200,
            test_settings
        )
        
        if not settings_success:
            print(f"   ❌ Failed to setup notification settings")
            return False
        
        print(f"   ✓ Notification settings configured")
        
        # Wait for signal generation and notifications
        print(f"   ⏳ Waiting 15 seconds for signal generation and notifications...")
        initial_signal_count = len(self.ws_messages)
        time.sleep(15)
        
        # Check if new signals were generated
        signals_success, signals_response = self.run_test(
            "Check Recent Signals",
            "GET",
            "api/signals?limit=5",
            200
        )
        
        if signals_success and isinstance(signals_response, dict):
            signals = signals_response.get('signals', [])
            print(f"   📈 Found {len(signals)} recent signals")
            
            # Check if alerts were created
            alerts_success, alerts_response = self.run_test(
                "Check Recent Alerts",
                "GET",
                "api/alerts?limit=5",
                200
            )
            
            if alerts_success and isinstance(alerts_response, dict):
                alerts = alerts_response.get('alerts', [])
                print(f"   🚨 Found {len(alerts)} recent alerts")
                
                # Verify signal-alert correlation
                signal_ids = {s.get('id') for s in signals if 'id' in s}
                alert_signal_ids = {a.get('signal_id') for a in alerts if 'signal_id' in a}
                
                correlated_alerts = signal_ids.intersection(alert_signal_ids)
                print(f"   🔗 Correlated signal-alert pairs: {len(correlated_alerts)}")
                
                if len(signals) > 0 and len(alerts) > 0:
                    print(f"   ✅ Notification system integration working")
                    self.tests_passed += 1
                    return True
                else:
                    print(f"   ⚠️ No signals or alerts generated during test period")
            else:
                print(f"   ❌ Failed to fetch alerts")
        else:
            print(f"   ❌ Failed to fetch signals")
        
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