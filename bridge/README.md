IQ Bridge - Execução via navegador (Playwright)

Rotas:
- GET /bridge/health → status
- POST /bridge/login {email, password, otp_code?} → autentica no site e persiste sessão
- POST /bridge/quick-order {asset, direction, amount, expiration, account_type, option_type} → tenta executar Buy/Sell

Build/Run (docker compose, na raiz do projeto):
- docker compose build bridge
- docker compose up -d bridge
- Teste no navegador: http://localhost:8100/bridge/health

Notas:
- A sessão fica salva no volume bridge_session; só logar uma vez.
- Se a IQ solicitar 2FA/captcha, informe otp_code; se houver captcha visual, precisará interação manual (podemos habilitar modo não-headless sob demanda).
- O backend usa BRIDGE_URL=http://bridge:8100 para chamar o serviço dentro da rede docker.
