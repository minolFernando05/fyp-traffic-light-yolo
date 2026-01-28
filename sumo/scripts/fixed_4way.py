import os, sys, csv
from pathlib import Path
import time

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
OUT_CSV = BASE_DIR / "output" / "fixed_4way_metrics.csv"

# ====== ADJUST HERE ======
USE_GUI = False          # True = watch in SUMO-GUI
GREEN_TIME = 30          # fixed green for each approach
YELLOW_TIME = 3
STEP_DELAY = 0.2  # delay between simulation steps (for viewing in GUI)
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

def queue(dir_key):
    return sum(traci.lane.getLastStepHaltingNumber(l) for l in LANES[dir_key])

def run_phase(phase_idx, duration, t, writer, served_dir):
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

        writer.writerow([t, phase_idx, served_dir, GREEN_TIME, departed, arrived, qN, qE, qS, qW, qN+qE+qS+qW])
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
        while t < SIM_SECONDS:
            t = run_phase(PHASE["N_G"], GREEN_TIME, t, writer, "N")
            t = run_phase(PHASE["N_Y"], YELLOW_TIME, t, writer, "N")
            t = run_phase(PHASE["E_G"], GREEN_TIME, t, writer, "E")
            t = run_phase(PHASE["E_Y"], YELLOW_TIME, t, writer, "E")
            t = run_phase(PHASE["S_G"], GREEN_TIME, t, writer, "S")
            t = run_phase(PHASE["S_Y"], YELLOW_TIME, t, writer, "S")
            t = run_phase(PHASE["W_G"], GREEN_TIME, t, writer, "W")
            t = run_phase(PHASE["W_Y"], YELLOW_TIME, t, writer, "W")

    traci.close()
    print("Saved:", OUT_CSV)

if __name__ == "__main__":
    main()
