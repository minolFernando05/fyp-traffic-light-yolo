from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

BASE_DIR = Path(__file__).resolve().parents[1]
fixed_path = BASE_DIR / "output" / "fixed_4way_metrics.csv"
adapt_path = BASE_DIR / "output" / "adaptive_4way_metrics.csv"
out_dir = BASE_DIR / "output"

fixed = pd.read_csv(fixed_path)
adapt = pd.read_csv(adapt_path)

# 1) Total Queue over time
plt.figure()
plt.plot(fixed["time"], fixed["total_queue"], label="Fixed (4-way)")
plt.plot(adapt["time"], adapt["total_queue"], label="Adaptive (4-way)")
plt.xlabel("Time (s)")
plt.ylabel("Total Queue (halting vehicles)")
plt.title("Total Queue vs Time (4-way Sri Lanka style)")
plt.legend()
plt.savefig(out_dir / "queue_fixed_vs_adaptive_4way.png", dpi=200)

# 2) Throughput (cumulative arrived)
fixed["arrived_cum"] = fixed["arrived"].cumsum()
adapt["arrived_cum"] = adapt["arrived"].cumsum()

plt.figure()
plt.plot(fixed["time"], fixed["arrived_cum"], label="Fixed (4-way)")
plt.plot(adapt["time"], adapt["arrived_cum"], label="Adaptive (4-way)")
plt.xlabel("Time (s)")
plt.ylabel("Cumulative Arrived Vehicles")
plt.title("Throughput vs Time (4-way Sri Lanka style)")
plt.legend()
plt.savefig(out_dir / "throughput_fixed_vs_adaptive_4way.png", dpi=200)

print("Saved plots to:", out_dir)
