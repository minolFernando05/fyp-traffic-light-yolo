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
OUT_CSV = BASE_DIR / "output" / "full_adaptive_4way_metrics.csv"

# ====== ADJUST HERE ======
USE_GUI = True
G_MIN = 10
G_MAX = 30
GAP_TIME = 3        # seconds of empty queue before ending green early
YELLOW_TIME = 3
MAX_WAIT = 90       # fairness: max seconds a direction can wait
STEP_DELAY = 0.2    # delay between simulation steps (for viewing in GUI)
EXTRA_CLEAR_TIME = 3   # seconds to hold green after ambulance passes junction

USE_LINEAR = True
Q_REF = 15
# =========================

# ===== EMERGENCY PREEMPTION SETTINGS =====
EMERGENCY_TYPE_ID = "ambulance"
EMERGENCY_DIST = 200   # meters to stop line
ALL_RED_TIME = 1       # seconds (buffer)
CLEAR_DIST = 5         # if dist_to_stop < 5m we consider it cleared
# =========================================

LANES = {
    "N": ["north_in_0", "north_in_1"],
    "E": ["east_in_0", "east_in_1"],
    "S": ["south_in_0", "south_in_1"],
    "W": ["west_in_0", "west_in_1"],
}

# Matches your intersection.net.xml order exactly
PHASE = {
    "N_G": 0, "N_Y": 1,
    "E_G": 2, "E_Y": 3,
    "S_G": 4, "S_Y": 5,
    "W_G": 6, "W_Y": 7,
    "ALL_RED": 8,
    "ALL_YELLOW": 9,  # you have this too (optional use)
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

def current_green_direction():
    """
    Determine which direction is currently green by checking current phase index.
    Returns: "N"|"E"|"S"|"W"|None
    """
    p = traci.trafficlight.getPhase(TLS_ID)
    if p == PHASE["N_G"]: return "N"
    if p == PHASE["E_G"]: return "E"
    if p == PHASE["S_G"]: return "S"
    if p == PHASE["W_G"]: return "W"
    return None

def find_ambulance_request():
    """
    Return the closest ambulance within EMERGENCY_DIST on any incoming lane.
    If multiple ambulances exist, pick the one nearest to the stop line.
    Returns: dict {vid, approach, dist, lane} or None
    """
    best = None  # best = smallest dist

    for vid in traci.vehicle.getIDList():
        if traci.vehicle.getTypeID(vid) != EMERGENCY_TYPE_ID:
            continue

        lane_id = traci.vehicle.getLaneID(vid)
        if not lane_id:
            continue

        # Must be on an incoming lane
        approach = None
        for d, lanes in LANES.items():
            if lane_id in lanes:
                approach = d
                break
        if not approach:
            continue

        # Distance to stop line (end of lane)
        lane_pos = traci.vehicle.getLanePosition(vid)
        L = traci.lane.getLength(lane_id)
        dist_to_stop = max(0.0, L - lane_pos)

        # Only trigger if within threshold
        if dist_to_stop > EMERGENCY_DIST:
            continue

        cand = {"vid": vid, "approach": approach, "dist": dist_to_stop, "lane": lane_id}

        if best is None or cand["dist"] < best["dist"]:
            best = cand

    return best


def is_ambulance_cleared(vid):
    """
    Robust: ambulance is cleared once it is NOT on any incoming lane anymore.
    (i.e., it has passed the junction and moved to an outgoing lane)
    """
    if vid not in traci.vehicle.getIDList():
        return True

    lane_id = traci.vehicle.getLaneID(vid)
    if not lane_id:
        return True

    incoming_lanes = set(LANES["N"] + LANES["E"] + LANES["S"] + LANES["W"])

    # Still approaching / at junction
    if lane_id in incoming_lanes:
        return False

    # Now on an outgoing lane (or elsewhere): considered cleared
    return True


def log_row(writer, t, phase_idx, served_dir, green_time):
    qN, qE, qS, qW = queue("N"), queue("E"), queue("S"), queue("W")
    departed = traci.simulation.getDepartedNumber()
    arrived = traci.simulation.getArrivedNumber()
    writer.writerow([t, phase_idx, served_dir, green_time, departed, arrived,
                    qN, qE, qS, qW, qN+qE+qS+qW])

def sim_step(t):
    traci.simulationStep()
    if USE_GUI:
        time.sleep(STEP_DELAY)
    return t + 1

def run_green_gapout(dir_key, phase_green, phase_yellow, target_green, t, writer):
    """
    Run green up to target_green seconds, but end early if:
    - G_MIN has passed AND
    - queue(dir_key) stays 0 for GAP_TIME consecutive seconds
    """
    traci.trafficlight.setPhase(TLS_ID, phase_green)
    traci.trafficlight.setPhaseDuration(TLS_ID, target_green)  # upper bound

    empty_streak = 0
    green_used = 0

    while green_used < target_green and t < SIM_SECONDS:
        log_row(writer, t, phase_green, dir_key, target_green)

        t = sim_step(t)
        green_used += 1

        q_served = queue(dir_key)
        if green_used >= G_MIN:
            if q_served == 0:
                empty_streak += 1
                if empty_streak >= GAP_TIME:
                    break
            else:
                empty_streak = 0

    # Yellow
    traci.trafficlight.setPhase(TLS_ID, phase_yellow)
    traci.trafficlight.setPhaseDuration(TLS_ID, YELLOW_TIME)

    for _ in range(YELLOW_TIME):
        if t >= SIM_SECONDS:
            break
        log_row(writer, t, phase_yellow, f"{dir_key}_Y", YELLOW_TIME)
        t = sim_step(t)

    return t

def main():
    sumoBinary = checkBinary("sumo-gui" if USE_GUI else "sumo")
    traci.start([sumoBinary, "-c", SUMO_CFG, "--start"])

    waited = {"N": 0, "E": 0, "S": 0, "W": 0}

    STATE_NORMAL = "NORMAL"
    STATE_ALL_RED = "ALL_RED"
    STATE_EMERGENCY = "EMERGENCY"

    state = STATE_NORMAL
    state_until = 0
    active_emg = None
    emg_release_at = None

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time","phase","served_dir","green_time","departed","arrived",
                        "qN","qE","qS","qW","total_queue"])

        t = 0
        while t < SIM_SECONDS:
            req = find_ambulance_request()

            # ================= NORMAL =================
            if state == STATE_NORMAL:
                if req:
                    active_emg = req
                    emg_dir = active_emg["approach"]

                    # If ambulance approach already has green, skip all-red and go straight to EMERGENCY
                    cg = current_green_direction()
                    if cg == active_emg["approach"]:
                        state = STATE_EMERGENCY
                    else:
                        state = STATE_ALL_RED
                        state_until = t + ALL_RED_TIME
                        traci.trafficlight.setPhase(TLS_ID, PHASE["ALL_RED"])
                        traci.trafficlight.setPhaseDuration(TLS_ID, ALL_RED_TIME)

                    log_row(writer, t, traci.trafficlight.getPhase(TLS_ID), f"EMG_DETECT_{active_emg['approach']}", 0)
                    t = sim_step(t)
                    continue

                # ---- your original adaptive selection ----
                q = {d: queue(d) for d in waited}
                starving = [d for d in waited if waited[d] >= MAX_WAIT]
                if starving:
                    chosen = max(starving, key=lambda d: q[d])
                else:
                    chosen = max(q, key=q.get)

                g = green_time_from_queue(q[chosen])
                start_t = t

                t = run_green_gapout(
                    dir_key=chosen,
                    phase_green=PHASE[f"{chosen}_G"],
                    phase_yellow=PHASE[f"{chosen}_Y"],
                    target_green=g,
                    t=t,
                    writer=writer
                )

                used = t - start_t
                for d in waited:
                    waited[d] = 0 if d == chosen else waited[d] + used
                continue

            # ================= ALL RED BUFFER =================
            if state == STATE_ALL_RED:
                # Keep all-red until time passes, but if ambulance disappears, still go back to normal safely
                traci.trafficlight.setPhase(TLS_ID, PHASE["ALL_RED"])
                traci.trafficlight.setPhaseDuration(TLS_ID, 1)

                log_row(writer, t, PHASE["ALL_RED"], "ALL_RED", ALL_RED_TIME)
                t = sim_step(t)

                if t >= state_until:
                    state = STATE_EMERGENCY
                continue

            # ================= EMERGENCY =================
            if state == STATE_EMERGENCY:
                if active_emg is None:
                    state = STATE_NORMAL
                    continue

                # Always force green for ambulance approach
                d = active_emg["approach"]
                traci.trafficlight.setPhase(TLS_ID, PHASE[f"{d}_G"])
                traci.trafficlight.setPhaseDuration(TLS_ID, 1)

                log_row(writer, t, PHASE[f"{d}_G"], f"EMG_{d}", 1)

                print("AMB:", active_emg["vid"], "lane:", traci.vehicle.getLaneID(active_emg["vid"]), "state:", state)

                t = sim_step(t)

                # Start hold timer when ambulance leaves incoming lanes (clears junction entry)
                if is_ambulance_cleared(active_emg["vid"]):
                    if emg_release_at is None:
                        emg_release_at = t + EXTRA_CLEAR_TIME

                    # Keep green until timer expires
                    if t >= emg_release_at:
                        state = STATE_NORMAL
                        active_emg = None
                        emg_release_at = None
                        continue
                else:
                    emg_release_at = None

                # Safety: active_emg must be a dict like {"vid":..., "approach":..., ...}
                if not isinstance(active_emg, dict):
                    # if it became a string by mistake, recover gracefully
                    active_emg = None
                    state = STATE_NORMAL
                    continue

                # Update active_emg info if still the same ambulance approaching
                vid = active_emg.get("vid")

                new_req = find_ambulance_request()
                if new_req and isinstance(new_req, dict) and new_req.get("vid") == vid:
                    active_emg = new_req


                continue



    traci.close()
    print("Saved:", OUT_CSV)

if __name__ == "__main__":
    main()
