"""
atc_backend.py
Logic Core for ATC Simulation
Fully Connected Airport Graph with Taxiways and Runways
"""
import networkx as nx
import heapq
import math

# --- 1. THE AIRPORT GRAPH (Taxi Logic) ---

# Global Coords (Moved from Simulation for A* Heuristics)
NODE_COORDS = {
    # Gates/Ramp
    "RAMP_CENTER": (400, 120),
    "GATE_1": (340, 80), "GATE_2": (400, 80), "GATE_3": (460, 80),
    
    # Taxiways
    "ALPHA_1": (380, 180), "ALPHA_2": (320, 260), "ALPHA_3": (260, 340), 
    "ALPHA_4": (200, 420), "ALPHA_5": (140, 500),
    "BRAVO_1": (340, 340), "BRAVO_2": (420, 340), "BRAVO_3": (500, 340),
    
    # Runways
    "HOLD_RWY23": (380, 300), "HOLD_RWY12": (480, 300),
    "RWY23_THRESH": (450, 250), "RWY_INTERSECT": (300, 480), "RWY23_END": (150, 650),
    "RWY12_THRESH": (550, 250), "RWY12_END": (650, 600),
    
    # Service
    "LUGGAGE_A": (250, 100),
}

class AirportGraph:
    def __init__(self):
        self.graph = nx.DiGraph()
        
        # ===========================================
        # NODES - All traversable points on airport
        # ===========================================
        self.nodes = list(NODE_COORDS.keys()) # Use keys from dict
        self.graph.add_nodes_from(self.nodes)
        
        # ===========================================
        # EDGES - Bidirectional connections
        # ===========================================
        edges = [
            # GATES -> RAMP
            ("GATE_1", "RAMP_CENTER", 1),
            ("GATE_2", "RAMP_CENTER", 1),
            ("GATE_3", "RAMP_CENTER", 1),
            ("RAMP_CENTER", "GATE_1", 1),
            ("RAMP_CENTER", "GATE_2", 1),
            ("RAMP_CENTER", "GATE_3", 1),
            
            # RAMP -> TAXIWAY ALPHA
            ("RAMP_CENTER", "ALPHA_1", 2),
            ("ALPHA_1", "RAMP_CENTER", 2),
            
            # TAXIWAY ALPHA (Main spine)
            ("ALPHA_1", "ALPHA_2", 2),
            ("ALPHA_2", "ALPHA_1", 2),
            ("ALPHA_2", "ALPHA_3", 2),
            ("ALPHA_3", "ALPHA_2", 2),
            ("ALPHA_3", "ALPHA_4", 2),
            ("ALPHA_4", "ALPHA_3", 2),
            ("ALPHA_4", "ALPHA_5", 2),
            ("ALPHA_5", "ALPHA_4", 2),
            
            # ALPHA -> HOLD SHORT 23
            ("ALPHA_2", "HOLD_RWY23", 1),
            ("HOLD_RWY23", "ALPHA_2", 1),
            
            # TAXIWAY BRAVO (Cross taxiway)
            ("ALPHA_3", "BRAVO_1", 2),
            ("BRAVO_1", "ALPHA_3", 2),
            ("BRAVO_1", "BRAVO_2", 2),
            ("BRAVO_2", "BRAVO_1", 2),
            ("BRAVO_2", "BRAVO_3", 2),
            ("BRAVO_3", "BRAVO_2", 2),
            
            # BRAVO -> HOLD SHORT 12
            ("BRAVO_2", "HOLD_RWY12", 1),
            ("HOLD_RWY12", "BRAVO_2", 1),
            
            # HOLD -> RUNWAY ENTRY
            ("HOLD_RWY23", "RWY23_THRESH", 1),
            ("HOLD_RWY12", "RWY12_THRESH", 1),
            
            # Runway 23/05 (Simplified: Thresh -> Intersect -> End)
            # Length ~ 5 units total
            ("RWY23_THRESH", "RWY_INTERSECT", 2),
            ("RWY_INTERSECT", "RWY23_END", 3),
            
            # Runway 12/30 (Simplified: Thresh -> Intersect -> End)
            ("RWY12_THRESH", "RWY_INTERSECT", 2),
            ("RWY_INTERSECT", "RWY12_END", 3),
            
            # EXIT TAXIWAY (From runway intersection area to taxiway)
            # Simplified exits near the intersection
            ("RWY_INTERSECT", "ALPHA_4", 2), 
            ("ALPHA_4", "RWY_INTERSECT", 2),
            ("RWY_INTERSECT", "BRAVO_3", 2),
            ("BRAVO_3", "RWY_INTERSECT", 2),

            # SERVICE ROADS (Ground Vehicles Only)
            # Connecting Gates to Luggage Area (Assume near Ramp Center/Alpha 1)
            ("GATE_1", "LUGGAGE_A", 2), ("LUGGAGE_A", "GATE_1", 2),
            ("GATE_2", "LUGGAGE_A", 2), ("LUGGAGE_A", "GATE_2", 2),
            ("GATE_3", "LUGGAGE_A", 2), ("LUGGAGE_A", "GATE_3", 2),
            ("RAMP_CENTER", "LUGGAGE_A", 1), ("LUGGAGE_A", "RAMP_CENTER", 1),
        ]
        
        self.graph.add_weighted_edges_from(edges)

    def heuristic(self, u, v):
        """Euclidean distance heuristic for A*."""
        if u not in NODE_COORDS or v not in NODE_COORDS:
            return 0
        x1, y1 = NODE_COORDS[u]
        x2, y2 = NODE_COORDS[v]
        return math.hypot(x2 - x1, y2 - y1)

    def update_weight(self, node, weight):
        """Blocks a node by setting incoming AND outgoing edge weights."""
        if node not in self.graph: 
            return
        # Block incoming edges
        for u, v, data in self.graph.in_edges(node, data=True):
            self.graph[u][v]['weight'] = weight
        # Block outgoing edges
        for u, v, data in self.graph.out_edges(node, data=True):
            self.graph[u][v]['weight'] = weight
            
    def get_taxi_route(self, start_node, end_node):
        """Standard Dijkstra (Fallback)."""
        try:
            path = nx.shortest_path(self.graph, source=start_node, target=end_node, weight='weight')
            return path
        except nx.NetworkXNoPath:
            return None

    def get_astar_route(self, start_node, end_node):
        """Legacy wrapper for A* Pathfinding."""
        return self.get_advanced_route(start_node, end_node)

    def _calculate_angle(self, p1, p2, p3):
        """Calculates angle (in degrees) at p2 between vectors p1->p2 and p2->p3."""
        v1 = (p1[0] - p2[0], p1[1] - p2[1]) # Vector incoming to p2
        v2 = (p3[0] - p2[0], p3[1] - p2[1]) # Vector outgoing from p2
        
        dot = v1[0]*v2[0] + v1[1]*v2[1]
        mag1 = math.hypot(v1[0], v1[1])
        mag2 = math.hypot(v2[0], v2[1])
        
        if mag1 == 0 or mag2 == 0: return 0
        
        # Clamp for floating point errors
        cos_theta = max(-1.0, min(1.0, dot / (mag1 * mag2)))
        angle_rad = math.acos(cos_theta)
        return math.degrees(angle_rad)

    def get_advanced_route(self, start_node, end_node, blocked_nodes=None):
        """
        Custom A* implementation considering:
        1. Distance (Euclidean cost)
        2. Turn Penalties (Minimize sharp turns)
        3. Runway Crossings (High cost)
        4. Dynamic Obstacles (blocked_nodes)
        """
        if blocked_nodes is None: blocked_nodes = set()
        
        if start_node not in self.graph or end_node not in self.graph:
            return None
            
        if end_node in blocked_nodes:
            return None # Destination is blocked

        # Priority Queue: (f_score, current_node, previous_node)
        open_set = []
        heapq.heappush(open_set, (0, start_node, None))
        
        # Cost to reach state (node, prev_node)
        g_score = {} 
        g_score[(start_node, None)] = 0
        
        came_from = {} # (current, prev) -> prev_of_prev (the node before 'prev')
        # Wait, standard came_from maps child -> parent.
        # Here child state is (current, prev). Parent state is (prev, prev_prev).
        # So came_from[(current, prev)] = prev_prev. (Wait, simply 'prev' is the node ID).
        # We need to know which 'prev_prev' led to 'prev' to backtrack further.
        # So values in came_from should be (prev_prev).
        # came_from[(neighbor, current)] = prev
        
        path_found_state = None # Will hold (end_node, final_prev)

        while open_set:
            current_f, current, prev = heapq.heappop(open_set)
            
            if current == end_node:
                path_found_state = (current, prev)
                break

            # Neighbors
            for neighbor in self.graph.neighbors(current):
                if neighbor in blocked_nodes:
                    continue

                # 1. Base Distance Cost
                dist_cost = self.graph[current][neighbor].get('weight', 1)
                
                # 2. Turn Penalty
                turn_cost = 0
                if prev:
                    p1 = NODE_COORDS[prev]
                    p2 = NODE_COORDS[current]
                    p3 = NODE_COORDS[neighbor]
                    
                    v_in = (p2[0]-p1[0], p2[1]-p1[1])
                    v_out = (p3[0]-p2[0], p3[1]-p2[1])
                    
                    dot = v_in[0]*v_out[0] + v_in[1]*v_out[1]
                    mag1 = math.hypot(*v_in)
                    mag2 = math.hypot(*v_out)
                    
                    if mag1 > 0 and mag2 > 0:
                        cos_theta = max(-1.0, min(1.0, dot / (mag1 * mag2)))
                        angle = math.degrees(math.acos(cos_theta))
                        
                        if angle > 45: 
                            turn_cost += 5 
                        if angle > 90:
                            turn_cost += 15 
                
                # 3. Runway Crossing Penalty
                rwy_cost = 0
                if "RWY" in neighbor and "HOLD" not in neighbor and "END" not in neighbor and "THRESH" not in neighbor:
                     # Penalize 'RWY_INTERSECT' or internal runway nodes heavily
                     # But allow entry to THRESH/END as they are start/end points of runway
                     rwy_cost = 50 
                
                tentative_g = g_score.get((current, prev), float('inf')) + dist_cost + turn_cost + rwy_cost
                
                if tentative_g < g_score.get((neighbor, current), float('inf')):
                    g_score[(neighbor, current)] = tentative_g
                    f_score = tentative_g + self.heuristic(neighbor, end_node)
                    heapq.heappush(open_set, (f_score, neighbor, current))
                    came_from[(neighbor, current)] = prev 
                    # Mapping: State(neighbor, ArrivedFrom=current) came from Node(current) [which ArrivedFrom=prev]
                    
        if path_found_state:
            # Reconstruct
            # state is (current_node, arrived_from_node)
            # value in came_from[state] is the node *before* arrived_from_node.
            curr, prev = path_found_state
            path = [curr]
            while prev is not None:
                path.append(prev)
                # Next step back: state was (prev, ???)
                # We need to look up came_from[(curr, prev)] to find ???
                # Wait. came_from key is (neighbor, current). value is 'prev' (the node before current).
                # So to back track from (C, B), we need (B, A). A = came_from[(C, B)].
                next_prev = came_from.get((curr, prev))
                curr = prev
                prev = next_prev
            
            return path[::-1] # Reverse to get Start -> End

        return None # No path found

