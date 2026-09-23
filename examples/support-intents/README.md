# Support intents

```bash
uv run openclass init examples/support-intents/classifier.json
uv run openclass classify "I was charged twice"
uv run openclass classify "Cancel my plan"
uv run openclass unknowns
```

Run the server first. The first result is billing; the second remains UNKNOWN.
This synthetic example exercises the mock provider, not the future discovery loop.
