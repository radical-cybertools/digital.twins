# train.py — "fit" a model to the streamed window passed as argv floats
import json
import sys

values = [float(v) for v in sys.argv[1:]]
mean = sum(values) / len(values)
var = sum((v - mean) ** 2 for v in values) / len(values)

with open("model.json", "w") as f:
    json.dump({"mean": mean, "var": var, "n": len(values)}, f)

print(f"Trained on window of {len(values)}: mean={mean:.4f} var={var:.4f}")
