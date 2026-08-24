# active.py — placeholder sample-selection step reading the current model
import json

with open("model.json") as f:
    model = json.load(f)

print(f"Active learning step on model: {model}")
