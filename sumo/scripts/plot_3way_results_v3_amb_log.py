from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

# ===================== ADJUST HERE =====================
SMOOTH_WINDOW_SEC = 15   # rolling average window (seconds). Try 10, 15, 30
DPI = 250
# =======================================================

BASE_DIR = Path(__file__).resolve().parents[1]
out_dir = BASE_DIR / "output"

# ---- Update filenames here if you changed them ----
fixed_path = out_dir / "fixed_4way_metrics.csv"
rot_path   = out_dir / "rotational_adaptive_4way_metrics.csv"
full_path  = out_dir / "full_adaptive_4way_metrics.csv"

fixed = pd.read_csv(fixed_path)
rot   = pd.read_csv(rot_path)
full  = pd.read_csv(full_path)

def add_common(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = df.sort_values("time")
    df["queue_smooth"] = df["total_queue"].rolling(SMOOTH_WINDOW_SEC, min_periods=1).mean()
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

plt.plot(fixed["time"], fixed["queue_smooth"], label="Fixed (smoothed)")
plt.plot(rot["time"],   rot["queue_smooth"],   label="Rotational Adaptive (smoothed)")
plt.plot(full["time"],  full["queue_smooth"],  label="Full Adaptive (smoothed)")

plt.plot(fixed["time"], fixed["total_queue"], alpha=0.15, label="_nolegend_")
plt.plot(rot["time"],   rot["total_queue"],   alpha=0.15, label="_nolegend_")
plt.plot(full["time"],  full["total_queue"],  alpha=0.15, label="_nolegend_")

plt.xlabel("Time (s)")
plt.ylabel("Total Queue (halting vehicles)")
plt.title(f"Total Queue vs Time (3-mode, {SMOOTH_WINDOW_SEC}s rolling avg)")
plt.legend(loc="upper left")
plt.grid(True, alpha=0.3)

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

# ==========================================================
# Plot 3: Ambulance waiting time comparison (NEW)
# ==========================================================

def extract_ambulance_wait_events(df: pd.DataFrame):
    """
    Returns a DataFrame of emergency events with:
      - detect_t, green_t, wait_time, emg_dir, emg_id (if available)
    Works for both:
      A) Scripts that log emg_wait_time explicitly
      B) Older scripts that only log served_dir like EMG_DETECT_* and EMG_*
    """
    df = df.sort_values("time").copy()

    # ---- Case A: explicit column exists ----
    wait_cols = [c for c in df.columns if c in ("emg_wait_time", "emg_wait", "wait_time")]
    if wait_cols:
        col = wait_cols[0]
        # coerce to numeric (handles blanks)
        w = pd.to_numeric(df[col], errors="coerce")
        # rows where wait time exists
        events = df.loc[w.notna(), ["time"]].copy()
        events["wait_time"] = w.loc[w.notna()].astype(float).values

        # Optional extra columns
        for extra in ["emg_detect_t", "emg_green_t", "emg_dir", "emg_id"]:
            if extra in df.columns:
                events[extra] = df.loc[w.notna(), extra].values
        # Fill detect/green if not present
        if "emg_detect_t" not in events.columns:
            events["emg_detect_t"] = events["time"]
        if "emg_green_t" not in events.columns:
            events["emg_green_t"] = events["time"]
        if "emg_dir" not in events.columns:
            events["emg_dir"] = ""
        if "emg_id" not in events.columns:
            events["emg_id"] = ""
        return events.reset_index(drop=True)

    # ---- Case B: infer from served_dir labels ----
    if "served_dir" not in df.columns:
        return pd.DataFrame(columns=["emg_detect_t", "emg_green_t", "wait_time", "emg_dir", "emg_id"])

    detect_rows = df[df["served_dir"].astype(str).str.startswith("EMG_DETECT_")].copy()
    green_rows  = df[df["served_dir"].astype(str).str.startswith("EMG_")].copy()

    # remove EMG_DETECT from green_rows filtering
    green_rows = green_rows[~green_rows["served_dir"].astype(str).str.startswith("EMG_DETECT_")]

    if detect_rows.empty or green_rows.empty:
        return pd.DataFrame(columns=["emg_detect_t", "emg_green_t", "wait_time", "emg_dir", "emg_id"])

    # For each detect, find first green after it, same direction
    events = []
    for _, r in detect_rows.iterrows():
        detect_t = int(r["time"])
        d = str(r["served_dir"]).replace("EMG_DETECT_", "").strip()

        g_after = green_rows[(green_rows["time"] >= detect_t) &
                             (green_rows["served_dir"].astype(str).str.startswith(f"EMG_{d}"))]
        if g_after.empty:
            continue
        green_t = int(g_after.iloc[0]["time"])
        events.append({
            "emg_detect_t": detect_t,
            "emg_green_t": green_t,
            "wait_time": float(green_t - detect_t),
            "emg_dir": d,
            "emg_id": ""
        })

    return pd.DataFrame(events)

events_fixed = extract_ambulance_wait_events(fixed)
events_rot   = extract_ambulance_wait_events(rot)
events_full  = extract_ambulance_wait_events(full)

def event_stats(events: pd.DataFrame):
    if events.empty:
        return {"n": 0, "avg": None, "min": None, "max": None}
    return {
        "n": int(len(events)),
        "avg": float(events["wait_time"].mean()),
        "min": float(events["wait_time"].min()),
        "max": float(events["wait_time"].max()),
    }

st_fixed = event_stats(events_fixed)
st_rot   = event_stats(events_rot)
st_full  = event_stats(events_full)

# If none of the datasets has any ambulance events, skip plotting
if st_fixed["n"] == 0 and st_rot["n"] == 0 and st_full["n"] == 0:
    print("No ambulance events found in CSVs -> skipping ambulance wait time plot.")
else:
    plt.figure(figsize=(11, 6))

    # Plot as scatter events (x = detect time)
    if st_fixed["n"] > 0:
        plt.scatter(events_fixed["emg_detect_t"], events_fixed["wait_time"], label=f"Fixed (n={st_fixed['n']})")
    if st_rot["n"] > 0:
        plt.scatter(events_rot["emg_detect_t"], events_rot["wait_time"], label=f"Rot-Adap (n={st_rot['n']})")
    if st_full["n"] > 0:
        plt.scatter(events_full["emg_detect_t"], events_full["wait_time"], label=f"Full-Adap (n={st_full['n']})")

    plt.xlabel("Ambulance detect time (s)")
    plt.ylabel("Ambulance waiting time (s)")
    plt.title("Ambulance waiting time comparison (detect → green)")
    plt.grid(True, alpha=0.3)
    plt.legend(loc="upper left")

    # Stats box
    def fmt_stats(name, st):
        if st["n"] == 0:
            return f"{name}: n=0"
        return f"{name}: n={st['n']}, avg={st['avg']:.2f}s, min={st['min']:.0f}s, max={st['max']:.0f}s"

    stats_text = (
        "Ambulance wait stats\n"
        + fmt_stats("Fixed", st_fixed) + "\n"
        + fmt_stats("Rot-Adap", st_rot) + "\n"
        + fmt_stats("Full-Adap", st_full)
    )
    plt.gca().text(
        0.02, 0.02, stats_text,
        transform=plt.gca().transAxes,
        fontsize=10,
        verticalalignment="bottom",
        bbox=dict(boxstyle="round", alpha=0.15)
    )

    plt.tight_layout()
    plt.savefig(out_dir / "ambulance_wait_time.png", dpi=DPI)

print("Saved:")
print(" -", out_dir / "queue_3way_clear.png")
print(" -", out_dir / "throughput_3way_clear.png")
if (out_dir / "ambulance_wait_time.png").exists():
    print(" -", out_dir / "ambulance_wait_time.png")
