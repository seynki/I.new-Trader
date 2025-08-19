Local Setup (Docker Compose)

Requisitos:
- Docker + Docker Compose

Passos:
1) Crie/edite backend/.env:
   MONGO_URL=mongodb://mongo:27017
   DB_NAME=typeia_trading
   IQ_EMAIL="seu_email@iqoption"
   IQ_PASSWORD="sua_senha"
   IQ_USE_FX=0
   BRIDGE_URL=http://bridge:8100

2) Suba os serviços:
   docker compose down -v
   docker compose up --build

3) Bridge (testes):
   - GET http://localhost:8100/bridge/health
   - GET http://localhost:8100/bridge/status
   - GET http://localhost:8100/bridge/screenshot
   - POST http://localhost:8100/bridge/login {email,password,otp_code?}
   - POST http://localhost:8100/bridge/quick-order {asset,direction,amount,expiration,account_type,option_type}

4) UI:
   http://localhost:3000 (WS deve conectar a ws://localhost:8001/api/ws)

Notas:
- /bridge/login aceita apenas POST JSON.
- Se a ordem via API falhar, o backend cai no Bridge automaticamente.
- Se a IQ exigir 2FA, forneça otp_code no /bridge/login.