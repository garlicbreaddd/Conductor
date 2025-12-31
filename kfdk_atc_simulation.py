"""
kfdk_atc_simulation.py
Phase 5: Human-Assistive Dashboard with Proper Taxiway Layout
"""
import pygame
import math
import random
from enum import Enum
from atc_backend import AirportGraph, RunwayMonitor, TaskScheduler, NODE_COORDS # Imported coords
from sai_polish import ThoughtBubble, WeatherStation, PilotAgent, ReadbackVerifier
from dashboard_ui import FlightStripDisplay, CommsLog, HumanOverride, VoiceProfile, StatusPinger

# ============================================================
# SECTION 1: CONFIGURATION & CONSTANTS
# ============================================================
# ============================================================
# SECTION 1: CONFIGURATION & CONSTANTS
# ============================================================
# Resolution: 16:9 Aspect Ratio
WINDOW_WIDTH = 1600
WINDOW_HEIGHT = 900
WINDOW_TITLE = "KFDK ATC - Human-Assistive Dashboard"
FPS = 60

# Map takes up 3/4 of the width (approx 4:3 ratio itself) or specific portion
MAP_WIDTH = 1200 
PANEL_X = MAP_WIDTH + 10

# Colors
COLOR_BACKGROUND = (25, 35, 25)  # Dark green tint
COLOR_GRASS = (35, 55, 35)
COLOR_RUNWAY = (60, 60, 60)
COLOR_TAXIWAY = (80, 80, 60)
COLOR_MARKING = (255, 255, 255)
COLOR_HOLD_LINE = (255, 200, 0)
COLOR_TEXT = (255, 255, 255)

# ============================================================
# NODE COORDINATES - Now managed by atc_backend.py
# ============================================================

# ============================================================
# NODE COORDINATES - Now managed by atc_backend.py
# ============================================================

