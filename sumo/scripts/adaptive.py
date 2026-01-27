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

TLS_ID = "J0"

# === Adaptive bounds (your requirement) ===
MIN_GREEN = 10
MAX_GREEN = 35
YELLOW = 3

SIM_SECONDS = 900
OUT_CSV = BASE_DIR / "output" / "adaptive_metrics.csv"


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def get_total_queue(lane_ids):
    return sum(traci.lane.getLastStepHaltingNumber(l) for l in lane_ids)


def main():
    sumoBinary = checkBinary("sumo")  # use "sumo-gui" if you want to watch
    traci.start([sumoBinary, "-c", SUMO_CFG])

    # Lanes controlled by TLS (auto-detected)
    controlled_lanes = sorted(set(traci.trafficlight.getControlledLanes(TLS_ID)))
    print("Controlled lanes:", controlled_lanes)

    # Phase info (for debugging/report)
    logic = traci.trafficlight.getAllProgramLogics(TLS_ID)[0]
    print("Number of phases:", len(logic.phases))
    for i, p in enumerate(logic.phases):
        print(f"Phase {i}: duration={p.duration}, state={p.state}")

    # Your observed phase mapping:
    # Phase 0 = one direction GREEN, Phase 1 = yellow, Phase 2 = other direction GREEN, Phase 3 = yellow
    GREEN_A_PHASE = 0
    YELLOW_A_PHASE = 1
    GREEN_B_PHASE = 2
    YELLOW_B_PHASE = 3

    # Split controlled lanes into two groups based on which phase gives them green.
    # We infer this by checking which lanes have green (G/g) in a phase state.
    # This avoids manual lane ID mapping.
    def lanes_green_in_phase(phase_index: int):
        # controlled links gives per-connection mapping; simplest practical approach:
        # Use the built-in helper: getControlledLinks and phase state positions.
        # We'll approximate by grouping lanes by their first controlled link position.
        # For small single junction, this is typically reliable.
        links = traci.trafficlight.getControlledLinks(TLS_ID)
        state = logic.phases[phase_index].state

        green_lanes = set()
        for link_index, link_group in enumerate(links):
            if link_index < len(state) and state[link_index] in ("G", "g"):
                # each link_group is list of connections for that signal index
                for conn in link_group:
                    # conn: (fromLane, toLane, viaLane)
                    from_lane = conn[0]
                    green_lanes.add(from_lane)
        return sorted(green_lanes)

    lanes_A = lanes_green_in_phase(GREEN_A_PHASE)
    lanes_B = lanes_green_in_phase(GREEN_B_PHASE)

    # If grouping fails (rare), fall back: split evenly
    if not lanes_A or not lanes_B:
        mid = len(controlled_lanes) // 2
        lanes_A = controlled_lanes[:mid]
        lanes_B = controlled_lanes[mid:]

    print("Group A lanes:", lanes_A)
    print("Group B lanes:", lanes_B)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "phase", "departed", "arrived", "queue_A", "queue_B", "total_queue","green_A", "green_B"])

        t = 0
        while t < SIM_SECONDS:
            # Observe queues at decision point
            qA = get_total_queue(lanes_A)
            qB = get_total_queue(lanes_B)

            # Proportional allocation with bounds
            total = qA + qB
            if total == 0:
                greenA = greenB = MIN_GREEN
            else:
                greenA = clamp(int(round((qA / total) * (MIN_GREEN + MAX_GREEN) )), MIN_GREEN, MAX_GREEN)
                greenB = clamp(int(round((qB / total) * (MIN_GREEN + MAX_GREEN) )), MIN_GREEN, MAX_GREEN)

            # Normalize a bit so cycle isn't crazy (optional but stable)
            # If both got MIN due to rounding, keep it.
            greenA = clamp(greenA, MIN_GREEN, MAX_GREEN)
            greenB = clamp(greenB, MIN_GREEN, MAX_GREEN)

            # ---- Run A green ----
            traci.trafficlight.setPhase(TLS_ID, GREEN_A_PHASE)
            traci.trafficlight.setPhaseDuration(TLS_ID, greenA)
            for _ in range(greenA):
                if t >= SIM_SECONDS: break
                traci.simulationStep()
                departed = traci.simulation.getDepartedNumber()
                arrived = traci.simulation.getArrivedNumber()
                qA_now = get_total_queue(lanes_A)
                qB_now = get_total_queue(lanes_B)
                writer.writerow([t, GREEN_A_PHASE, departed, arrived, qA_now, qB_now, qA_now + qB_now, greenA, greenB])
                t += 1

            # ---- Yellow A ----
            traci.trafficlight.setPhase(TLS_ID, YELLOW_A_PHASE)
            traci.trafficlight.setPhaseDuration(TLS_ID, YELLOW)
            for _ in range(YELLOW):
                if t >= SIM_SECONDS: break
                traci.simulationStep()
                departed = traci.simulation.getDepartedNumber()
                arrived = traci.simulation.getArrivedNumber()
                qA_now = get_total_queue(lanes_A)
                qB_now = get_total_queue(lanes_B)
                writer.writerow([t, YELLOW_A_PHASE, departed, arrived, qA_now, qB_now, qA_now + qB_now, greenA, greenB])
                t += 1

            # ---- Run B green ----
            traci.trafficlight.setPhase(TLS_ID, GREEN_B_PHASE)
            traci.trafficlight.setPhaseDuration(TLS_ID, greenB)
            for _ in range(greenB):
                if t >= SIM_SECONDS: break
                traci.simulationStep()
                departed = traci.simulation.getDepartedNumber()
                arrived = traci.simulation.getArrivedNumber()
                qA_now = get_total_queue(lanes_A)
                qB_now = get_total_queue(lanes_B)
                writer.writerow([t, GREEN_B_PHASE, departed, arrived, qA_now, qB_now, qA_now + qB_now, greenA, greenB])
                t += 1

            # ---- Yellow B ----
            traci.trafficlight.setPhase(TLS_ID, YELLOW_B_PHASE)
            traci.trafficlight.setPhaseDuration(TLS_ID, YELLOW)
            for _ in range(YELLOW):
                if t >= SIM_SECONDS: break
                traci.simulationStep()
                departed = traci.simulation.getDepartedNumber()
                arrived = traci.simulation.getArrivedNumber()
                qA_now = get_total_queue(lanes_A)
                qB_now = get_total_queue(lanes_B)
                writer.writerow([t, YELLOW_B_PHASE, departed, arrived, qA_now, qB_now, qA_now + qB_now, greenA, greenB])
                t += 1

    traci.close()
    print("Saved:", OUT_CSV)


if __name__ == "__main__":
    main()
