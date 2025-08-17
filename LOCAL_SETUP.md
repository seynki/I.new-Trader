Local Setup (Docker Compose)

Requisitos:
- Docker + Docker Compose

Passos:
1) Crie um arquivo .env no backend com:
   MONGO_URL=mongodb://mongo:27017
   DB_NAME=typeia_trading
   IQ_EMAIL="seu_email@iqoption"
   IQ_PASSWORD="sua_senha"
   # Opcional para forçar fallback iqoptionapi:
   # IQ_USE_FX=0

2) Suba os serviços:
   docker compose up --build

3) Acesse:
   Frontend: http://localhost:3000
   Backend:  http://localhost:8001/api/health

4) Testes úteis:
   - POST http://localhost:8001/api/iq-option/live-login-check
   - POST http://localhost:8001/api/iq-option/test-connection (simulado)
   - POST http://localhost:8001/api/trading/quick-order (com body JSON)

Observações:
- O backend usa apenas as variáveis de ambiente e conecta no Mongo do compose (service mongo).
- Se quiser usar apenas iqoptionapi, defina IQ_USE_FX=0 no backend/.env e reinicie.
- Se sua conta tiver 2FA/captcha, desative temporariamente para o teste.
- Forex em fins de semana vira -OTC (ex: EURUSD -> EURUSD-OTC); cripto BTCUSDT -> BTCUSD.
