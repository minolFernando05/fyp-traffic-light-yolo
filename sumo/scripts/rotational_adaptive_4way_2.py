import os, sys, csv, time
from pathlib import Path

if "SUMO_HOME" not in os.environ:
    sys.exit("ERROR: set SUMO_HOME, e.g. export SUMO_HOME=/usr/share/sumo")

sys.path.append(os.path.join(os.environ["SUMO_HOME"], "tools"))
import traci
from sumolib import checkBinary

BASE_DIR = Path(__file__).resolve().parents[1]
SUMO_CFG = str(BASE_DIR / "intersection.sumocfg")

TLS_ID = "J0"
SIM_SECONDS = 900
# SIM_SECONDS = 1200  # for testing GUI
OUT_CSV = BASE_DIR / "output" / "rotational_adaptive_4way_metrics.csv"

# ====== ADJUST HERE ======
USE_GUI = True
G_MIN = 10
G_MAX = 35
GAP_TIME = 3       # seconds of empty queue before ending green early
YELLOW_TIME = 3
STEP_DELAY = 0.2  # delay between simulation steps (for viewing in GUI)

# Choose ONE mapping method:
USE_LINEAR = True
Q_REF = 15          # only used in linear mapping
# =========================

LANES = {
    "N": ["north_in_0", "north_in_1"],
    "E": ["east_in_0", "east_in_1"],
    "S": ["south_in_0", "south_in_1"],
    "W": ["west_in_0", "west_in_1"],
}

PHASE = {
    "N_G": 0, "N_Y": 1,
    "E_G": 2, "E_Y": 3,
    "S_G": 4, "S_Y": 5,
    "W_G": 6, "W_Y": 7,
}

ORDER = ["N", "E", "S", "W"]  # fixed rotation

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def queue(dir_key):
    return sum(traci.lane.getLastStepHaltingNumber(l) for l in LANES[dir_key])

def run_green_gapout(dir_key, phase_green, phase_yellow, target_green, t, writer):
    """
    Run green up to target_green seconds, but end early if:
    - MIN_GREEN has passed AND
    - queue(dir_key) stays 0 for GAP_TIME consecutive seconds
    """

    # Start green
    traci.trafficlight.setPhase(TLS_ID, phase_green)
    traci.trafficlight.setPhaseDuration(TLS_ID, target_green)  # upper bound

    empty_streak = 0
    green_used = 0

    while green_used < target_green and t < SIM_SECONDS:
        traci.simulationStep()

        # served approach queue only
        q_served = queue(dir_key)

        # log (same as your previous writer row)
        qN, qE, qS, qW = queue("N"), queue("E"), queue("S"), queue("W")
        departed = traci.simulation.getDepartedNumber()
        arrived = traci.simulation.getArrivedNumber()

        writer.writerow([t, phase_green, dir_key, target_green, departed, arrived,
                        qN, qE, qS, qW, qN+qE+qS+qW])

        # Gap-out logic
        green_used += 1
        t += 1

        if green_used >= G_MIN:
            if q_served == 0:
                empty_streak += 1
                if empty_streak >= GAP_TIME:
                    break
            else:
                empty_streak = 0

    # Yellow phase
    traci.trafficlight.setPhase(TLS_ID, phase_yellow)
    traci.trafficlight.setPhaseDuration(TLS_ID, YELLOW_TIME)

    for _ in range(YELLOW_TIME):
        if t >= SIM_SECONDS:
            break
        traci.simulationStep()
        if USE_GUI:
            time.sleep(STEP_DELAY)
        t += 1

    return t


def green_time_from_queue(q):
    # Linear mapping: smooth increase
    if USE_LINEAR:
        g = G_MIN + (q / max(Q_REF, 1)) * (G_MAX - G_MIN)
        return int(round(clamp(g, G_MIN, G_MAX)))

    # Step mapping: stable, easy to explain (if you switch USE_LINEAR=False)
    if q <= 2: return 10
    if q <= 5: return 15
    if q <= 9: return 20
    if q <= 13: return 25
    return 35

def run_phase(phase_idx, duration, t, writer, served_dir, chosen_green):
    traci.trafficlight.setPhase(TLS_ID, phase_idx)
    traci.trafficlight.setPhaseDuration(TLS_ID, duration)

    for _ in range(duration):
        if t >= SIM_SECONDS:
            return t
        traci.simulationStep()
        if USE_GUI:
            time.sleep(STEP_DELAY)

        qN, qE, qS, qW = queue("N"), queue("E"), queue("S"), queue("W")
        departed = traci.simulation.getDepartedNumber()
        arrived = traci.simulation.getArrivedNumber()

        writer.writerow([t, phase_idx, served_dir, chosen_green, departed, arrived, qN, qE, qS, qW, qN+qE+qS+qW])
        t += 1

    return t

def main():
    sumoBinary = checkBinary("sumo-gui" if USE_GUI else "sumo")
    traci.start([sumoBinary, "-c", SUMO_CFG, "--start"])

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time","phase","served_dir","green_time","departed","arrived",
                        "qN","qE","qS","qW","total_queue"])

        t = 0
        idx = 0
        while t < SIM_SECONDS:
            d = ORDER[idx % len(ORDER)]
            idx += 1

            qd = queue(d)
            g = green_time_from_queue(qd)


            # gap-out green + yellow handled inside
            t = run_green_gapout(
                dir_key=d,
                phase_green=PHASE[f"{d}_G"],
                phase_yellow=PHASE[f"{d}_Y"],
                target_green=g,
                t=t,
                writer=writer
            )


    traci.close()
    print("Saved:", OUT_CSV)

if __name__ == "__main__":
    main()
