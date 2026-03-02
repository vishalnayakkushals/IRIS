# Portable CTO Bot (Plug-and-Play)

This folder is intentionally isolated from core app code.
You can copy this folder to another repository and run it there.

## Run

```bash
python tools/cto_bot/cto_bot.py --log-dir data/ops_logs
```

## Optional customization

```bash
python tools/cto_bot/cto_bot.py \
  --pytest-cmd "PYTHONPATH=src pytest -q" \
  --compile-cmd "python -m py_compile src/yourpkg/*.py"
```

## Logs
- `data/ops_logs/cto-bot.log`
- `data/ops_logs/cto-bot-<run_id>.json`

## GitHub Actions template
Use `tools/cto_bot/workflow-template.yml` in any repo if you want scheduled runs.
