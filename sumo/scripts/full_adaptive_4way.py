import os, sys, csv,time
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
OUT_CSV = BASE_DIR / "output" / "full_adaptive_4way_metrics.csv"

# ====== ADJUST HERE ======
USE_GUI = False
G_MIN = 10
G_MAX = 30
YELLOW_TIME = 3
MAX_WAIT = 90       # fairness: max seconds a direction can wait
STEP_DELAY = 0.2  # delay between simulation steps (for viewing in GUI)

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

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def queue(dir_key):
    return sum(traci.lane.getLastStepHaltingNumber(l) for l in LANES[dir_key])

def green_time_from_queue(q):
    if USE_LINEAR:
        g = G_MIN + (q / max(Q_REF, 1)) * (G_MAX - G_MIN)
        return int(round(clamp(g, G_MIN, G_MAX)))

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

    waited = {"N": 0, "E": 0, "S": 0, "W": 0}

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time","phase","served_dir","green_time","departed","arrived",
                        "qN","qE","qS","qW","total_queue"])

        t = 0
        while t < SIM_SECONDS:
            q = {d: queue(d) for d in waited}

            # fairness override
            starving = [d for d in waited if waited[d] >= MAX_WAIT]
            if starving:
                chosen = max(starving, key=lambda d: q[d])
            else:
                chosen = max(q, key=q.get)

            g = green_time_from_queue(q[chosen])

            # run green + yellow
            t = run_phase(PHASE[f"{chosen}_G"], g, t, writer, chosen, g)
            t = run_phase(PHASE[f"{chosen}_Y"], YELLOW_TIME, t, writer, chosen, g)

            # update waited times
            for d in waited:
                waited[d] = 0 if d == chosen else waited[d] + (g + YELLOW_TIME)

    traci.close()
    print("Saved:", OUT_CSV)

if __name__ == "__main__":
    main()
