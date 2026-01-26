import os
import sys
import csv
from pathlib import Path

if "SUMO_HOME" not in os.environ:
    sys.exit("ERROR: Please set SUMO_HOME (e.g., export SUMO_HOME=/usr/share/sumo)")

tools = os.path.join(os.environ["SUMO_HOME"], "tools")
sys.path.append(tools)

import traci
from sumolib import checkBinary

BASE_DIR = Path(__file__).resolve().parents[1]
SUMO_CFG = str(BASE_DIR / "intersection.sumocfg")

# === YOUR TLS ===
TLS_ID = "J0"

# === FIXED-TIME SETTINGS ===
GREEN_A = 30   # phase 0 green duration
YELLOW_A = 3   # phase 1
GREEN_B = 30   # phase 2 green duration
YELLOW_B = 3   # phase 3

SIM_SECONDS = 900
OUT_CSV = BASE_DIR / "output" / "fixed_metrics.csv"


def get_total_queue(lane_ids):
    # "Halting" ~= queued (stopped/very slow)
    return sum(traci.lane.getLastStepHaltingNumber(l) for l in lane_ids)


def main():
    sumoBinary = checkBinary("sumo")  # change to "sumo-gui" if you want to watch
    traci.start([sumoBinary, "-c", SUMO_CFG])

    # auto-detect lanes controlled by this traffic light (no manual lane ID work)
    controlled_lanes = sorted(set(traci.trafficlight.getControlledLanes(TLS_ID)))
    print("Controlled lanes:", controlled_lanes)

    # confirm phase states (for your report)
    logic = traci.trafficlight.getAllProgramLogics(TLS_ID)[0]
    print("TLS Program ID:", logic.programID)
    print("Number of phases:", len(logic.phases))
    for i, p in enumerate(logic.phases):
        print(f"Phase {i}: duration={p.duration}, state={p.state}")

    # Fixed-time schedule: (phaseIndex, durationSeconds)
    schedule = [
        (0, GREEN_A),
        (1, YELLOW_A),
        (2, GREEN_B),
        (3, YELLOW_B),
    ]

    # Start from phase 0
    current_sched_idx = 0
    phase, dur = schedule[current_sched_idx]
    traci.trafficlight.setPhase(TLS_ID, phase)
    traci.trafficlight.setPhaseDuration(TLS_ID, dur)

    # Logging
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "phase", "departed", "arrived", "total_queue"])

        remaining = dur

        for t in range(SIM_SECONDS):
            traci.simulationStep()

            departed = traci.simulation.getDepartedNumber()
            arrived = traci.simulation.getArrivedNumber()
            total_queue = get_total_queue(controlled_lanes)

            writer.writerow([t, phase, departed, arrived, total_queue])

            # countdown phase time
            remaining -= 1
            if remaining <= 0:
                # move to next phase in schedule
                current_sched_idx = (current_sched_idx + 1) % len(schedule)
                phase, dur = schedule[current_sched_idx]
                traci.trafficlight.setPhase(TLS_ID, phase)
                traci.trafficlight.setPhaseDuration(TLS_ID, dur)
                remaining = dur

    traci.close()
    print("Saved:", OUT_CSV)


if __name__ == "__main__":
    main()
