import os
import sys

if "SUMO_HOME" not in os.environ:
    sys.exit("ERROR: Please set SUMO_HOME. Example: export SUMO_HOME=/usr/share/sumo")

tools = os.path.join(os.environ["SUMO_HOME"], "tools")
sys.path.append(tools)

import traci
from sumolib import checkBinary

SUMO_CFG = os.path.join(os.path.dirname(__file__), "..", "intersection.sumocfg")

sumoBinary = checkBinary("sumo")  # use "sumo-gui" if you want GUI

traci.start([sumoBinary, "-c", SUMO_CFG])

tls_ids = traci.trafficlight.getIDList()
print("Traffic Light IDs:", tls_ids)

traci.close()
