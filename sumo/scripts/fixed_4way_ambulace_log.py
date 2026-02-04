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
OUT_CSV = BASE_DIR / "output" / "fixed_4way_metrics.csv"

# ====== ADJUST HERE ======
USE_GUI = True
GREEN_TIME = 30
YELLOW_TIME = 3
STEP_DELAY = 0.2

# ambulance detection (log only, no preemption)
EMERGENCY_TYPE_ID = "ambulance"
EMERGENCY_DIST = 150
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

def current_green_direction():
    p = traci.trafficlight.getPhase(TLS_ID)
    if p == PHASE["N_G"]: return "N"
    if p == PHASE["E_G"]: return "E"
    if p == PHASE["S_G"]: return "S"
    if p == PHASE["W_G"]: return "W"
    return None

def find_closest_ambulance_request():
    """
    Return closest ambulance within EMERGENCY_DIST on incoming lanes.
    dict: {vid, approach, dist, lane} or None
    """
    best = None
    for vid in traci.vehicle.getIDList():
        if traci.vehicle.getTypeID(vid) != EMERGENCY_TYPE_ID:
            continue

        lane_id = traci.vehicle.getLaneID(vid)
        if not lane_id:
            continue

        approach = None
        for d, lanes in LANES.items():
            if lane_id in lanes:
                approach = d
                break
        if not approach:
            continue

        lane_pos = traci.vehicle.getLanePosition(vid)
        L = traci.lane.getLength(lane_id)
        dist_to_stop = max(0.0, L - lane_pos)

        if dist_to_stop > EMERGENCY_DIST:
            continue

        cand = {"vid": vid, "approach": approach, "dist": dist_to_stop, "lane": lane_id}
        if best is None or cand["dist"] < best["dist"]:
            best = cand

    return best

def log_row(writer, t, phase_idx, served_dir, emg):
    qN, qE, qS, qW = queue("N"), queue("E"), queue("S"), queue("W")
    departed = traci.simulation.getDepartedNumber()
    arrived = traci.simulation.getArrivedNumber()
    total_q = qN + qE + qS + qW

    writer.writerow([
        t, phase_idx, served_dir, GREEN_TIME, departed, arrived,
        qN, qE, qS, qW, total_q,
        int(emg["active"]),
        emg.get("vid",""),
        emg.get("dir",""),
        f"{emg.get('dist', 0.0):.2f}" if emg.get("dist") is not None else "",
        emg.get("detect_t",""),
        emg.get("green_t",""),
        emg.get("wait_t","")
    ])

def sim_step(t):
    traci.simulationStep()
    if USE_GUI:
        time.sleep(STEP_DELAY)
    return t + 1

def run_phase(phase_idx, duration, t, writer, served_dir, emg):
    traci.trafficlight.setPhase(TLS_ID, phase_idx)
    traci.trafficlight.setPhaseDuration(TLS_ID, duration)

    for _ in range(duration):
        if t >= SIM_SECONDS:
            return t

        # ----- detect ambulance (log only) -----
        req = find_closest_ambulance_request()

        if req:
            # start a new event only when new ambulance id appears
            if (not emg["active"]) or (emg["vid"] != req["vid"]):
                emg["active"] = True
                emg["vid"] = req["vid"]
                emg["dir"] = req["approach"]
                emg["detect_t"] = t
                emg["green_t"] = None
                emg["wait_t"] = None

            emg["dist"] = req["dist"]

        # record first time it naturally becomes green for that dir
        if emg["active"] and emg["green_t"] is None:
            if current_green_direction() == emg["dir"]:
                emg["green_t"] = t
                emg["wait_t"] = emg["green_t"] - emg["detect_t"]

        # log BEFORE stepping (consistent with your other scripts)
        log_row(writer, t, phase_idx, served_dir, emg)

        t = sim_step(t)

    return t

def main():
    sumoBinary = checkBinary("sumo-gui" if USE_GUI else "sumo")
    traci.start([sumoBinary, "-c", SUMO_CFG, "--start"])

    emg = {
        "active": False,
        "vid": "",
        "dir": "",
        "dist": None,
        "detect_t": None,
        "green_t": None,
        "wait_t": None,
    }

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "time","phase","served_dir","green_time","departed","arrived",
            "qN","qE","qS","qW","total_queue",
            "emg_active","emg_id","emg_dir","emg_dist",
            "emg_detect_t","emg_green_t","emg_wait_time"
        ])

        t = 0
        while t < SIM_SECONDS:
            t = run_phase(PHASE["N_G"], GREEN_TIME, t, writer, "N", emg)
            t = run_phase(PHASE["N_Y"], YELLOW_TIME, t, writer, "N_Y", emg)
            t = run_phase(PHASE["E_G"], GREEN_TIME, t, writer, "E", emg)
            t = run_phase(PHASE["E_Y"], YELLOW_TIME, t, writer, "E_Y", emg)
            t = run_phase(PHASE["S_G"], GREEN_TIME, t, writer, "S", emg)
            t = run_phase(PHASE["S_Y"], YELLOW_TIME, t, writer, "S_Y", emg)
            t = run_phase(PHASE["W_G"], GREEN_TIME, t, writer, "W", emg)
            t = run_phase(PHASE["W_Y"], YELLOW_TIME, t, writer, "W_Y", emg)

    traci.close()
    print("Saved:", OUT_CSV)

if __name__ == "__main__":
    main()