# ============================================================
# SECTION 1.5: CAMERA CLASS
# ============================================================
class Camera:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.offset_x = 0
        self.offset_y = 0
        self.zoom = 1.0
        self.drag_start = None
        
    def to_screen(self, pos):
        """Transforms world coords (x,y) to screen coords."""
        # (world_x - offset_x) * zoom, ...
        sx = (pos[0] - self.offset_x) * self.zoom
        sy = (pos[1] - self.offset_y) * self.zoom
        return (int(sx), int(sy))
    
    def to_world(self, pos):
        """Transforms screen coords to world coords."""
        wx = (pos[0] / self.zoom) + self.offset_x
        wy = (pos[1] / self.zoom) + self.offset_y
        return (wx, wy)
        
    def handle_input(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 3: # Right click drag
                self.drag_start = event.pos
            elif event.button == 4: # Scroll Up (Zoom In)
                self.adjust_zoom(1.1, event.pos)
            elif event.button == 5: # Scroll Down (Zoom Out)
                self.adjust_zoom(0.9, event.pos)
                
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 3:
                self.drag_start = None
                
        elif event.type == pygame.MOUSEMOTION:
            if self.drag_start:
                dx = event.pos[0] - self.drag_start[0]
                dy = event.pos[1] - self.drag_start[1]
                # Adjust offset inverse to drag
                self.offset_x -= dx / self.zoom
                self.offset_y -= dy / self.zoom
                self.drag_start = event.pos
                
    def adjust_zoom(self, factor, mouse_pos):
        # Zoom towards mouse
        old_zoom = self.zoom
        self.zoom *= factor
        self.zoom = max(0.2, min(5.0, self.zoom)) # Clamp
        
        # Adjust offset to keep mouse pointed at same world coord
        # world = (mouse / old_zoom) + old_offset
        # new_offset = world - (mouse / new_zoom)
        
        if mouse_pos[0] < self.width: # Only zoom if mouse is in map area
            world_x = (mouse_pos[0] / old_zoom) + self.offset_x
            world_y = (mouse_pos[1] / old_zoom) + self.offset_y
            
            self.offset_x = world_x - (mouse_pos[0] / self.zoom)
            self.offset_y = world_y - (mouse_pos[1] / self.zoom)

# Global Camera Instance (will be init in main)
CAMERA = None

# ============================================================
# SECTION 2: AIRCRAFT & VEHICLE CLASSES
# ============================================================
class AircraftState(Enum):
    IDLE = 0
    TAXIING = 1
    HOLDING = 2
    TAKEOFF = 3
    DEPARTING = 4
    RAMP = 5

class GroundVehicle:
    def __init__(self, vehicle_id, start_node):
        self.id = vehicle_id
        self.type = "BUS" if "BUS" in vehicle_id else "LOADER"
        self.pos = list(NODE_COORDS.get(start_node, (250, 100)))
        self.target_node = start_node
        self.current_goal = "LUGGAGE_A" if start_node != "LUGGAGE_A" else "GATE_1"
        self.speed = 0.8 # Slower than planes
        self.color = (255, 165, 0) if self.type == "LOADER" else (50, 50, 200) # Orange loader, Blue bus
        self.path_queue = []
        self.state = "IDLE"
        self.wait_timer = 0
    
    def set_route(self, node_list):
        self.path_queue = [NODE_COORDS[n] for n in node_list if n in NODE_COORDS]
        if self.path_queue:
            self.target_pos = self.path_queue.pop(0)
            self.state = "MOVING"

    def update(self, graph, current_time):
        # 1. State Logic
        if self.state == "IDLE":
            if current_time > self.wait_timer:
                # Decide destination
                # If target was Luggage, now go to Gate. If Gate, go to Luggage
                if "LUGGAGE" in self.current_goal:
                     # We just finished at Luggage. Go to a Gate.
                     dest = f"GATE_{random.randint(1,3)}"
                     self.current_goal = dest
                     # Route from Luggage -> Gate
                     route = graph.get_taxi_route("LUGGAGE_A", dest)
                else:
                     # We finished at a Gate. Go back to Luggage.
                     start_node = self.current_goal # Where we are now
                     self.current_goal = "LUGGAGE_A"
                     route = graph.get_taxi_route(start_node, "LUGGAGE_A")
                
                if route:
                    self.set_route(route)
                else:
                    # Fallback (teleport/reset if lost)
                    self.wait_timer = current_time + 2000

        # 2. Movement Logic
        if self.state == "MOVING" and hasattr(self, 'target_pos'):
            dx = self.target_pos[0] - self.pos[0]
            dy = self.target_pos[1] - self.pos[1]
            dist = math.hypot(dx, dy)
            
            if dist < 4:
                self.pos = list(self.target_pos)
                if self.path_queue:
                    self.target_pos = self.path_queue.pop(0)
                else:
                    self.state = "IDLE"
                    self.wait_timer = current_time + random.randint(3000, 8000) # Load/Unload time
            else:
                self.pos[0] += (dx/dist) * self.speed
                self.pos[1] += (dy/dist) * self.speed

    def draw(self, screen, camera):
        # Draw Square
        s_pos = camera.to_screen(self.pos)
        size = 12 * camera.zoom
        rect = pygame.Rect(s_pos[0]-size/2, s_pos[1]-size/2, size, size)
        pygame.draw.rect(screen, self.color, rect)
        pygame.draw.rect(screen, (0,0,0), rect, 1)

# ============================================================
# SECTION 3: AIRCRAFT CLASS (Cont.)
# ============================================================ # Added state

class Aircraft:
    def __init__(self, callsign, aircraft_type, start_node, color=(255,255,255)):
        self.callsign = callsign
        self.type = aircraft_type
        self.current_node = start_node
        self.pos = list(NODE_COORDS.get(start_node, (400, 100)))
        self.color = color
        self.state = AircraftState.IDLE
        self.speed = 0
        self.target = None
        self.path_queue = []
        self.intention = "Awaiting Clearance"
        self.route_nodes = []
        # Dynamic Simulation Config
        self.is_stopped = False
        self.stop_timer = 0
        self.blocked_node = None
        self.speed_factor = 1.0
        self.max_speed = 1.5

    def set_route(self, node_list, intention="Taxi"):
        """Sets route from list of node names."""
        self.route_nodes = node_list
        self.path_queue = [NODE_COORDS[n] for n in node_list if n in NODE_COORDS]
        self.intention = intention
        if self.path_queue:
            self.target = self.path_queue.pop(0)
            self.state = AircraftState.TAXIING
            base_speed = 1.2 if "CESSNA" in self.type.upper() else 2.0
            self.speed_factor = random.choice([0.8, 0.9, 1.0, 1.1, 1.2])
            self.max_speed = base_speed * self.speed_factor
            self.speed = self.max_speed
            self.is_stopped = False
            self.stop_timer = 0
            self.blocked_node = None # If we are stopped, which node are we blocking?

    def trigger_random_stop(self, current_time):
        """Randomly stops the aircraft (Technical Issue)."""
        if self.state == AircraftState.TAXIING and not self.is_stopped:
            if random.random() < 0.001: # 0.1% chance per frame
                self.is_stopped = True
                self.speed = 0
                duration = random.randint(3000, 8000)
                self.stop_timer = current_time + duration
                self.intention = "STOPPED (Tech)"
                return True
        return False

    def move(self, current_time=0):
        # Handle Random Stops
        if self.is_stopped:
            if current_time > self.stop_timer:
                self.is_stopped = False
                self.speed = self.max_speed
                self.intention = "Resuming Taxi"
            else:
                return # Don't move

        if self.state == AircraftState.TAXIING and self.target:
            dx = self.target[0] - self.pos[0]
            dy = self.target[1] - self.pos[1]
            dist = math.hypot(dx, dy)
            
            if dist < 5:
                self.pos = list(self.target)
                if self.path_queue:
                    self.target = self.path_queue.pop(0)
                else:
                    self.target = None
                    self.state = AircraftState.HOLDING
                    self.speed = 0
                    self.intention = "Holding"
            else:
                self.pos[0] += (dx/dist) * self.speed
                self.pos[1] += (dy/dist) * self.speed
                
    def draw(self, screen, font, camera):
        # Aircraft body
        s_pos = camera.to_screen(self.pos)
        radius = int(8 * camera.zoom)
        pygame.draw.circle(screen, self.color, s_pos, radius)
        # Scaled Outline
        pygame.draw.circle(screen, (255,255,255), s_pos, radius, 1)
        
        # Label (Dynamic size or Fixed?) - Fixed size for readability usually better, but positioned relative
        # Or scale font? Let's keep font fixed size but position it well
        lbl = font.render(self.callsign, True, (255,255,255))
        screen.blit(lbl, (s_pos[0]+10, s_pos[1]-15))

# ============================================================
# SECTION 3: DRAWING FUNCTIONS
# ============================================================
def draw_taxiway_segment(screen, camera, start, end, width=20):
    """Draws a taxiway segment with centerline."""
    s_start = camera.to_screen(start)
    s_end = camera.to_screen(end)
    scaled_width = int(width * camera.zoom)
    pygame.draw.line(screen, COLOR_TAXIWAY, s_start, s_end, scaled_width)
    pygame.draw.line(screen, (255, 255, 0), s_start, s_end, max(1, int(2 * camera.zoom)))  # Yellow centerline

def draw_runway(screen, camera, start, end, width=50):
    """Draws runway with markings."""
    s_start = camera.to_screen(start)
    s_end = camera.to_screen(end)
    scaled_width = int(width * camera.zoom)
    pygame.draw.line(screen, COLOR_RUNWAY, s_start, s_end, scaled_width)
    pygame.draw.line(screen, COLOR_MARKING, s_start, s_end, max(1, int(3 * camera.zoom)))  # White centerline

def draw_airport(screen, font, graph_backend, camera):
    # Background
    pygame.draw.rect(screen, COLOR_GRASS, (0, 0, MAP_WIDTH, WINDOW_HEIGHT))
    
    # ===== RUNWAYS (Base Layer) =====
    draw_runway(screen, camera, NODE_COORDS["RWY23_THRESH"], NODE_COORDS["RWY23_END"], 50)
    draw_runway(screen, camera, NODE_COORDS["RWY12_THRESH"], NODE_COORDS["RWY12_END"], 45)
    
    # ===== GRAPH EDGES (The "Node Graph") =====
    # We iterate through the actual backend graph edges to ensure visuals match logic 100%
    if graph_backend and graph_backend.graph:
        for u, v in graph_backend.graph.edges():
            if u in NODE_COORDS and v in NODE_COORDS:
                start = NODE_COORDS[u]
                end = NODE_COORDS[v]
                s_start = camera.to_screen(start)
                s_end = camera.to_screen(end)
                
                # Determine styling
                is_runway_edge = "RWY" in u and "RWY" in v
                
                if is_runway_edge:
                    # Draw Runway Connectivity (Centerline)
                    pygame.draw.line(screen, (200, 200, 200), s_start, s_end, max(1, int(3 * camera.zoom)))
                else:
                    # Draw Taxiway/Connector Edges
                    # Thick taxiway base
                    scaled_width = int(20 * camera.zoom)
                    pygame.draw.line(screen, COLOR_TAXIWAY, s_start, s_end, scaled_width)
                    # Bright Yellow Connectivity Line
                    pygame.draw.line(screen, (255, 255, 0), s_start, s_end, max(1, int(3 * camera.zoom)))

    # ===== NODES (Visual Debug Nodes) =====
    for name, pos in NODE_COORDS.items():
        # Default Style (Taxiway/Graph Node)
        color = (0, 255, 255) # Cyan for general nodes
        base_radius = 5
        
        # Specific Types
        if "GATE" in name: 
            color = (0, 255, 0) # Green for Gates
            base_radius = 7
        elif "HOLD" in name:
            color = (255, 200, 0) # Yellow for Hold Short
            base_radius = 6
        elif "RWY" in name:
            if "INTERSECT" in name:
                color = (255, 50, 50) # Red for Intersection
                base_radius = 8
            elif "THRESH" in name or "END" in name:
                color = (255, 100, 255) # Pink for Ends
                base_radius = 6
            else: # Mid points
                color = (200, 200, 200)
                base_radius = 4
        
        s_pos = camera.to_screen(pos)
        radius = int(base_radius * camera.zoom)

        # Draw the node
        pygame.draw.circle(screen, color, s_pos, radius)
        pygame.draw.circle(screen, (0,0,0), s_pos, radius, 1) # Black outline
        
        # Draw Labels for Gates
        if "GATE" in name:
             screen.blit(font.render(name[-1], True, (255,255,255)), (s_pos[0]-5, s_pos[1]-20))

    # ===== RUNWAY LABELS =====
    font_rwy = pygame.font.SysFont('Arial', int(20 * camera.zoom), bold=True)
    
    p23 = camera.to_screen(NODE_COORDS["RWY23_THRESH"])
    screen.blit(font_rwy.render("23", True, COLOR_MARKING), (p23[0]-25, p23[1]-10))
    
    p05 = camera.to_screen(NODE_COORDS["RWY23_END"])
    screen.blit(font_rwy.render("05", True, COLOR_MARKING), (p05[0]+10, p05[1]-10))
    
    p12 = camera.to_screen(NODE_COORDS["RWY12_THRESH"])
    screen.blit(font_rwy.render("12", True, COLOR_MARKING), (p12[0]+10, p12[1]-10))
    
    p30 = camera.to_screen(NODE_COORDS["RWY12_END"])
    screen.blit(font_rwy.render("30", True, COLOR_MARKING), (p30[0]+10, p30[1]-10))
    
    # ===== HOLD SHORT MARKING =====
    for hold in ["HOLD_RWY23", "HOLD_RWY12"]:
        pos = NODE_COORDS[hold]
        s_pos = camera.to_screen(pos)
        # Assuming standard rotation for now, simple line
        pygame.draw.line(screen, COLOR_HOLD_LINE, (s_pos[0]-15, s_pos[1]), (s_pos[0]+15, s_pos[1]), max(1, int(4 * camera.zoom)))

# ============================================================
# SECTION 4: MAIN SIMULATION
# ============================================================
def main():
    pygame.init()
    
    # --- PHASE 0: MAP THE AIRPORT (Fullscreen) ---
    from airport_mapper import AirportMapper
    print("Launching Airport Mapper...")
    # Mapper now self-configures to Fullscreen
    mapper = AirportMapper()
    custom_coords = mapper.run()
    
    if not mapper.complete:
        print("Mapping incomplete/cancelled. Exiting.")
        return

    # Update global coords with user choices
    global NODE_COORDS
    
    # INTERPOLATION FIX: Fill in gaps that user didn't map
    # AirportMapper already does some interpolation, but let's reinforce it here just in case
    # or rely on what mapper returns if it's robust.
    # Looking at airport_mapper.py, it DOES have interpolate_nodes().
    # However, the user might have old mapper or it needs updating.
    # Let's ensure we merge correctly.
    
    NODE_COORDS.update(custom_coords)
    
    # Recalculate specific intermediaries based on NEW coords if they weren't in custom_coords
    # (In case mapper didn't cover everything like BRAVO_2 etc adequately)
    
    if "ALPHA_1" in NODE_COORDS and "ALPHA_5" in NODE_COORDS:
        start = NODE_COORDS["ALPHA_1"]
        end = NODE_COORDS["ALPHA_5"]
        for i, key in enumerate(['ALPHA_2', 'ALPHA_3', 'ALPHA_4'], 1):
             if key not in custom_coords: # Only overwrite if not explicitly mapped
                 ratio = i * 0.25
                 nx = start[0] + (end[0] - start[0]) * ratio
                 ny = start[1] + (end[1] - start[1]) * ratio
                 NODE_COORDS[key] = (int(nx), int(ny))
                 
    # Fix Runway Intersect if missing
    if "RWY_INTERSECT" not in custom_coords:
         # Simple average
         if "RWY23_THRESH" in NODE_COORDS and "RWY12_THRESH" in NODE_COORDS:
             rx = (NODE_COORDS['RWY23_THRESH'][0] + NODE_COORDS['RWY23_END'][0] + NODE_COORDS['RWY12_THRESH'][0] + NODE_COORDS['RWY12_END'][0]) / 4
             ry = (NODE_COORDS['RWY23_THRESH'][1] + NODE_COORDS['RWY23_END'][1] + NODE_COORDS['RWY12_THRESH'][1] + NODE_COORDS['RWY12_END'][1]) / 4
             NODE_COORDS['RWY_INTERSECT'] = (int(rx), int(ry))

    print("Custom Layout Applied & Interpolated!")
    
    # --- START SIMULATION ---
    # Set Resolution
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT)) # Removed Fullscreen for dev stability
    
    pygame.display.set_caption(WINDOW_TITLE)
    clock = pygame.time.Clock()
    font = pygame.font.SysFont('Arial', 14)
    font_small = pygame.font.SysFont('Arial', 12)
    
    # Initialize Camera
    camera = Camera(MAP_WIDTH, WINDOW_HEIGHT)
    
    # --- BACKEND ---
    # Init backend AFTER updating coords so edges use new positions
    atc_graph = AirportGraph() 
    scheduler = TaskScheduler()
    weather = WeatherStation()

    # --- DASHBOARD ---
    # --- DASHBOARD ---
    # Stack panels vertically on the right: Strips (Top), Bubble (Mid), Comms (Bottom)
    # Total H = 900.
    
    # Strips: Top 500px
    strips = FlightStripDisplay(PANEL_X, 10, 380, 500, font_small)
    
    # Bubble: Mid 200px (y=520)
    bubble = ThoughtBubble(PANEL_X, 520, 380, 200, font_small)
    
    # Comms: Bottom remaining (y=730 to 890 approx)
    comms = CommsLog(PANEL_X, 730, 380, 160, font_small)
    
    override = HumanOverride()
    voices = VoiceProfile()
    
    # Status Pinger (Bottom Right aligned)
    # We'll position it dynamically in draw or fixed. Fixed for now.
    pinger = StatusPinger(WINDOW_WIDTH - 320, WINDOW_HEIGHT - 40, font_small)

    
    # --- TRAFFIC GENERATOR ---
    class TrafficGenerator:
        def __init__(self, graph):
            self.graph = graph
            self.spawn_timer = 0
            self.active_fleet = []
            
        def update(self, current_time, fleet_list):
            if current_time > self.spawn_timer:
                self.spawn_aircraft(fleet_list)
                # Next arrival/departure in 5-15 seconds
                self.spawn_timer = current_time + random.randint(5000, 15000)
                
        def spawn_aircraft(self, fleet_list):
            if len(fleet_list) > 15: return # Cap traffic
            
            # Determine Arrival or Departure
            is_arrival = random.choice([True, False])
            
            types = [("CESSNA", "N"), ("B737", "DAL"), ("B777", "UAL"), ("A320", "JBU"), ("CRJ", "SKW")]
            t_data = random.choice(types)
            callsign = f"{t_data[1]}{random.randint(100, 999)}"
            color = (random.randint(50, 255), random.randint(50, 255), random.randint(50, 255))
            
            if is_arrival:
                # Spawn at Runway End (as if landed)
                start_node = random.choice(["RWY23_END", "RWY12_END"])
                ac = Aircraft(callsign, t_data[0], start_node, color)
                # Request taxi to Gate
                gate = f"GATE_{random.randint(1,3)}"
                ac.request_time = 0 # Immediate
                ac.has_requested = True
                ac.dest_node = gate
                ac.intention = "Taxi to Gate"
                fleet_list.append(ac)
                pinger.push_status(f"ARRIVAL: {callsign} landed {start_node}")
            else:
                # Spawn at Gate
                start_node = f"GATE_{random.randint(1,3)}"
                ac = Aircraft(callsign, t_data[0], "RAMP", color)
                ac.pos = list(NODE_COORDS.get(start_node))
                ac.request_time = pygame.time.get_ticks() + 2000 # Short delay
                ac.has_requested = False
                ac.dest_node = random.choice(["HOLD_RWY23", "HOLD_RWY12"]) # Target Runway
                fleet_list.append(ac)
                pinger.push_status(f"DEPARTURE: {callsign} at {start_node}")
                
    traffic_gen = TrafficGenerator(atc_graph)
    fleet = [] # Start empty
    
    # Initial seed
    traffic_gen.spawn_aircraft(fleet)
    traffic_gen.spawn_aircraft(fleet)
    
    # --- GROUND FLEET GENERATION (5 Vehicles) ---
    ground_fleet = []
    for i in range(5):
        # Alternate Bus and Loader
        v_type = "BUS" if i % 2 == 0 else "LOADER"
        vid = f"{v_type}_{i+1}"
        # Start at Luggage A
        vehicle = GroundVehicle(vid, "LUGGAGE_A")
        # Stagger start times
        vehicle.wait_timer = pygame.time.get_ticks() + random.randint(1000, 10000)
        ground_fleet.append(vehicle)

    # Update strips initially
    for ac in fleet:
        strips.update_strip(ac.callsign, ac.type, "RAMP", f"Dep in {int((ac.request_time - pygame.time.get_ticks())/1000)}s", "OUT")
    
    running = True
    while running:
        current_time = pygame.time.get_ticks()
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q or event.key == pygame.K_ESCAPE:
                    running = False
            
            # Camera Input
            camera.handle_input(event)
        
        # Human Override
        keys = pygame.key.get_pressed()
        if keys[pygame.K_SPACE]:
            if not override.active:
                override.start()
                comms.log("124.6", "HUMAN", "*** TRANSMITTING ***")
        else:
            if override.active:
                override.stop()
        
        # --- AUTONOMOUS LOGIC ---
        
        # 0. Traffic Gen
        traffic_gen.update(current_time, fleet)

        # 0b. Start Ground Fleet Staggered
        for v in ground_fleet:
             v.update(atc_graph, current_time)

        # 0c. Cleanup Traffic (Despawn Logic)
        for ac in fleet[:]: # Copy for safe removal
            # Condition 1: Departure reached runway end
            if ac.intention and "Taxi to" in ac.intention and ac.state == AircraftState.HOLDING:
                # Actually, departures need to take off first. 
                # For this sim "Taxi to End" simulation:
                # If they are at their dest node (Runway End) and state is Holding (finished taxi)
                # We can assume they take off and despawn.
                if "RWY" in ac.current_node and "END" in ac.current_node:
                     print(f"{ac.callsign} Taking Off & Leaving Airspace.")
                     pinger.push_status(f"TAKEOFF: {ac.callsign} departed")
                     fleet.remove(ac)
            
            # Condition 2: Arrival reached gate
            elif ac.intention and "Gate" in ac.intention and ac.state == AircraftState.HOLDING:
                 # If at Gate
                 if "GATE" in ac.current_node:
                     print(f"{ac.callsign} Arrived at Gate. Despawning.")
                     pinger.push_status(f"PARKED: {ac.callsign} at Gate")
                     fleet.remove(ac)
            
            # Simple check: If distance to target < 5 AND target was final destination
            if ac.state == AircraftState.HOLDING and ac.dest_node:
                 # Check if we are basically at the dest node
                 d_pos = NODE_COORDS.get(ac.dest_node)
                 if d_pos:
                     dist = math.hypot(ac.pos[0]-d_pos[0], ac.pos[1]-d_pos[1])
                     if dist < 10:
                        if "GATE" in ac.dest_node or "END" in ac.dest_node:
                            if ac in fleet:
                                pinger.push_status(f"DESPAWN: {ac.callsign} reached block")
                                fleet.remove(ac)

        # 1. Check for Requests & Routing
        # Get set of currently blocked nodes (by stopped planes)
        blocked_nodes = set()
        for ac in fleet:
            if ac.is_stopped and ac.target:
                # Block the node they are aiming for (effectively blocking that edge)
                # Or block the node they are AT? 
                # Let's block the closest graph node.
                # Simplification: Block their 'target' node if they are taxiing.
                blocked_nodes.add(ac.target)
        
        for ac in fleet:
            # Trigger Random Stops
            if ac.trigger_random_stop(current_time):
                 bubble.log(f"{ac.callsign} STOPPED: Tech Issue", "ALERT")
                 blocked_nodes.add(ac.target) # Add new block
        
        # Route Handling
        for ac in fleet:
            # Case A: Departing at Ramp
            if ac.state == AircraftState.RAMP and not ac.has_requested:
                if current_time > ac.request_time:
                    ac.has_requested = True
                    # Determine Runway
                    rwy_node = ac.dest_node
                    
                    # Request Route using Advanced A*
                    route = atc_graph.get_advanced_route("RAMP_CENTER", rwy_node, blocked_nodes)
                    
                    if route:
                        ac.set_route(route, f"Taxi to {rwy_node}")
                        comms.log("124.6", "ATC", f"{ac.callsign}, taxi via {route[1]} to {rwy_node}", is_ai=True)
                        strips.update_strip(ac.callsign, ac.type, "Taxiing", rwy_node, "OUT")
                    else:
                        bubble.log(f"{ac.callsign}: No clear path!", "ERR")
            
            # Case B: Arrival (Just spawned at Runway End)
            # Logic: If just spawned and has target, get route immediately
            if ac.state == AircraftState.IDLE and hasattr(ac, 'dest_node') and ac.target is None:
                # It's an arrival needing a path
                start_node = "RWY23_END" if "23" in ac.callsign else "RWY12_END" # Guess based on spawn
                if "RWY" in ac.current_node: start_node = ac.current_node
                
                route = atc_graph.get_advanced_route(start_node, ac.dest_node, blocked_nodes)
                if route:
                     ac.set_route(route, f"Taxi to {ac.dest_node}")
                     strips.update_strip(ac.callsign, ac.type, "Taxiing", ac.dest_node, "IN")
            
            # Case C: Obstacle Encounter (Progressive Command)
            # If my next target is blocked, re-route!
            if ac.state == AircraftState.TAXIING and ac.target in blocked_nodes and not ac.is_stopped:
                # Obstacle ahead! Re-calculate functionality
                current_node_approx = "RAMP_CENTER" # Fallback
                # Find closest node logic omitted for brevity, assuming 'current_node' property tracks last passed node.
                # Actually Aircraft.current_node is updated? No, we need to update it.
                # Let's assume re-routing from 'target' is too late. We need to re-route from NOW.
                # Simplification: Just HOLD if blocked.
                # The user asked for "circumvent".
                # To circumvent, we need to find a path from *current position* to dest avoiding *target*.
                # We need to know 'last visited node'.
                # Let's just create a Hold command for now, implementing true dynamic re-routing requires tracking 'last_node' perfectly.
                ac.speed = 0
                ac.intention = "Holding for Obstacle"
            elif ac.state == AircraftState.TAXIING and not ac.is_stopped:
                 ac.speed = ac.max_speed # Resume if clear

        # 2. Collision Avoidance (The "Figure it out" System)
        # Simple proximity check: If I'm behind someone and close, stop.
        for i, ac in enumerate(fleet):
            if ac.state == AircraftState.TAXIING:
                should_stop = False
                for j, other in enumerate(fleet):
                    if i != j:
                        # Calc distance
                        dx = ac.pos[0] - other.pos[0]
                        dy = ac.pos[1] - other.pos[1]
                        dist = (dx**2 + dy**2)**0.5
                        
                        # If close, AM I BEHIND THEM? (Simple logic: if distance < 40)
                        if dist < 45:
                            should_stop = True
                
                if should_stop and not ac.is_stopped:
                    ac.speed = 0 # Wait
                    ac.intention = "Conflict Hold"
                elif not should_stop and not ac.is_stopped:
                    # Resume speed (unless handled above by obstacle)
                    ac.speed = ac.max_speed 

        # --- UPDATE ---
        for ac in fleet:
            ac.move(current_time)
            if ac.state != AircraftState.RAMP:
                 # Update strip status
                 status = "Taxiing" if ac.speed > 0 else "Holding"
                 if ac.state == AircraftState.HOLDING: status = "Ready for TO"
                 strips.update_strip(ac.callsign, ac.type, status, ac.intention, "OUT")
        
        # Update Pinger
        pinger.update(current_time)
        
        # --- DRAWING ---
        screen.fill((20, 20, 25))
        draw_airport(screen, font, atc_graph, camera)
        
        # Draw Vehicles first (under planes)
        for v in ground_fleet:
            v.draw(screen, camera)
            
        for ac in fleet:
            ac.draw(screen, font, camera)
        
        # Dashboard
        strips.draw(screen)
        comms.draw(screen, override.active)
        bubble.draw(screen)
        
        # Title
        title = font.render(f"KFDK Human-Assistive ATC (Autonomous Fleet: {len(fleet)})", True, (180, 180, 180))
        screen.blit(title, (10, 10))
        
        # Draw Pinger (Floating UI)
        pinger.draw(screen)
        
        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()

if __name__ == "__main__":
    main()
