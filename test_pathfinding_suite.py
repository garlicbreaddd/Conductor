
import math
import random
import time
from atc_backend import AirportGraph, NODE_COORDS

# =========================================================
# CONFIGURATION
# =========================================================
NUM_SIMULATIONS = 100
PLANES_PER_SIM = 20  # 10 In, 10 Out
MAX_STEPS = 2000     # Timeout for each sim
SPEED = 2.0          # Units per step

# =========================================================
# HEADLESS SIMULATION CLASSES
# =========================================================
class SimAgent:
    def __init__(self, agent_id, start_node, end_node, graph):
        self.id = agent_id
        self.pos = list(NODE_COORDS[start_node])
        self.target_pos = None
        self.path_queue = [] # List of coords
        self.finished = False
        self.fuel_burnt = 0
        self.time_elapsed = 0
        
        # Get A* Route
        # We prioritize "Urgency" by just getting the shortest A* path for now.
        # Ideally, low fuel = higher weight on delays, but A* finds shortest path anyway.
        path_nodes = graph.get_astar_route(start_node, end_node)
        
        if path_nodes:
            self.route = path_nodes
            # Convert nodes to coords
            self.path_queue = [NODE_COORDS[n] for n in path_nodes]
            self.target_pos = self.path_queue.pop(0) # Start immediately
        else:
            self.finished = True # Failed to find route

    def update(self):
        if self.finished: return

        self.time_elapsed += 1
        self.fuel_burnt += 0.5 # Idle burn
        
        if self.target_pos:
            dx = self.target_pos[0] - self.pos[0]
            dy = self.target_pos[1] - self.pos[1]
            dist = math.hypot(dx, dy)
            
            if dist < SPEED:
                # Reached node
                self.pos = list(self.target_pos)
                if self.path_queue:
                    self.target_pos = self.path_queue.pop(0)
                else:
                    self.finished = True
            else:
                # Move
                self.pos[0] += (dx/dist) * SPEED
                self.pos[1] += (dy/dist) * SPEED
                self.fuel_burnt += 1.0 # Moving burn

# =========================================================
# METRICS TRACKER
# =========================================================
class Metrics:
    def __init__(self):
        self.total_taxitime = 0
        self.total_fuel = 0
        self.total_conflicts = 0
        self.completed_flights = 0

# =========================================================
# MAIN TEST LOOP
# =========================================================
def run_monte_carlo():
    print(f"--- Starting Monte Carlo Stress Test ({NUM_SIMULATIONS} Sims) ---")
    print(f"Algorithm: A* (Euclidean Heuristic)")
    print(f"Fleet: {PLANES_PER_SIM} planes/sim (10 Dep, 10 Arr)")
    
    graph = AirportGraph()
    metrics = Metrics()
    
    start_time = time.time()
    
    for sim_idx in range(NUM_SIMULATIONS):
        fleet = []
        
        # 1. Spawn Departures (RAMP -> RUNWAY)
        for i in range(10):
            gate = f"GATE_{random.randint(1,3)}"
            rwy = "HOLD_RWY23" if random.random() > 0.5 else "HOLD_RWY12"
            agent = SimAgent(f"DEP_{i}", gate, rwy, graph)
            fleet.append(agent)
            
        # 2. Spawn Arrivals (RUNWAY -> RAMP)
        for i in range(10):
            rwy_end = "RWY23_END" if random.random() > 0.5 else "RWY12_END"
            gate = "RAMP_CENTER" # Simplify arrival to Ramp Center
            agent = SimAgent(f"ARR_{i}", rwy_end, gate, graph)
            fleet.append(agent)
            
        # 3. Fast-Forward Loop
        step = 0
        active_planes = True
        
        while active_planes and step < MAX_STEPS:
            step += 1
            active_cnt = 0
            
            # Update Positions
            for agent in fleet:
                if not agent.finished:
                    agent.update()
                    active_cnt += 1
            
            # Detect Conflicts (Naive O(N^2))
            # Only count conflicts if dist < 20px
            for i, a in enumerate(fleet):
                if a.finished: continue
                for j, b in enumerate(fleet):
                    if i != j and not b.finished:
                        dx = a.pos[0] - b.pos[0]
                        dy = a.pos[1] - b.pos[1]
                        if math.hypot(dx, dy) < 20: 
                            metrics.total_conflicts += 1
            
            if active_cnt == 0:
                active_planes = False

        # End of Sim Logic
        for agent in fleet:
            if agent.finished:
                metrics.completed_flights += 1
                metrics.total_taxitime += agent.time_elapsed
                metrics.total_fuel += agent.fuel_burnt

        if (sim_idx + 1) % 10 == 0:
            print(f"Completed Sim {sim_idx + 1}/{NUM_SIMULATIONS}...")

    end_time = time.time()
    
    # =========================================================
    # REPORT
    # =========================================================
    total_flights = NUM_SIMULATIONS * PLANES_PER_SIM
    success_rate = (metrics.completed_flights / total_flights) * 100
    avg_fuel = metrics.total_fuel / metrics.completed_flights if metrics.completed_flights else 0
    avg_time = metrics.total_taxitime / metrics.completed_flights if metrics.completed_flights else 0
    avg_conflicts = metrics.total_conflicts / NUM_SIMULATIONS
    
    print("\n" + "="*40)
    print("STRESS TEST RESULTS")
    print("="*40)
    print(f"Total Simulations: {NUM_SIMULATIONS}")
    print(f"Total Agents: {total_flights}")
    print(f"Real Time Elapsed: {end_time - start_time:.2f}s")
    print("-" * 20)
    print(f"Success Rate:      {success_rate:.1f}%")
    print(f"Avg Taxi Time:     {avg_time:.1f} steps")
    print(f"Avg Fuel Burn:     {avg_fuel:.1f} units")
    print(f"Avg Conflicts/Sim: {avg_conflicts:.1f}")
    print("="*40)

if __name__ == "__main__":
    run_monte_carlo()
