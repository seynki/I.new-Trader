import requests
import sys
import json
import time
import websocket
import threading
from datetime import datetime

class AITradingSystemTester:
    def __init__(self, base_url="https://live-trade-buttons.preview.emergentagent.com"):
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

    def test_review_request_endpoints(self):
        """Test specific endpoints mentioned in review request"""
        print(f"\n🎯 Testing Review Request Specific Endpoints...")
        
        all_passed = True
        
        # 1) GET /api/stats - should return score_avg, max_score, rr_avg, trending_markets
        print(f"\n1️⃣ Testing GET /api/stats endpoint...")
        success, response = self.run_test(
            "Stats Endpoint (Review Request)",
            "GET",
            "api/stats",
            200
        )
        
        if success and isinstance(response, dict):
            required_fields = ['score_avg', 'max_score', 'rr_avg', 'trending_markets']
            for field in required_fields:
                if field in response:
                    print(f"   ✅ Required field '{field}' present: {response[field]}")
                else:
                    print(f"   ❌ Required field '{field}' missing")
                    all_passed = False
        else:
            all_passed = False
        
        # 2) GET /api/market-data - should return data[] and ensure no SP500/NAS100
        print(f"\n2️⃣ Testing GET /api/market-data endpoint...")
        success, response = self.run_test(
            "Market Data Endpoint (Review Request)",
            "GET",
            "api/market-data",
            200
        )
        
        if success and isinstance(response, dict):
            if 'data' in response and isinstance(response['data'], list):
                market_data = response['data']
                print(f"   ✅ Found data[] with {len(market_data)} markets")
                
                # Check for SP500 and NAS100 symbols (should NOT be present)
                symbols = [item.get('symbol', '') for item in market_data]
                forbidden_symbols = ['SP500', 'NAS100']
                
                for symbol in forbidden_symbols:
                    if symbol in symbols:
                        print(f"   ❌ Forbidden symbol '{symbol}' found in market data")
                        all_passed = False
                    else:
                        print(f"   ✅ Forbidden symbol '{symbol}' correctly excluded")
                
                print(f"   📊 Available symbols: {symbols}")
            else:
                print(f"   ❌ 'data' field missing or not a list")
                all_passed = False
        else:
            all_passed = False
        
        # 3) GET /api/signals?limit=5 - should return signals[] with confidence_score, risk_reward_ratio
        print(f"\n3️⃣ Testing GET /api/signals?limit=5 endpoint...")
        success, response = self.run_test(
            "Signals Endpoint (Review Request)",
            "GET",
            "api/signals?limit=5",
            200
        )
        
        if success and isinstance(response, dict):
            if 'signals' in response and isinstance(response['signals'], list):
                signals = response['signals']
                print(f"   ✅ Found signals[] with {len(signals)} signals")
                
                if signals:
                    # Check required fields in first signal
                    sample_signal = signals[0]
                    required_fields = ['confidence_score', 'risk_reward_ratio']
                    for field in required_fields:
                        if field in sample_signal:
                            print(f"   ✅ Required field '{field}' present: {sample_signal[field]}")
                        else:
                            print(f"   ❌ Required field '{field}' missing")
                            all_passed = False
                else:
                    print(f"   ⚠️ No signals available, but endpoint working")
            else:
                print(f"   ❌ 'signals' field missing or not a list")
                all_passed = False
        else:
            all_passed = False
        
        # 4) WebSocket /api/ws - connect, wait 3-5s, verify market_update messages
        print(f"\n4️⃣ Testing WebSocket /api/ws endpoint...")
        ws_url = self.base_url.replace('https', 'wss') + '/api/ws'
        print(f"   WebSocket URL: {ws_url}")
        
        market_updates_received = []
        ws_connected = False
        
        def on_message(ws, message):
            nonlocal market_updates_received
            try:
                data = json.loads(message)
                if data.get('type') == 'market_update':
                    market_updates_received.append(data)
                    print(f"   📊 Market update received (total: {len(market_updates_received)})")
                    
                    # Optional: Check for SP500/NAS100 in market updates
                    if 'data' in data and isinstance(data['data'], list):
                        symbols_in_update = [item.get('symbol', '') for item in data['data']]
                        forbidden_in_update = [s for s in ['SP500', 'NAS100'] if s in symbols_in_update]
                        if forbidden_in_update:
                            print(f"   ⚠️ Forbidden symbols in market update: {forbidden_in_update}")
                        else:
                            print(f"   ✅ No forbidden symbols in market update")
                else:
                    print(f"   📨 Other message type: {data.get('type', 'unknown')}")
            except Exception as e:
                print(f"   ❌ Error parsing WebSocket message: {e}")

        def on_error(ws, error):
            print(f"   ❌ WebSocket error: {error}")

        def on_close(ws, close_status_code, close_msg):
            print(f"   🔌 WebSocket closed")

        def on_open(ws):
            nonlocal ws_connected
            print(f"   ✅ WebSocket connected successfully")
            ws_connected = True

        try:
            import websocket
            ws = websocket.WebSocketApp(ws_url,
                                      on_open=on_open,
                                      on_message=on_message,
                                      on_error=on_error,
                                      on_close=on_close)
            
            # Run WebSocket in a separate thread
            wst = threading.Thread(target=ws.run_forever)
            wst.daemon = True
            wst.start()
            
            # Wait 3-5 seconds as requested
            print(f"   ⏳ Waiting 5 seconds for market_update messages...")
            time.sleep(5)
            
            if ws_connected:
                print(f"   ✅ WebSocket connection successful")
                print(f"   📊 Market updates received: {len(market_updates_received)}")
                
                if len(market_updates_received) > 0:
                    print(f"   ✅ Continuous market_update messages confirmed")
                else:
                    print(f"   ⚠️ No market_update messages received in 5 seconds")
                    all_passed = False
                
                ws.close()
            else:
                print(f"   ❌ WebSocket connection failed")
                all_passed = False
                
        except Exception as e:
            print(f"   ❌ WebSocket test failed: {str(e)}")
            all_passed = False
        
        if all_passed:
            self.tests_passed += 1
            print(f"\n🎉 All review request endpoints PASSED!")
        else:
            print(f"\n❌ Some review request endpoints FAILED!")
        
        self.tests_run += 1
        return all_passed

    def test_iq_option_formatting_verification(self):
        """Test IQ Option formatting in alerts as per review request"""
        print(f"\n🎯 Testing IQ Option Formatting Verification...")
        
        all_passed = True
        
        # 1) Connect to WebSocket for 20s and collect trading_alert messages
        print(f"\n1️⃣ Testing WebSocket /api/ws for trading alerts (20s)...")
        ws_url = self.base_url.replace('https', 'wss') + '/api/ws'
        print(f"   WebSocket URL: {ws_url}")
        
        trading_alerts_received = []
        ws_connected = False
        
        def on_message(ws, message):
            nonlocal trading_alerts_received
            try:
                data = json.loads(message)
                if data.get('type') == 'trading_alert':
                    trading_alerts_received.append(data)
                    print(f"   🚨 Trading alert received: {len(trading_alerts_received)}")
                    
                    # Inspect the alert data immediately
                    alert_data = data.get('data', {})
                    title = alert_data.get('title', '')
                    message = alert_data.get('message', '')
                    
                    print(f"      Title: {title}")
                    print(f"      Message: {message}")
                    
                    # Check title format
                    if 'BUY Signal - ' in title or 'SELL Signal - ' in title:
                        if '/' in title:
                            print(f"      ✅ Title contains signal type and '/' symbol")
                        else:
                            print(f"      ❌ Title missing '/' in symbol")
                    else:
                        print(f"      ❌ Title doesn't match expected format")
                    
                    # Check message format
                    if 'Oportunidade' in message and 'Ativo: ' in message and ' | ' in message:
                        if '\n' not in message:
                            print(f"      ✅ Message format correct with '|' separators, no newlines")
                        else:
                            print(f"      ❌ Message contains newline characters")
                    else:
                        print(f"      ❌ Message format incorrect")
                        
            except Exception as e:
                print(f"   ❌ Error parsing WebSocket message: {e}")

        def on_error(ws, error):
            print(f"   ❌ WebSocket error: {error}")

        def on_close(ws, close_status_code, close_msg):
            print(f"   🔌 WebSocket closed")

        def on_open(ws):
            nonlocal ws_connected
            print(f"   ✅ WebSocket connected successfully")
            ws_connected = True

        try:
            import websocket
            ws = websocket.WebSocketApp(ws_url,
                                      on_open=on_open,
                                      on_message=on_message,
                                      on_error=on_error,
                                      on_close=on_close)
            
            # Run WebSocket in a separate thread
            wst = threading.Thread(target=ws.run_forever)
            wst.daemon = True
            wst.start()
            
            # Wait 20 seconds as requested
            print(f"   ⏳ Waiting 20 seconds for trading_alert messages...")
            time.sleep(20)
            
            if ws_connected:
                print(f"   ✅ WebSocket connection successful")
                print(f"   🚨 Trading alerts received: {len(trading_alerts_received)}")
                
                # Analyze collected trading alerts
                if len(trading_alerts_received) > 0:
                    print(f"   📊 Analyzing {len(trading_alerts_received)} trading alerts...")
                    
                    valid_alerts = 0
                    for alert in trading_alerts_received:
                        alert_data = alert.get('data', {})
                        title = alert_data.get('title', '')
                        message = alert_data.get('message', '')
                        
                        # Validate title format
                        title_valid = False
                        if ('BUY Signal - ' in title or 'SELL Signal - ' in title) and '/' in title:
                            title_valid = True
                        
                        # Validate message format
                        message_valid = False
                        if ('Oportunidade' in message and 'Ativo: ' in message and 
                            ' | ' in message and '\n' not in message):
                            message_valid = True
                        
                        if title_valid and message_valid:
                            valid_alerts += 1
                    
                    print(f"   📈 Valid formatted alerts: {valid_alerts}/{len(trading_alerts_received)}")
                    
                    if valid_alerts == len(trading_alerts_received):
                        print(f"   ✅ All trading alerts properly formatted")
                    else:
                        print(f"   ❌ Some trading alerts have formatting issues")
                        all_passed = False
                else:
                    print(f"   ⚠️ No trading alerts received in 20 seconds")
                    # This might not be a failure if no signals were generated
                
                ws.close()
            else:
                print(f"   ❌ WebSocket connection failed")
                all_passed = False
                
        except Exception as e:
            print(f"   ❌ WebSocket test failed: {str(e)}")
            all_passed = False
        
        # 2) Test GET /api/alerts?limit=3 for symbol formatting
        print(f"\n2️⃣ Testing GET /api/alerts?limit=3 for symbol formatting...")
        success, response = self.run_test(
            "Recent Alerts Symbol Formatting",
            "GET",
            "api/alerts?limit=3",
            200
        )
        
        if success and isinstance(response, dict):
            if 'alerts' in response and isinstance(response['alerts'], list):
                alerts = response['alerts']
                print(f"   ✅ Found {len(alerts)} recent alerts")
                
                if alerts:
                    valid_alert_formatting = 0
                    for alert in alerts:
                        title = alert.get('title', '')
                        message = alert.get('message', '')
                        
                        print(f"   📋 Alert Title: {title}")
                        print(f"   📋 Alert Message: {message}")
                        
                        # Check title has formatted symbol
                        title_has_slash = '/' in title
                        # Check message has formatted symbol and proper structure
                        message_has_formatted_symbol = 'Ativo: ' in message and '/' in message
                        message_has_separators = ' | ' in message
                        message_no_newlines = '\n' not in message
                        
                        if (title_has_slash and message_has_formatted_symbol and 
                            message_has_separators and message_no_newlines):
                            valid_alert_formatting += 1
                            print(f"   ✅ Alert formatting valid")
                        else:
                            print(f"   ❌ Alert formatting issues:")
                            if not title_has_slash:
                                print(f"      - Title missing '/' in symbol")
                            if not message_has_formatted_symbol:
                                print(f"      - Message missing formatted symbol")
                            if not message_has_separators:
                                print(f"      - Message missing ' | ' separators")
                            if not message_no_newlines:
                                print(f"      - Message contains newlines")
                    
                    print(f"   📊 Valid formatted alerts: {valid_alert_formatting}/{len(alerts)}")
                    
                    if valid_alert_formatting != len(alerts):
                        all_passed = False
                else:
                    print(f"   ⚠️ No alerts available for formatting check")
            else:
                print(f"   ❌ 'alerts' field missing or not a list")
                all_passed = False
        else:
            all_passed = False
        
        # 3) Test POST /api/iq-option/test-connection
        print(f"\n3️⃣ Testing POST /api/iq-option/test-connection...")
        success, response = self.run_test(
            "IQ Option Connection Test",
            "POST",
            "api/iq-option/test-connection",
            200
        )
        
        if success and isinstance(response, dict):
            required_fields = ['status', 'message', 'email', 'connected', 'account_type', 'balance']
            missing_fields = []
            
            for field in required_fields:
                if field in response:
                    print(f"   ✅ Field '{field}' present: {response[field]}")
                else:
                    print(f"   ❌ Field '{field}' missing")
                    missing_fields.append(field)
            
            if missing_fields:
                print(f"   ❌ Missing required fields: {missing_fields}")
                all_passed = False
            else:
                print(f"   ✅ All required fields present")
        else:
            all_passed = False
        
        if all_passed:
            self.tests_passed += 1
            print(f"\n🎉 IQ Option formatting verification PASSED!")
        else:
            print(f"\n❌ IQ Option formatting verification FAILED!")
        
        self.tests_run += 1
        return all_passed

    def test_minimum_score_threshold_validation(self):
        """Test minimum score threshold logic at 70% as per review request"""
        print(f"\n🎯 Testing Minimum Score Threshold Validation (70%)...")
        
        all_passed = True
        
        # 1) GET /api/notifications/settings and confirm min_score_threshold == 70
        print(f"\n1️⃣ Testing GET /api/notifications/settings for min_score_threshold == 70...")
        success, response = self.run_test(
            "Get Notification Settings - Check Threshold",
            "GET",
            "api/notifications/settings",
            200
        )
        
        if success and isinstance(response, dict):
            min_score_threshold = response.get('min_score_threshold')
            if min_score_threshold == 70:
                print(f"   ✅ min_score_threshold is correctly set to 70")
            else:
                print(f"   ❌ min_score_threshold is {min_score_threshold}, expected 70")
                all_passed = False
        else:
            print(f"   ❌ Failed to get notification settings")
            all_passed = False
        
        # 2) Wait for signals and verify alerts only created when confidence_score >= 70
        print(f"\n2️⃣ Testing signal generation and alert creation with 70% threshold...")
        print(f"   ⏳ Waiting for signals to be generated (system generates every ~8s)...")
        
        # Wait for multiple signal generation cycles
        time.sleep(25)  # Wait ~3 cycles to get enough samples
        
        # Get recent alerts
        success, response = self.run_test(
            "Get Recent Alerts for Threshold Validation",
            "GET",
            "api/alerts?limit=10",
            200
        )
        
        if success and isinstance(response, dict) and 'alerts' in response:
            alerts = response['alerts']
            print(f"   📊 Found {len(alerts)} recent alerts")
            
            if len(alerts) >= 5:
                # Sample 5 alerts and verify all have confidence_score >= 70
                sample_alerts = alerts[:5]
                valid_threshold_alerts = 0
                
                print(f"   🔍 Analyzing 5 sample alerts for confidence score >= 70...")
                
                for i, alert in enumerate(sample_alerts, 1):
                    signal_id = alert.get('signal_id')
                    if signal_id:
                        # Get the corresponding signal
                        signal_success, signal_response = self.run_test(
                            f"Get Signal {i} for Alert Validation",
                            "GET",
                            f"api/signals?limit=50",  # Get more signals to find the matching one
                            200
                        )
                        
                        if signal_success and isinstance(signal_response, dict):
                            signals = signal_response.get('signals', [])
                            matching_signal = None
                            
                            for signal in signals:
                                if signal.get('id') == signal_id:
                                    matching_signal = signal
                                    break
                            
                            if matching_signal:
                                confidence_score = matching_signal.get('confidence_score')
                                print(f"   📈 Alert {i}: Signal ID {signal_id[:8]}... has confidence_score = {confidence_score}")
                                
                                if confidence_score >= 70:
                                    print(f"      ✅ Confidence score {confidence_score} >= 70 (threshold met)")
                                    valid_threshold_alerts += 1
                                else:
                                    print(f"      ❌ Confidence score {confidence_score} < 70 (threshold violated)")
                                    all_passed = False
                            else:
                                print(f"   ⚠️ Alert {i}: Could not find matching signal with ID {signal_id}")
                        else:
                            print(f"   ❌ Alert {i}: Failed to fetch signals for validation")
                    else:
                        print(f"   ❌ Alert {i}: Missing signal_id")
                        all_passed = False
                
                print(f"   📊 Valid threshold alerts: {valid_threshold_alerts}/5")
                
                if valid_threshold_alerts == 5:
                    print(f"   ✅ All sampled alerts have confidence_score >= 70")
                else:
                    print(f"   ❌ Some alerts violate the 70% threshold requirement")
                    all_passed = False
                    
            else:
                print(f"   ⚠️ Not enough alerts ({len(alerts)}) to sample 5 for validation")
                # This might not be a failure if system is just starting
                if len(alerts) > 0:
                    print(f"   🔍 Checking available {len(alerts)} alerts...")
                    for i, alert in enumerate(alerts, 1):
                        signal_id = alert.get('signal_id')
                        if signal_id:
                            # Quick check on available alerts
                            signal_success, signal_response = self.run_test(
                                f"Get Signals for Available Alert {i}",
                                "GET",
                                f"api/signals?limit=20",
                                200
                            )
                            
                            if signal_success and isinstance(signal_response, dict):
                                signals = signal_response.get('signals', [])
                                for signal in signals:
                                    if signal.get('id') == signal_id:
                                        confidence_score = signal.get('confidence_score')
                                        print(f"   📈 Available Alert {i}: confidence_score = {confidence_score}")
                                        if confidence_score < 70:
                                            print(f"      ❌ Threshold violation detected!")
                                            all_passed = False
                                        break
        else:
            print(f"   ❌ Failed to get alerts for threshold validation")
            all_passed = False
        
        # 3) Test POST /api/notifications/settings accepts changes and setting 70 explicitly remains 70
        print(f"\n3️⃣ Testing POST /api/notifications/settings with explicit 70% threshold...")
        
        test_settings = {
            "user_id": "threshold_test_user",
            "notifications_enabled": True,
            "min_score_threshold": 70,  # Explicitly set to 70
            "min_rr_threshold": 1.5,
            "notification_types": ["websocket"],
            "timeframes": ["1m", "5m", "15m"]
        }
        
        success, response = self.run_test(
            "Update Notification Settings - Set Threshold to 70",
            "POST",
            "api/notifications/settings",
            200,
            test_settings
        )
        
        if success and isinstance(response, dict):
            if response.get('status') == 'success':
                print(f"   ✅ Settings update successful")
                
                # Verify the setting persisted by getting it back
                success_verify, response_verify = self.run_test(
                    "Verify Threshold Setting Persisted",
                    "GET",
                    "api/notifications/settings",
                    200
                )
                
                if success_verify and isinstance(response_verify, dict):
                    persisted_threshold = response_verify.get('min_score_threshold')
                    if persisted_threshold == 70:
                        print(f"   ✅ Threshold correctly persisted as 70")
                    else:
                        print(f"   ❌ Threshold not persisted correctly: {persisted_threshold}")
                        all_passed = False
                else:
                    print(f"   ❌ Failed to verify persisted settings")
                    all_passed = False
            else:
                print(f"   ❌ Settings update failed: {response}")
                all_passed = False
        else:
            print(f"   ❌ Failed to update notification settings")
            all_passed = False
        
        if all_passed:
            self.tests_passed += 1
            print(f"\n🎉 Minimum score threshold validation (70%) PASSED!")
        else:
            print(f"\n❌ Minimum score threshold validation (70%) FAILED!")
        
        self.tests_run += 1
        return all_passed

    def test_quick_order_endpoint(self):
        """Test POST /api/trading/quick-order endpoint as per review request"""
        print(f"\n🎯 Testing Quick Order API Endpoint...")
        
        all_passed = True
        
        # 1) Test valid payload
        print(f"\n1️⃣ Testing POST /api/trading/quick-order with valid payload...")
        valid_payload = {
            "asset": "EURUSD",
            "direction": "call",
            "amount": 10,
            "expiration": 1,
            "account_type": "demo",
            "option_type": "binary"
        }
        
        success, response = self.run_test(
            "Quick Order - Valid Payload",
            "POST",
            "api/trading/quick-order",
            200,
            valid_payload
        )
        
        if success and isinstance(response, dict):
            # Check required response fields
            required_fields = ['success', 'message', 'order_id', 'echo']
            for field in required_fields:
                if field in response:
                    print(f"   ✅ Response field '{field}' present: {response[field]}")
                else:
                    print(f"   ❌ Response field '{field}' missing")
                    all_passed = False
            
            # Verify success is true
            if response.get('success') == True:
                print(f"   ✅ Success field is True")
            else:
                print(f"   ❌ Success field is not True: {response.get('success')}")
                all_passed = False
            
            # Verify message contains "Fase 1"
            message = response.get('message', '')
            if 'Fase 1' in message or 'fase 1' in message:
                print(f"   ✅ Message contains 'Fase 1': {message}")
            else:
                print(f"   ❌ Message does not contain 'Fase 1': {message}")
                all_passed = False
            
            # Verify order_id is a string
            order_id = response.get('order_id')
            if isinstance(order_id, str) and len(order_id) > 0:
                print(f"   ✅ Order ID is valid string: {order_id}")
            else:
                print(f"   ❌ Order ID is not valid string: {order_id}")
                all_passed = False
            
            # Verify echo contains sent fields
            echo = response.get('echo', {})
            if isinstance(echo, dict):
                for key, value in valid_payload.items():
                    if echo.get(key) == value:
                        print(f"   ✅ Echo field '{key}' matches: {value}")
                    else:
                        print(f"   ❌ Echo field '{key}' mismatch: expected {value}, got {echo.get(key)}")
                        all_passed = False
            else:
                print(f"   ❌ Echo is not a dict: {echo}")
                all_passed = False
        else:
            all_passed = False
        
        # 2) Test negative validations
        print(f"\n2️⃣ Testing negative validations...")
        
        negative_tests = [
            {
                "name": "Invalid direction 'buy'",
                "payload": {**valid_payload, "direction": "buy"},
                "expected_status": 400
            },
            {
                "name": "Invalid account_type 'paper'",
                "payload": {**valid_payload, "account_type": "paper"},
                "expected_status": 400
            },
            {
                "name": "Invalid option_type 'turbo'",
                "payload": {**valid_payload, "option_type": "turbo"},
                "expected_status": 400
            },
            {
                "name": "Invalid amount 0",
                "payload": {**valid_payload, "amount": 0},
                "expected_status": 400
            },
            {
                "name": "Invalid expiration 0",
                "payload": {**valid_payload, "expiration": 0},
                "expected_status": 400
            },
            {
                "name": "Invalid expiration 61",
                "payload": {**valid_payload, "expiration": 61},
                "expected_status": 400
            }
        ]
        
        for test_case in negative_tests:
            print(f"\n   Testing: {test_case['name']}")
            success, response = self.run_test(
                f"Quick Order - {test_case['name']}",
                "POST",
                "api/trading/quick-order",
                test_case['expected_status'],
                test_case['payload']
            )
            
            if success:
                print(f"   ✅ Correctly returned {test_case['expected_status']} for {test_case['name']}")
                # Check if response contains error detail
                if isinstance(response, dict) and 'detail' in response:
                    print(f"      Error detail: {response['detail']}")
            else:
                print(f"   ❌ Failed validation for {test_case['name']}")
                all_passed = False
        
        # 3) Test ingress compatibility (route works with /api/...)
        print(f"\n3️⃣ Testing ingress compatibility...")
        print(f"   ✅ All tests use '/api/trading/quick-order' route - ingress compatible")
        
        if all_passed:
            self.tests_passed += 1
            print(f"\n🎉 Quick Order API endpoint tests PASSED!")
        else:
            print(f"\n❌ Quick Order API endpoint tests FAILED!")
        
        self.tests_run += 1
        return all_passed

    def test_sell_signals_review_request(self):
        """Test backend emits SELL signals as per review request"""
        print(f"\n🎯 Testing SELL Signals Review Request...")
        
        all_passed = True
        sell_signals_found = []
        
        # 1) Connect to /api/signals?limit=50 and scan for SELL signals, retry up to 3 times
        print(f"\n1️⃣ Testing /api/signals?limit=50 for SELL signals (up to 3 attempts)...")
        
        for attempt in range(1, 4):
            print(f"\n   Attempt {attempt}/3:")
            success, response = self.run_test(
                f"Get Signals - Attempt {attempt}",
                "GET",
                "api/signals?limit=50",
                200
            )
            
            if success and isinstance(response, dict) and 'signals' in response:
                signals = response['signals']
                print(f"   📊 Found {len(signals)} total signals")
                
                # Scan for SELL signals
                sell_signals = [s for s in signals if s.get('signal_type') == 'SELL']
                print(f"   🔴 Found {len(sell_signals)} SELL signals")
                
                if sell_signals:
                    sell_signals_found.extend(sell_signals)
                    print(f"   ✅ SELL signals found on attempt {attempt}")
                    break
                else:
                    print(f"   ⚠️ No SELL signals found on attempt {attempt}")
                    if attempt < 3:
                        print(f"   ⏳ Waiting 20 seconds before next attempt...")
                        time.sleep(20)
            else:
                print(f"   ❌ Failed to get signals on attempt {attempt}")
                if attempt < 3:
                    time.sleep(20)
        
        if not sell_signals_found:
            print(f"   ❌ No SELL signals found after 3 attempts")
            all_passed = False
            
            # Get sample of recent signals for analysis
            print(f"   📋 Getting sample of recent signals for analysis...")
            success, response = self.run_test(
                "Sample Recent Signals",
                "GET",
                "api/signals?limit=10",
                200
            )
            
            if success and isinstance(response, dict) and 'signals' in response:
                signals = response['signals']
                print(f"   📊 Sample signals analysis:")
                signal_types = {}
                confidence_scores = []
                
                for signal in signals:
                    signal_type = signal.get('signal_type', 'UNKNOWN')
                    signal_types[signal_type] = signal_types.get(signal_type, 0) + 1
                    
                    confidence = signal.get('confidence_score', 0)
                    confidence_scores.append(confidence)
                
                print(f"      Signal types: {signal_types}")
                if confidence_scores:
                    avg_confidence = sum(confidence_scores) / len(confidence_scores)
                    min_confidence = min(confidence_scores)
                    max_confidence = max(confidence_scores)
                    print(f"      Confidence scores - Avg: {avg_confidence:.1f}, Min: {min_confidence}, Max: {max_confidence}")
                
                print(f"   💡 SUGGESTION: Consider relaxing thresholds or adjusting signal generator to produce more SELL signals")
        else:
            print(f"   ✅ Found {len(sell_signals_found)} SELL signals total")
        
        # 2) Validate /api/signals with filters returns SELL when regimes or symbols are changed
        print(f"\n2️⃣ Testing /api/signals with filters for SELL signals...")
        
        filter_tests = [
            ("symbols=BTCUSDT,EURUSD", "api/signals?symbols=BTCUSDT,EURUSD&limit=50"),
            ("regimes=trending,sideways", "api/signals?regimes=trending,sideways&limit=50"),
            ("since_minutes=240", "api/signals?since_minutes=240&limit=50"),
            ("combined filters", "api/signals?symbols=BTCUSDT,EURUSD&regimes=trending,sideways&since_minutes=240&limit=50")
        ]
        
        filter_sell_found = False
        for filter_name, endpoint in filter_tests:
            print(f"\n   Testing filter: {filter_name}")
            success, response = self.run_test(
                f"Filtered Signals - {filter_name}",
                "GET",
                endpoint,
                200
            )
            
            if success and isinstance(response, dict) and 'signals' in response:
                signals = response['signals']
                sell_signals = [s for s in signals if s.get('signal_type') == 'SELL']
                
                print(f"      📊 Total signals: {len(signals)}, SELL signals: {len(sell_signals)}")
                
                if sell_signals:
                    filter_sell_found = True
                    print(f"      ✅ SELL signals found with {filter_name}")
                    
                    # Show sample SELL signal details
                    sample_sell = sell_signals[0]
                    print(f"      📋 Sample SELL signal:")
                    print(f"         Symbol: {sample_sell.get('symbol', 'N/A')}")
                    print(f"         Confidence: {sample_sell.get('confidence_score', 'N/A')}")
                    print(f"         Regime: {sample_sell.get('regime', 'N/A')}")
                    print(f"         Timeframe: {sample_sell.get('timeframe', 'N/A')}")
                else:
                    print(f"      ⚠️ No SELL signals found with {filter_name}")
            else:
                print(f"      ❌ Failed to get filtered signals for {filter_name}")
        
        if not filter_sell_found:
            print(f"   ❌ No SELL signals found across any filter combinations")
            all_passed = False
        
        # 3) Assert schema contains required fields: symbol, signal_type, confidence_score, timeframe, justification
        print(f"\n3️⃣ Validating signal schema contains required fields...")
        
        # Use any signals we found (SELL or otherwise) to validate schema
        test_signals = sell_signals_found if sell_signals_found else []
        
        if not test_signals:
            # Get any signals for schema validation
            success, response = self.run_test(
                "Get Signals for Schema Validation",
                "GET",
                "api/signals?limit=5",
                200
            )
            
            if success and isinstance(response, dict) and 'signals' in response:
                test_signals = response['signals']
        
        if test_signals:
            required_fields = ['symbol', 'signal_type', 'confidence_score', 'timeframe', 'justification']
            schema_valid = True
            
            print(f"   📋 Validating schema on {len(test_signals)} signals...")
            
            for i, signal in enumerate(test_signals[:3], 1):  # Check first 3 signals
                print(f"   Signal {i} schema check:")
                signal_valid = True
                
                for field in required_fields:
                    if field in signal and signal[field] is not None:
                        print(f"      ✅ Field '{field}' present: {signal[field]}")
                    else:
                        print(f"      ❌ Field '{field}' missing or null")
                        signal_valid = False
                        schema_valid = False
                
                if signal_valid:
                    print(f"      ✅ Signal {i} schema valid")
                else:
                    print(f"      ❌ Signal {i} schema invalid")
            
            if schema_valid:
                print(f"   ✅ All signals have required schema fields")
            else:
                print(f"   ❌ Some signals missing required schema fields")
                all_passed = False
        else:
            print(f"   ❌ No signals available for schema validation")
            all_passed = False
        
        # 4) Final assessment and recommendations
        print(f"\n4️⃣ Final Assessment...")
        
        if sell_signals_found:
            print(f"   ✅ SUCCESS: Found {len(sell_signals_found)} SELL signals")
            print(f"   📊 SELL signal details:")
            
            for i, signal in enumerate(sell_signals_found[:3], 1):  # Show first 3 SELL signals
                print(f"      SELL Signal {i}:")
                print(f"         Symbol: {signal.get('symbol', 'N/A')}")
                print(f"         Confidence: {signal.get('confidence_score', 'N/A')}%")
                print(f"         Entry Price: {signal.get('entry_price', 'N/A')}")
                print(f"         Risk/Reward: {signal.get('risk_reward_ratio', 'N/A')}")
                print(f"         Timeframe: {signal.get('timeframe', 'N/A')}")
                print(f"         Regime: {signal.get('regime', 'N/A')}")
                print(f"         Justification: {signal.get('justification', 'N/A')[:100]}...")
        else:
            print(f"   ❌ FAILURE: No SELL signals found after all attempts")
            print(f"   💡 RECOMMENDATIONS:")
            print(f"      - Consider lowering confidence score thresholds in signal generator")
            print(f"      - Adjust technical analysis parameters to detect more bearish conditions")
            print(f"      - Review market regime detection logic")
            print(f"      - Ensure signal generation covers both bullish and bearish scenarios")
        
        if all_passed:
            self.tests_passed += 1
            print(f"\n🎉 SELL signals review request PASSED!")
        else:
            print(f"\n❌ SELL signals review request FAILED!")
        
        self.tests_run += 1
        return all_passed

def main():
    print("🚀 Starting AI Trading System Backend Tests - SELL Signals Review Request")
    print("=" * 80)
    
    tester = AITradingSystemTester()
    
    # Run focused tests based on review request
    tests = [
        tester.test_sell_signals_review_request,  # Primary focus - SELL signals testing
        tester.test_health_endpoint,              # Basic health check
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
    
    # Detailed notification system results
    print(f"\n🔔 NOTIFICATION SYSTEM RESULTS:")
    print(f"WebSocket Messages Received: {len(tester.ws_messages)}")
    print(f"Trading Alerts Received: {len(tester.notification_alerts_received)}")
    
    if tester.tests_passed == tester.tests_run:
        print("🎉 All backend tests passed!")
        return 0
    else:
        print("⚠️ Some backend tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())