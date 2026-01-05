# API Rules (FastAPI)

Architecture:
- routers/controllers: request/response only
- services: business logic (unit tested)
- repositories: DB access only

Testing:
- pytest
- unit tests mock repositories/clients
- API tests use TestClient + dependency overrides

Do:
- small functions, explicit typing where useful
- validate inputs + test failure paths
