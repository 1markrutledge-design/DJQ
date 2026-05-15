import json

with open("check_tennis_pnl.py", "r") as f:
    text = f.read()

text = text.replace('f.get("yes_price", 0)', 'f.get("price", f.get("yes_price", 0))')

with open("check_tennis_pnl.py", "w") as f:
    f.write(text)
