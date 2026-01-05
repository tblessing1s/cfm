# Scripts Rules (Python / Excel logging)

Rules:
- scripts are idempotent where possible
- avoid hard-coded paths; use config/env
- separate IO (excel/files) from transformations (pure functions)

Testing:
- pytest
- unit tests focus on pure functions
- mock filesystem/excel IO