# --- 2. THE RUNWAY MONITOR (Safety Logic) ---
class RunwayMonitor:
    def __init__(self, runway_rect):
        self.rect = runway_rect
        self.is_occupied = False

    def scan_runway(self, aircraft_list):
        self.is_occupied = False
        rx, ry, rw, rh = self.rect
        
        for plane in aircraft_list:
            px, py = 0, 0
            if hasattr(plane, 'pos'):
                px, py = plane.pos[0], plane.pos[1]
            elif isinstance(plane, dict) and 'pos' in plane:
                px, py = plane['pos']
            
            if (rx <= px <= rx + rw) and (ry <= py <= ry + rh):
                self.is_occupied = True
                return True
        return False

# --- 3. THE TASK SCHEDULER (Priority Logic) ---
class TaskScheduler:
    def __init__(self):
        self.queue = []
        self.PRIORITY_EMERGENCY = 1
        self.PRIORITY_LANDING = 2
        self.PRIORITY_TAKEOFF = 3
        self.PRIORITY_TAXI = 4

    def add_task(self, priority, aircraft_id, request):
        task = (priority, aircraft_id, request)
        heapq.heappush(self.queue, task)

    def get_next_task(self):
        if self.queue:
            return heapq.heappop(self.queue)
        return None

# --- TEST ---
if __name__ == "__main__":
    print("--- Airport Graph Test ---")
    g = AirportGraph()
    
    # Test routes
    routes = [
        ("GATE_1", "HOLD_RWY23"),
        ("GATE_2", "HOLD_RWY12"),
        ("GATE_1", "RWY23_END"),
        ("RAMP_CENTER", "RWY_INTERSECT"),
    ]
    
    for start, end in routes:
        path = g.get_taxi_route(start, end)
        print(f"{start} -> {end}: {path}")
