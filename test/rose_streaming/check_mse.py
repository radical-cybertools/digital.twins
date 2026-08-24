# check_mse.py — report the model's variance as a pseudo-MSE metric
import json

with open("model.json") as f:
    model = json.load(f)

print(model["var"])
