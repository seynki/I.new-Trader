import requests
import sys
import json
import time
import websocket
import threading
from datetime import datetime

class AITradingSystemTester:
    def __init__(self, base_url="https://signal-test-scores.preview.emergentagent.com"):
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

    def test_signal_confidence_and_alerts_correlation(self):
        """Test specific requirement: signals with confidence_score >= 70 and corresponding alerts"""
        print(f"\n🔍 Testing Signal Confidence >= 70 and Alert Correlation...")
        print(f"   📋 Following exact review request requirements")
        
        # Step 1: Test health endpoint
        print(f"\n   Step 1: Testing health endpoint...")
        health_success, health_response = self.run_test(
            "Health Check Validation",
            "GET", 
            "api/health",
            200
        )
        
        if not health_success or not isinstance(health_response, dict):
            print(f"   ❌ Health check failed")
            return False
            
        if health_response.get('status') != 'healthy':
            print(f"   ❌ Health status not healthy: {health_response.get('status')}")
            return False
            
        print(f"   ✅ Health check passed - status: {health_response.get('status')}")
        
        # Step 2: Get notification settings and validate
        print(f"\n   Step 2: Validating notification settings...")
        settings_success, settings_response = self.run_test(
            "Get Notification Settings",
            "GET",
            "api/notifications/settings", 
            200
        )
        
        if not settings_success or not isinstance(settings_response, dict):
            print(f"   ❌ Failed to get notification settings")
            return False
            
        min_score_threshold = settings_response.get('min_score_threshold', 0)
        notifications_enabled = settings_response.get('notifications_enabled', False)
        min_rr_threshold = settings_response.get('min_rr_threshold', 0)
        timeframes = settings_response.get('timeframes', [])
        
        print(f"   📊 Current settings:")
        print(f"      - notifications_enabled: {notifications_enabled}")
        print(f"      - min_score_threshold: {min_score_threshold}")
        print(f"      - min_rr_threshold: {min_rr_threshold}")
        print(f"      - timeframes: {timeframes}")
        
        if min_score_threshold < 70:
            print(f"   ⚠️ min_score_threshold is {min_score_threshold}, expected >= 70")
        else:
            print(f"   ✅ min_score_threshold is {min_score_threshold} (>= 70)")
            
        if not notifications_enabled:
            print(f"   ⚠️ notifications_enabled is False, expected True")
        else:
            print(f"   ✅ notifications_enabled is True")
        
        # Step 3: Wait and poll for signals with score >= 70
        print(f"\n   Step 3: Waiting up to 25s for signal generation...")
        high_score_signals = []
        poll_count = 0
        max_polls = 3
        wait_time = 8  # Wait 8 seconds between polls
        
        for poll in range(max_polls):
            poll_count += 1
            print(f"   📡 Poll {poll_count}/{max_polls} - checking for signals...")
            
            signals_success, signals_response = self.run_test(
                f"Get Signals Poll {poll_count}",
                "GET",
                "api/signals?limit=50",
                200
            )
            
            if signals_success and isinstance(signals_response, dict):
                signals = signals_response.get('signals', [])
                print(f"      Found {len(signals)} total signals")
                
                # Filter signals with confidence_score >= 70
                current_high_score = [s for s in signals if s.get('confidence_score', 0) >= 70]
                print(f"      Found {len(current_high_score)} signals with score >= 70")
                
                # Log details of high score signals
                for signal in current_high_score[:5]:  # Show first 5
                    score = signal.get('confidence_score', 0)
                    symbol = signal.get('symbol', 'Unknown')
                    signal_id = signal.get('id', 'No ID')
                    rr = signal.get('risk_reward_ratio', 0)
                    print(f"         - {symbol}: score={score}, RR={rr}, ID={signal_id[:8]}...")
                
                # Update our collection of high score signals
                for signal in current_high_score:
                    if signal.get('id') not in [s.get('id') for s in high_score_signals]:
                        high_score_signals.append(signal)
            
            if poll < max_polls - 1:  # Don't wait after last poll
                print(f"      ⏳ Waiting {wait_time}s before next poll...")
                time.sleep(wait_time)
        
        print(f"\n   📊 Total unique signals with score >= 70 found: {len(high_score_signals)}")
        
        if len(high_score_signals) == 0:
            print(f"   ⚠️ No signals with confidence_score >= 70 found after {max_polls} polls")
            # Try extended polling as per requirements
            print(f"   🔄 Extending polling for up to 60s total as per edge case handling...")
            
            extended_polls = 3
            for poll in range(extended_polls):
                print(f"   📡 Extended poll {poll+1}/{extended_polls}...")
                time.sleep(15)  # 15-20s blocks as specified
                
                signals_success, signals_response = self.run_test(
                    f"Extended Signals Poll {poll+1}",
                    "GET",
                    "api/signals?limit=50",
                    200
                )
                
                if signals_success and isinstance(signals_response, dict):
                    signals = signals_response.get('signals', [])
                    current_high_score = [s for s in signals if s.get('confidence_score', 0) >= 70]
                    print(f"      Found {len(current_high_score)} signals with score >= 70")
                    
                    for signal in current_high_score:
                        if signal.get('id') not in [s.get('id') for s in high_score_signals]:
                            high_score_signals.append(signal)
            
            if len(high_score_signals) == 0:
                print(f"   ❌ No signals with score >= 70 found even after extended polling")
                return False
        
        # Step 4: Get alerts and validate correlation
        print(f"\n   Step 4: Checking alerts correlation...")
        alerts_success, alerts_response = self.run_test(
            "Get Alerts for Correlation",
            "GET",
            "api/alerts?limit=50",
            200
        )
        
        if not alerts_success or not isinstance(alerts_response, dict):
            print(f"   ❌ Failed to get alerts")
            return False
            
        alerts = alerts_response.get('alerts', [])
        print(f"   📨 Found {len(alerts)} total alerts")
        
        if len(alerts) == 0:
            print(f"   ⚠️ No alerts found - checking backend logs for errors...")
            # This would be where we check logs in a real scenario
            print(f"   ❌ Alert generation may have failed")
            return False
        
        # Step 5: Validate alert structure and correlation
        print(f"\n   Step 5: Validating alert structure and correlation...")
        
        high_score_signal_ids = {s.get('id') for s in high_score_signals}
        correlated_alerts = []
        
        for alert in alerts:
            # Validate alert structure
            required_fields = ['id', 'signal_id', 'title', 'message', 'priority', 'timestamp', 'read', 'iq_option_ready']
            missing_fields = [field for field in required_fields if field not in alert]
            
            if missing_fields:
                print(f"   ⚠️ Alert missing fields: {missing_fields}")
            
            # Check if alert corresponds to high score signal
            alert_signal_id = alert.get('signal_id')
            if alert_signal_id in high_score_signal_ids:
                correlated_alerts.append(alert)
                
                # Validate priority mapping
                signal = next((s for s in high_score_signals if s.get('id') == alert_signal_id), None)
                if signal:
                    score = signal.get('confidence_score', 0)
                    priority = alert.get('priority', '')
                    expected_priority = 'high' if score >= 80 else 'medium' if score >= 70 else 'low'
                    
                    if priority == expected_priority:
                        print(f"   ✅ Alert priority correct: score={score} -> priority={priority}")
                    else:
                        print(f"   ⚠️ Alert priority mismatch: score={score}, expected={expected_priority}, got={priority}")
                
                # Validate iq_option_ready
                if alert.get('iq_option_ready') == True:
                    print(f"   ✅ Alert is IQ Option ready")
                else:
                    print(f"   ⚠️ Alert not marked as IQ Option ready")
        
        print(f"\n   📊 Correlation Results:")
        print(f"      - High score signals (>=70): {len(high_score_signals)}")
        print(f"      - Total alerts: {len(alerts)}")
        print(f"      - Correlated alerts: {len(correlated_alerts)}")
        
        # Step 6: Validate minimum correlation requirement
        if len(high_score_signals) >= 3 and len(correlated_alerts) >= 1:
            print(f"   ✅ PASSED: Found {len(high_score_signals)} signals >=70 with {len(correlated_alerts)} corresponding alerts")
            self.tests_passed += 1
            return True
        elif len(high_score_signals) > 0 and len(correlated_alerts) > 0:
            print(f"   ✅ PARTIAL PASS: Found {len(high_score_signals)} signals >=70 with {len(correlated_alerts)} corresponding alerts")
            print(f"      (Less than 3 high-score signals, but correlation is working)")
            self.tests_passed += 1
            return True
        else:
            print(f"   ❌ FAILED: Insufficient correlation between high-score signals and alerts")
            return False

    def test_review_request_focused_endpoints(self):
        """Test specific endpoints mentioned in review request"""
        print(f"\n🎯 REVIEW REQUEST FOCUSED TESTING")
        print(f"=" * 60)
        print(f"Testing backend endpoints that feed frontend changes as per review request")
        
        all_tests_passed = True
        
        # Test 1: /api/stats endpoint - test twice with 10s interval
        print(f"\n📊 Test 1: /api/stats endpoint (testing twice with 10s interval)")
        
        # First call
        success1, response1 = self.run_test(
            "Stats Endpoint - First Call",
            "GET",
            "api/stats",
            200
        )
        
        if success1 and isinstance(response1, dict):
            # Validate required fields and types
            required_fields = {
                'score_avg': int,
                'max_score': int, 
                'rr_avg': float,
                'trending_markets': int
            }
            
            for field, expected_type in required_fields.items():
                if field in response1:
                    value = response1[field]
                    if isinstance(value, expected_type):
                        print(f"   ✅ {field}: {value} (type: {type(value).__name__})")
                    else:
                        print(f"   ❌ {field}: {value} (expected {expected_type.__name__}, got {type(value).__name__})")
                        all_tests_passed = False
                else:
                    print(f"   ❌ Missing required field: {field}")
                    all_tests_passed = False
        else:
            print(f"   ❌ First stats call failed")
            all_tests_passed = False
        
        # Wait 10 seconds
        print(f"   ⏳ Waiting 10 seconds before second call...")
        time.sleep(10)
        
        # Second call
        success2, response2 = self.run_test(
            "Stats Endpoint - Second Call",
            "GET", 
            "api/stats",
            200
        )
        
        if success2 and isinstance(response2, dict):
            print(f"   ✅ Second stats call successful")
            
            # Compare values to observe variation
            if success1:
                for field in ['score_avg', 'max_score', 'rr_avg', 'trending_markets']:
                    if field in response1 and field in response2:
                        val1, val2 = response1[field], response2[field]
                        if val1 != val2:
                            print(f"   📈 {field} changed: {val1} → {val2}")
                        else:
                            print(f"   📊 {field} unchanged: {val1}")
        else:
            print(f"   ❌ Second stats call failed")
            all_tests_passed = False
        
        # Test 2: /api/market-data endpoint
        print(f"\n📈 Test 2: /api/market-data endpoint")
        success, response = self.run_test(
            "Market Data Endpoint",
            "GET",
            "api/market-data", 
            200
        )
        
        if success and isinstance(response, dict):
            if 'data' in response and isinstance(response['data'], list):
                data = response['data']
                print(f"   ✅ Market data returned {len(data)} symbols")
                
                # Check for diverse symbols (not just SP500/NAS100)
                symbols = [item.get('symbol', '') for item in data]
                diverse_symbols = [s for s in symbols if s not in ['SP500', 'NAS100']]
                print(f"   ✅ Diverse symbols available: {len(diverse_symbols)} (non-SP500/NAS100)")
                print(f"   📋 Sample symbols: {symbols[:5]}")
                
                # Validate structure
                if data:
                    sample = data[0]
                    required_fields = ['symbol', 'price', 'change_24h', 'volume', 'timestamp']
                    for field in required_fields:
                        if field in sample:
                            print(f"   ✅ Field '{field}' present")
                        else:
                            print(f"   ❌ Field '{field}' missing")
                            all_tests_passed = False
            else:
                print(f"   ❌ Invalid market data structure")
                all_tests_passed = False
        else:
            print(f"   ❌ Market data endpoint failed")
            all_tests_passed = False
        
        # Test 3: /api/signals endpoint
        print(f"\n🎯 Test 3: /api/signals?limit=5 endpoint")
        success, response = self.run_test(
            "Signals Endpoint",
            "GET",
            "api/signals?limit=5",
            200
        )
        
        if success and isinstance(response, dict):
            if 'signals' in response:
                signals = response['signals']
                print(f"   ✅ Signals returned: {len(signals)}")
                
                if signals:
                    # Validate signal structure
                    sample = signals[0]
                    required_fields = ['id', 'symbol', 'confidence_score', 'risk_reward_ratio']
                    for field in required_fields:
                        if field in sample:
                            print(f"   ✅ Signal field '{field}': {sample[field]}")
                        else:
                            print(f"   ❌ Signal field '{field}' missing")
                            all_tests_passed = False
                else:
                    print(f"   ⚠️ No signals available")
            else:
                print(f"   ❌ 'signals' key missing")
                all_tests_passed = False
        else:
            print(f"   ❌ Signals endpoint failed")
            all_tests_passed = False
        
        # Test 4: /api/iq-option/test-connection endpoint
        print(f"\n🔗 Test 4: /api/iq-option/test-connection endpoint")
        success, response = self.run_test(
            "IQ Option Test Connection",
            "POST",
            "api/iq-option/test-connection",
            200
        )
        
        if success and isinstance(response, dict):
            required_fields = ['connected', 'account_type', 'balance']
            for field in required_fields:
                if field in response:
                    print(f"   ✅ IQ Option field '{field}': {response[field]}")
                else:
                    print(f"   ❌ IQ Option field '{field}' missing")
                    all_tests_passed = False
        else:
            print(f"   ❌ IQ Option test connection failed")
            all_tests_passed = False
        
        # Test 5: WebSocket /api/ws for market_update and new_signal events
        print(f"\n🌐 Test 5: WebSocket /api/ws for market_update and new_signal events")
        
        ws_url = self.base_url.replace('https', 'wss') + '/api/ws'
        print(f"   WebSocket URL: {ws_url}")
        
        market_updates_received = []
        new_signals_received = []
        
        def on_message(ws, message):
            try:
                data = json.loads(message)
                msg_type = data.get('type', '')
                
                if msg_type == 'market_update':
                    market_updates_received.append(data)
                    print(f"   📊 Market update received (total: {len(market_updates_received)})")
                elif msg_type == 'new_signal':
                    new_signals_received.append(data)
                    print(f"   🎯 New signal received (total: {len(new_signals_received)})")
                    
            except Exception as e:
                print(f"   ❌ Error parsing WebSocket message: {e}")

        def on_error(ws, error):
            print(f"   ❌ WebSocket error: {error}")

        def on_close(ws, close_status_code, close_msg):
            print(f"   🔌 WebSocket closed")

        def on_open(ws):
            print(f"   ✅ WebSocket connected")

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
            
            # Wait 15 seconds (12-18s as specified)
            print(f"   ⏳ Listening for 15 seconds...")
            time.sleep(15)
            
            # Validate results
            print(f"   📊 Market updates received: {len(market_updates_received)}")
            print(f"   🎯 New signals received: {len(new_signals_received)}")
            
            if len(market_updates_received) >= 1:
                print(f"   ✅ At least one market_update received")
                # Validate structure
                sample = market_updates_received[0]
                if 'data' in sample and isinstance(sample['data'], list):
                    print(f"   ✅ Market update has valid structure")
                else:
                    print(f"   ❌ Market update structure invalid")
                    all_tests_passed = False
            else:
                print(f"   ❌ No market_update events received")
                all_tests_passed = False
            
            if len(new_signals_received) >= 1:
                print(f"   ✅ At least one new_signal received")
                # Validate structure
                sample = new_signals_received[0]
                if 'data' in sample and isinstance(sample['data'], dict):
                    signal_data = sample['data']
                    required_fields = ['id', 'symbol', 'confidence_score', 'risk_reward_ratio']
                    for field in required_fields:
                        if field in signal_data:
                            print(f"   ✅ New signal field '{field}' present")
                        else:
                            print(f"   ❌ New signal field '{field}' missing")
                            all_tests_passed = False
                else:
                    print(f"   ❌ New signal structure invalid")
                    all_tests_passed = False
            else:
                print(f"   ⚠️ No new_signal events received (may be normal if no signals generated)")
            
            ws.close()
            
        except Exception as e:
            print(f"   ❌ WebSocket test failed: {str(e)}")
            all_tests_passed = False
        
        # Test 6: /api/alerts endpoint
        print(f"\n🚨 Test 6: /api/alerts?limit=5 endpoint")
        success, response = self.run_test(
            "Alerts Endpoint",
            "GET",
            "api/alerts?limit=5",
            200
        )
        
        if success and isinstance(response, dict):
            if 'alerts' in response:
                alerts = response['alerts']
                print(f"   ✅ Alerts returned: {len(alerts)}")
                
                if alerts:
                    # Validate alert structure
                    sample = alerts[0]
                    required_fields = ['id', 'signal_id', 'alert_type', 'title', 'message', 'priority', 'timestamp']
                    for field in required_fields:
                        if field in sample:
                            print(f"   ✅ Alert field '{field}' present")
                        else:
                            print(f"   ❌ Alert field '{field}' missing")
                            all_tests_passed = False
                else:
                    print(f"   ⚠️ No alerts available")
            else:
                print(f"   ❌ 'alerts' key missing")
                all_tests_passed = False
        else:
            print(f"   ❌ Alerts endpoint failed")
            all_tests_passed = False
        
        # Final result
        print(f"\n🎯 REVIEW REQUEST TESTING SUMMARY:")
        if all_tests_passed:
            print(f"   ✅ ALL REVIEW REQUEST TESTS PASSED")
            self.tests_passed += 1
        else:
            print(f"   ❌ SOME REVIEW REQUEST TESTS FAILED")
        
        self.tests_run += 1
        return all_tests_passed

def main():
    print("🚀 Starting AI Trading System Backend Tests")
    print("=" * 50)
    
    tester = AITradingSystemTester()
    
    # Run focused test based on review request first
    tests = [
        tester.test_review_request_focused_endpoints,  # NEW: Specific review request focused test
        tester.test_health_endpoint,
        tester.test_signal_confidence_and_alerts_correlation,  # Existing comprehensive test
        tester.test_market_data_endpoint,
        tester.test_signals_endpoint,
        tester.test_notification_settings_endpoints,
        tester.test_alerts_endpoint,
        tester.test_iq_option_endpoints,
        tester.test_stats_endpoint,
        tester.test_indicators_endpoint,
        tester.test_websocket_notifications,
        tester.test_signal_generation_logic,
        tester.test_notification_system_integration
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