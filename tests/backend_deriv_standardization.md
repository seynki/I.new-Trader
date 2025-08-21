Plan for backend validation after Deriv standardization:
- GET /api/market-data: symbols should be frx*/cry*/R_* or BOOM*/CRASH*
- GET /api/symbols: same rule
- GET /api/signals?limit=5: symbols standardized
- WS /api/ws: market_update symbols standardized
- POST /api/trading/quick-order tests:
  a) asset=BOOM_500, direction=put -> expect 400 with detail "Este mercado aceita apenas compra (CALL)."
  b) asset=EURUSD, direction=call -> expect 503 "Deriv não configurado"
- GET /api/alerts?limit=5: alert.symbol should be standardized
