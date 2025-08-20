#!/usr/bin/env python3

import sys
import os
sys.path.append('/app')

from backend_test import AITradingSystemTester

def main():
    print("🎯 Testing IQ Option Diagnostics Endpoint - Review Request")
    print("=" * 60)
    
    # Get the backend URL from frontend .env
    backend_url = "https://naming-standard.preview.emergentagent.com"
    
    tester = AITradingSystemTester(base_url=backend_url)
    
    # Run the specific diagnostics test
    try:
        result = tester.test_iq_option_diagnostics_endpoint()
        
        print("\n" + "=" * 60)
        print(f"📊 IQ OPTION DIAGNOSTICS TEST RESULT")
        print(f"Test Result: {'✅ PASSED' if result else '❌ FAILED'}")
        print(f"Tests Run: {tester.tests_run}")
        print(f"Tests Passed: {tester.tests_passed}")
        
        if result:
            print("\n🎉 IQ Option Diagnostics Endpoint test completed successfully!")
            return 0
        else:
            print("\n❌ IQ Option Diagnostics Endpoint test failed!")
            return 1
            
    except Exception as e:
        print(f"❌ Test failed with exception: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())