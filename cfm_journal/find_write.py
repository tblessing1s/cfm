from pathlib import Path
lines = Path('cfm_ledger_autotemplate.py').read_text(encoding='utf-8').splitlines()
for i,line in enumerate(lines, start=1):
    if 'def write_formulas' in line:
        print(i, line)
