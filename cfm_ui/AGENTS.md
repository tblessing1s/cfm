# Frontend Rules (Angular)

Architecture:
- smart/container components orchestrate
- dumb/presentational components render
- services for API calls/state
- avoid logic in templates

Testing:
- Jest/Karma (whichever repo uses) + Angular TestBed
- component tests for template behavior
- service tests mock HTTP with HttpTestingController

Do:
- keep feature modules/components isolated
- avoid cross-project coupling
