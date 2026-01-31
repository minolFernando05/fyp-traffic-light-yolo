from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

# ===================== ADJUST HERE =====================
SMOOTH_WINDOW_SEC = 15   # rolling average window (seconds). Try 10, 15, 30
DPI = 250
# =======================================================

BASE_DIR = Path(__file__).resolve().parents[1]
out_dir = BASE_DIR / "output"

fixed = pd.read_csv(out_dir / "fixed_4way_metrics.csv")
rot   = pd.read_csv(out_dir / "rotational_adaptive_4way_metrics.csv")
full  = pd.read_csv(out_dir / "full_adaptive_4way_metrics.csv")

def add_common(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Ensure sorted time
    df = df.sort_values("time")
    # Smooth queue
    df["queue_smooth"] = df["total_queue"].rolling(SMOOTH_WINDOW_SEC, min_periods=1).mean()
    # Smooth arrived rate (optional)
    df["arrived_cum"] = df["arrived"].cumsum()
    return df

fixed = add_common(fixed)
rot   = add_common(rot)
full  = add_common(full)

def summary(df: pd.DataFrame):
    return {
        "avgQ": df["total_queue"].mean(),
        "maxQ": df["total_queue"].max(),
        "finalArrived": int(df["arrived_cum"].iloc[-1]),
    }

s_fixed = summary(fixed)
s_rot   = summary(rot)
s_full  = summary(full)

# ------------------ Plot 1: Queue (raw + smooth) ------------------
plt.figure(figsize=(11, 6))

# Smooth lines (main)
plt.plot(fixed["time"], fixed["queue_smooth"], label="Fixed (smoothed)")
plt.plot(rot["time"],   rot["queue_smooth"],   label="Rotational Adaptive (smoothed)")
plt.plot(full["time"],  full["queue_smooth"],  label="Full Adaptive (smoothed)")

# Optional: faint raw lines (helps show variability without clutter)
plt.plot(fixed["time"], fixed["total_queue"], alpha=0.15, label="_nolegend_")
plt.plot(rot["time"],   rot["total_queue"],   alpha=0.15, label="_nolegend_")
plt.plot(full["time"],  full["total_queue"],  alpha=0.15, label="_nolegend_")

plt.xlabel("Time (s)")
plt.ylabel("Total Queue (halting vehicles)")
plt.title(f"Total Queue vs Time (3-mode, {SMOOTH_WINDOW_SEC}s rolling avg)")
plt.legend(loc="upper left")
plt.grid(True, alpha=0.3)

# Summary box
text = (
    "Summary (900s)\n"
    f"Fixed:     avgQ={s_fixed['avgQ']:.2f}, maxQ={s_fixed['maxQ']}, arrived={s_fixed['finalArrived']}\n"
    f"Rot-Adap:  avgQ={s_rot['avgQ']:.2f}, maxQ={s_rot['maxQ']}, arrived={s_rot['finalArrived']}\n"
    f"Full-Adap: avgQ={s_full['avgQ']:.2f}, maxQ={s_full['maxQ']}, arrived={s_full['finalArrived']}\n"
)
plt.gca().text(
    0.02, 0.02, text,
    transform=plt.gca().transAxes,
    fontsize=10,
    verticalalignment="bottom",
    bbox=dict(boxstyle="round", alpha=0.15)
)

plt.tight_layout()
plt.savefig(out_dir / "queue_3way_clear.png", dpi=DPI)

# ------------------ Plot 2: Throughput (cumulative arrived) ------------------
plt.figure(figsize=(11, 6))
plt.plot(fixed["time"], fixed["arrived_cum"], label="Fixed")
plt.plot(rot["time"],   rot["arrived_cum"],   label="Rotational Adaptive")
plt.plot(full["time"],  full["arrived_cum"],  label="Full Adaptive")

plt.xlabel("Time (s)")
plt.ylabel("Cumulative Arrived Vehicles")
plt.title("Throughput vs Time (3-mode comparison)")
plt.legend(loc="upper left")
plt.grid(True, alpha=0.3)

# Add final numbers on the right side
plt.gca().text(0.70, 0.15,
            f"Final arrived:\n"
            f"Fixed: {s_fixed['finalArrived']}\n"
            f"Rot-Adap: {s_rot['finalArrived']}\n"
            f"Full-Adap: {s_full['finalArrived']}",
            transform=plt.gca().transAxes,
            fontsize=11,
            bbox=dict(boxstyle="round", alpha=0.15))

plt.tight_layout()
plt.savefig(out_dir / "throughput_3way_clear.png", dpi=DPI)

print("Saved:")
print(" -", out_dir / "queue_3way_clear.png")
print(" -", out_dir / "throughput_3way_clear.png")
