from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

BASE_DIR = Path(__file__).resolve().parents[1]
out_dir = BASE_DIR / "output"

fixed = pd.read_csv(out_dir / "fixed_4way_metrics.csv")
rot   = pd.read_csv(out_dir / "rotational_adaptive_4way_metrics.csv")
full  = pd.read_csv(out_dir / "full_adaptive_4way_metrics.csv")

# 1) Total Queue over time
plt.figure()
plt.plot(fixed["time"], fixed["total_queue"], label="Fixed")
plt.plot(rot["time"],   rot["total_queue"],   label="Rotational Adaptive")
plt.plot(full["time"],  full["total_queue"],  label="Full Adaptive")
plt.xlabel("Time (s)")
plt.ylabel("Total Queue (halting vehicles)")
plt.title("Total Queue vs Time (3-mode comparison)")
plt.legend()
plt.savefig(out_dir / "queue_3way.png", dpi=200)

# 2) Throughput (cumulative arrived)
fixed["arrived_cum"] = fixed["arrived"].cumsum()
rot["arrived_cum"]   = rot["arrived"].cumsum()
full["arrived_cum"]  = full["arrived"].cumsum()

plt.figure()
plt.plot(fixed["time"], fixed["arrived_cum"], label="Fixed")
plt.plot(rot["time"],   rot["arrived_cum"],   label="Rotational Adaptive")
plt.plot(full["time"],  full["arrived_cum"],  label="Full Adaptive")
plt.xlabel("Time (s)")
plt.ylabel("Cumulative Arrived Vehicles")
plt.title("Throughput vs Time (3-mode comparison)")
plt.legend()
plt.savefig(out_dir / "throughput_3way.png", dpi=200)

print("Saved plots:", out_dir / "queue_3way.png", "and", out_dir / "throughput_3way.png")
