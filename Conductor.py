import math
import heapq
import random
import sys
import json
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGraphicsView, QLabel, QPushButton,
    QGraphicsPixmapItem, QGraphicsScene, QFileDialog, QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsPolygonItem,
    QTextEdit, QGraphicsItem, QSlider
)
from PyQt6.QtGui import QPixmap, QPen, QBrush, QPolygonF
from PyQt6.QtCore import QTimer, Qt, QPointF

# Optional geodetic transformer
try:
    from pyproj import Transformer
    _HAVE_PYPROJ = True
except Exception:
    Transformer = None
    _HAVE_PYPROJ = False


class InteractiveGraphicsView(QGraphicsView):
    """
    QGraphicsView subclass that supports mouse panning and wheel zooming.
    Middle-click (or Ctrl+left) drag to pan; wheel to zoom under cursor.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._zoom = 0
        self._zoom_step = 1.15
        self._zoom_range = (-20, 40)
        self._panning = False
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta == 0:
            return
        if delta > 0 and self._zoom < self._zoom_range[1]:
            factor = self._zoom_step
            self.scale(factor, factor)
            self._zoom += 1
        elif delta < 0 and self._zoom > self._zoom_range[0]:
            factor = 1 / self._zoom_step
            self.scale(factor, factor)
            self._zoom -= 1

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self._panning = True
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self._pan_start = event.position()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if getattr(self, "_panning", False):
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(delta.y()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if getattr(self, "_panning", False):
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def resetZoom(self):
        self.resetTransform()
        self._zoom = 0


class GraphManager:
    def __init__(self):
        self.nodes = {}  # id -> {pos: (x,y), type: str}
        self.edges = {}  # id -> {start, end}
        self.adj = {}    # node_id -> [neighbor_id]
        self.runway_nodes = set()

    def add_node(self, node_id, pos, ntype):
        self.nodes[node_id] = {'pos': pos, 'type': ntype}
        if ntype == 'runway':
            self.runway_nodes.add(node_id)
        if node_id not in self.adj:
            self.adj[node_id] = []

    def add_edge(self, u, v, data=None):
        if u in self.nodes and v in self.nodes:
            self.adj[u].append(v)
            self.adj[v].append(u)
            # Store edge data (undirected for now, or keyed by tuple)
            # We use sorted tuple to store undirected properties
            key = tuple(sorted((u, v)))
            self.edges[key] = data or {}

    def get_edge_name(self, u, v):
        key = tuple(sorted((u, v)))
        data = self.edges.get(key, {})
        return data.get('name', 'taxiway')

    def get_pos(self, node_id):
        return self.nodes[node_id]['pos']

    def heuristic(self, a, b):
        ax, ay = self.get_pos(a)
        bx, by = self.get_pos(b)
        return math.hypot(ax - bx, ay - by)

    def get_turn_angle(self, p1, p2, p3):
        """Returns angle deviation in degrees. 0 means straight."""
        x1, y1 = self.get_pos(p1)
        x2, y2 = self.get_pos(p2)
        x3, y3 = self.get_pos(p3)
        
        v1x, v1y = x2 - x1, y2 - y1
        v2x, v2y = x3 - x2, y3 - y2
        
        dot = v1x * v2x + v1y * v2y
        mag1 = math.hypot(v1x, v1y)
        mag2 = math.hypot(v2x, v2y)
        
        if mag1 == 0 or mag2 == 0:
            return 0
            
        # Clamp for acos safety
        val = dot / (mag1 * mag2)
        val = max(-1.0, min(1.0, val))
        angle_rad = math.acos(val)
        return math.degrees(angle_rad)

    def cost(self, prev, curr, nxt, blocked_nodes, reserved_reversed_edges, node_congestion, final_dest=None):
        # Base distance
        dist = self.heuristic(curr, nxt)
        
        # Penalties
        penalty = 0
        
        # Turn penalty
        if prev:
            angle = self.get_turn_angle(prev, curr, nxt)
            # Penalize sharp turns heavily
            penalty += (angle ** 2) * 0.1
            if angle > 170: # Prevent U-turns
                penalty += 1000000
            
        # Runway interaction
        if self.nodes[curr]['type'] == 'runway' or self.nodes[nxt]['type'] == 'runway':
             penalty += 500  # High cost to enter/cross runway unless necessary
             
        # Blocked nodes (Soft constraint for pathfinding, but avoided if possible)
        if nxt in blocked_nodes:
            return float('inf') # Strict Hard Constraint
            
        # Avoid Head-on edges (Global Reservation Check)
        # If we go curr->nxt, we check if anyone has reserved nxt->curr
        # The set contains (u, v) if someone is going u->v.
        # If someone is going nxt->curr, the set contains (nxt, curr).
        if reserved_reversed_edges and (nxt, curr) in reserved_reversed_edges:
            return float('inf') # Strict Hard Constraint
            
        # Congestion Penalty
        # If nxt is heavily booked, add cost
        if node_congestion:
            penalty += node_congestion.get(nxt, 0) * 1000

        # Spawn/Gate Penalty: Do not taxi THROUGH other gates
        if self.nodes[nxt]['type'] == 'spawn':
             # If nxt is a gate, it's allowed ONLY if it is our final destination or our start.
             # We generally only care if it's NOT our destination.
             if final_dest and nxt != final_dest:
                 penalty += 5000000 # Effectively a wall

        return dist + penalty

    def find_path(self, start, end, blocked_nodes=set(), reserved_reversed_edges=set(), node_congestion=None):
        """A* Pathfinding"""
        queue = [(0, 0, start, None)] # f, g, current, prev
        came_from = {}
        g_score = {start: 0}
        
        while queue:
            f, g, current, prev = heapq.heappop(queue)
            
            if current == end:
                # Reconstruct
                path = []
                while current:
                    path.append(current)
                    current = came_from.get(current)
                return path[::-1]

            for neighbor in self.adj.get(current, []):
                # Calculate transitional cost
                step_cost = self.cost(prev, current, neighbor, blocked_nodes, reserved_reversed_edges, node_congestion, end)
                
                if step_cost == float('inf'):
                    continue
                    
                tentative_g = g + step_cost
                
                if tentative_g < g_score.get(neighbor, float('inf')):
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    h = self.heuristic(neighbor, end)
                    heapq.heappush(queue, (tentative_g + h, tentative_g, neighbor, current))
                    
        return None

class ClickablePolygonItem(QGraphicsPolygonItem):
    def __init__(self, polygon, parent_plane, callback):
        super().__init__(polygon)
        self.plane = parent_plane
        self.callback = callback
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)

    def mousePressEvent(self, event):
        self.callback(self.plane.id)
        super().mousePressEvent(event)

class Plane:
    def __init__(self, pid, start_node, end_node, graph_manager, director_callback, is_arrival=False):
        self.id = pid
        self.graph = graph_manager
        self.current_node = start_node
        self.destination_node = end_node
        self.is_arrival = is_arrival
        self.path = [] # The CURRENT clearance path (subset of full flight)
        self.target_node = None # Next node in path
        self.pos = list(self.graph.get_pos(start_node)) # [x, y]
        self.speed = DEFAULT_SPEED # Pixels per tick
        self.heading = 0.0 # Degrees
        self.state = "IDLE" # MOVING, HOLD, STOPPED, TURNING, AWAITING_INSTRUCTION
        self.color = Qt.GlobalColor.magenta
        self.stopped_timer = 0
        self.turn_delay = 0
        self.wait_time = 0 # Time spent in HOLD
        
        # Visual item: Polygon for plane shape
        # Smaller plane shape
        scale = 0.6
        self.poly = QPolygonF([
            QPointF(0, -10*scale),   # Nose
            QPointF(5*scale, 5*scale),     # Right Wing
            QPointF(0, 2*scale),     # Tail center
            QPointF(-5*scale, 5*scale)     # Left Wing
        ])
        
        self.item = ClickablePolygonItem(self.poly, self, director_callback)
        self.item.setBrush(QBrush(self.color))
        self.item.setPen(QPen(Qt.GlobalColor.black, 1))
        self.item.setZValue(10)
        
        # Arrival dot
        if self.is_arrival:
             self.dot = QGraphicsEllipseItem(-1, -1, 2, 2, self.item)
             self.dot.setBrush(QBrush(Qt.GlobalColor.black))
             self.dot.setPen(QPen(Qt.GlobalColor.white, 0))
             
        self.update_visual_pos()

    def update_visual_pos(self):
        self.item.setPos(self.pos[0], self.pos[1])
        self.item.setRotation(self.heading)

    def set_path(self, path):
        self.path = path
        if len(self.path) > 0:
            # If path has current node at start, skip it
            if self.path[0] == self.current_node:
                self.path.pop(0)
                
        if len(self.path) > 0:
            self.target_node = self.path[0]
            self.path.pop(0)
            self.state = "MOVING"
        else:
             self.state = "AWAITING_INSTRUCTION"

    def update(self, dt_sec, obstacles, speed_mult=1.0):
        if self.state == "AWAITING_INSTRUCTION":
            self.item.setBrush(QBrush(Qt.GlobalColor.magenta))
            return
            
        if self.state == "STOPPED":
            self.item.setBrush(QBrush(Qt.GlobalColor.red))
            # Randomly resume? Logic in director
            return

        if self.state == "HOLD":
            self.item.setBrush(QBrush(Qt.GlobalColor.yellow))
            # wait_time incremented by director
            return 
        
        if self.state == "TURNING":
            self.turn_delay -= (1 * speed_mult)
            if self.turn_delay <= 0:
                self.state = "MOVING"
            return
            
        self.item.setBrush(QBrush(self.color))
        
        if not self.target_node:
            return

        # Move towards target
        tx, ty = self.graph.get_pos(self.target_node)
        dx, dy = tx - self.pos[0], ty - self.pos[1]
        dist = math.hypot(dx, dy)
        
        # Calculate angle to target
        target_angle = math.degrees(math.atan2(dy, dx)) + 90 
        
        self.heading = target_angle
        
        current_speed = self.speed * speed_mult
        
        if dist < current_speed:
            # Reached node
            self.pos = [tx, ty]
            self.current_node = self.target_node
            
            if self.path:
                next_node = self.path[0]
                
                # Check turn angle
                # ... existing turn logic ...
                angle_diff = 0 # Simplified check for now
                if len(self.path) > 0:
                     pass # Todo: re-add turn logic if needed
                
                self.target_node = next_node
                self.path.pop(0)
                
                # ... (Turning logic preserved but simplified for this diff) ...
                    
            else:
                self.target_node = None
                self.state = "AWAITING_INSTRUCTION" # Reached end of current clearance
        else:
            # Normalize and move
            move_x = (dx / dist) * self.speed
            move_y = (dy / dist) * self.speed
            self.pos[0] += move_x
            self.pos[1] += move_y

        self.update_visual_pos()

DEFAULT_SPEED = 0.1 # Very Slow for debugging

class Director:
    def __init__(self, graph_manager, scene, log_widget, coll_label, stand_label):
        self.graph = graph_manager
        self.scene = scene
        self.log_widget = log_widget
        self.coll_lbl = coll_label
        self.stand_lbl = stand_label
        self.planes = []
        self.spawn_timer = 0
        self.spawn_interval = 20  # ticks
        self.plane_id_counter = 100 # United 100
        self.selected_plane_id = None
        self.plane_logs = {} # pid -> list of strings
        
        self.speed_multiplier = 1.0 # Multiplier
        
        self.collision_count = 0
        self.standoff_count = 0
        
        # Flight Plan Management
        # plane_id -> { 'full_path': [], 'current_progress': int }
        self.flight_plans = {} 
        
    def select_plane(self, pid):
        self.selected_plane_id = pid
        self.log_widget.clear()
        logs = self.plane_logs.get(pid, [])
        self.log_widget.setText("\n".join(logs))
        # Highlight visual?
        for p in self.planes:
            if p.id == pid:
                p.item.setPen(QPen(Qt.GlobalColor.magenta, 2))
            else:
                p.item.setPen(QPen(Qt.GlobalColor.black, 1))

    def _gather_global_reservations(self):
        """
        Builds a set of edges that are 'booked' in reverse by other planes.
        Uses Flight Plans for future prediction.
        """
        reserved_edges = set()
        node_congestion = {}
        
        # Check active plans
        for pid, plan in self.flight_plans.items():
            # If plane is arrived, ignore?
            # We need to filter out planes that are gone?
            # Actually, flight_plans might stay. Check active planes list.
            
            # Find the plane object to verify it's active
            plane_obj = next((p for p in self.planes if p.id == pid), None)
            if not plane_obj: continue
            
            # Get remaining path from master plan
            full = plan['full_path']
            curr = plan['next_index'] # Index of next node to assign?
            # Actually, the plane is currently AT full[curr-1] or between chunk nodes.
            # To be safe, let's reserve everything from the current plane position onwards.
            
            # Better: current plane path + remaining master plan
            
            # 1. Edges in current 'chunk' (plane.path)
            current_path = []
            if plane_obj.current_node: current_path.append(plane_obj.current_node)
            if plane_obj.target_node: current_path.append(plane_obj.target_node)
            current_path.extend(plane_obj.path)
            
            # 2. Remaining master plan (from next_index)
            remaining_master = full[plan['next_index']:]
            
            # Combine
            future_route = current_path + remaining_master
            
            # Edges
            for i in range(len(future_route) - 1):
                u, v = future_route[i], future_route[i+1]
                reserved_edges.add((u, v))
                
            # Nodes
            for n in future_route:
                node_congestion[n] = node_congestion.get(n, 0) + 1
                
        return reserved_edges, node_congestion

    def set_speed_multiplier(self, val):
        self.speed_multiplier = val
        for p in self.planes:
            p.speed = DEFAULT_SPEED * self.speed_multiplier

    def spawn_plane(self):
        # Throttle logic: 20 planes
        if len(self.planes) >= 20: 
            return

        gates = [n for n, data in self.graph.nodes.items() if data['type'] == 'spawn'] 
        runways = list(self.graph.runway_nodes)

        if not gates or not runways:
            return

        start = random.choice(gates)
        end = random.choice(runways)
        is_arrival = False
        
        if random.random() < 0.5:
             start, end = end, start
             is_arrival = True
             
        p = Plane(self.plane_id_counter, start, end, self.graph, self.select_plane, is_arrival)
        p.speed = DEFAULT_SPEED * self.speed_multiplier
        
        # Calculate MASTER PLAN considering ALL OTHER PLANS
        reserved_edges, node_congestion = self._gather_global_reservations()
        blocked_nodes = {pl.current_node for pl in self.planes if pl.state == "STOPPED"}
        
        # Strictly avoid head-ons with ANY existing plan
        full_path = self.graph.find_path(start, end, blocked_nodes, reserved_edges, node_congestion)
        
        if full_path:
            self.flight_plans[self.plane_id_counter] = {
                'full_path': full_path,
                'next_index': 0, # Index in full_path we have cleared up to
                'cleared_to': 0
            }
            
            self.planes.append(p)
            self.scene.addItem(p.item)
            
            # Init Message
            self.log_msg(f"UKN{p.id}: Requesting taxi.", p.id)
            # self.log_msg(f"ATC: UKN{p.id}, Taxi to runway via initial path.") -> Redundant with first command loop
            
            # Give first chunk? No, let update loop handle "AWAITING_INSTRUCTION"
            p.state = "AWAITING_INSTRUCTION"
            
            self.plane_id_counter += 1

    def log_msg(self, msg, pid=None):
        # Extract PID from msg if not provided? 
        # Better: Pass PID explicitly.
        # But we called it like `log_msg("...")` before.
        # Parse PID if needed: "UKN100:"
        
        target_pid = pid
        if not target_pid:
             if "UKN" in msg:
                 try:
                     parts = msg.split("UKN")
                     sub = parts[1].split(",")[0].split(":")[0] # "100" from "UKN100"
                     target_pid = int(sub)
                 except: pass

        if target_pid:
            if target_pid not in self.plane_logs:
                self.plane_logs[target_pid] = []
            self.plane_logs[target_pid].append(msg)
            
            if self.selected_plane_id == target_pid:
                self.log_widget.append(msg)
                sb = self.log_widget.verticalScrollBar()
                sb.setValue(sb.maximum())
        else:
            # System message?
            pass

    def update(self):
        self.spawn_timer += 1
        if self.spawn_timer > self.spawn_interval:
            self.spawn_plane()
            self.spawn_timer = 0

        # --- Progressive ATC Logic ---
        for p in self.planes:
            if p.state == "AWAITING_INSTRUCTION":
                # Check Master Plan
                plan = self.flight_plans.get(p.id)
                if not plan: continue
                
                full = plan['full_path']
                curr_idx = plan['next_index']
                
                if curr_idx >= len(full):
                    # Done
                    self.log_msg(f"ATC: UKN{p.id}, Frequency change approved. Good day.")
                    p.state = "ARRIVED"
                    continue
                
                # Determine Next Leg (Chunk)
                # "Taxi to decision node" logic
                # Scan master plan from curr_idx full[curr_idx] is where we are (or just finished)
                # We want to find the next node in the path that is an "Intersection" (degree > 2) or the End.
                
                end_idx = len(full)
                found_decision = False
                
                # Start searching from the NEXT node
                for i in range(curr_idx + 1, len(full)):
                    node_id = full[i]
                    # Check connections
                    degree = len(self.graph.adj.get(node_id, []))
                    
                    # It's a decision node if:
                    # 1. It's an intersection (degree > 2)
                    # 2. It's the destination (last node) - loop handles this naturally if not found earlier
                    
                    if degree > 2:
                        end_idx = i + 1 # Include the intersection node in this command
                        found_decision = True
                        break
                
                chunk = full[curr_idx : end_idx]
                
                # Update progress
                plan['next_index'] = end_idx
                
                if not chunk:
                    continue

                target_node = chunk[-1]
                target_type = self.graph.nodes[target_node]['type']
                
                # Analyze Path for Phraseology
                # 1. Taxiways used
                used_taxiways = []
                last_name = None
                for i in range(len(chunk)-1):
                    u, v = chunk[i], chunk[i+1]
                    ename = self.graph.get_edge_name(u, v)
                    if ename and ename != last_name and ename != 'taxiway':
                        used_taxiways.append(ename)
                        last_name = ename
                        
                route_str = ""
                if used_taxiways:
                    # Deduplicate consecutive duplicates just in case
                    route_str = " via " + " ".join(used_taxiways)
                else:
                    route_str = " via taxiways"

                # 2. Crossing Runways
                # Check if any intermediate node is a runway
                crossing_instruction = ""
                for n in chunk[:-1]: # Exclude last node (that's a hold short or line up)
                    if self.graph.nodes[n]['type'] == 'runway':
                        crossing_instruction += f"; Cross Runway {n}"
                
                # 3. Main Instruction
                atc_cmd = ""
                
                # Case A: Entering a Runway for Takeoff
                # If target is runway AND it's our final destination node
                if target_type == 'runway' and target_node == full[-1]:
                     atc_cmd = f"Runway {target_node}, Line up and wait{crossing_instruction}."
                
                # Case B: Holding Short of a Runway
                # If target is runway BUT we are not cleared onto it yet (or crossing it next)
                # Actually, our chunk ends AT the decision node.
                # If the target node is a runway type, we are holding short of it.
                elif target_type == 'runway':
                     atc_cmd = f"Hold short of Runway {target_node}{route_str}{crossing_instruction}."
                
                # Case C: Progressive Taxi (Intersection)
                elif found_decision:
                     atc_cmd = f"Taxi to intersection {target_node}{route_str}{crossing_instruction}."
                
                # Case D: Generic
                else:
                     atc_cmd = f"Continue taxi to {target_node}{route_str}{crossing_instruction}."

                self.log_msg(f"ATC: UKN{p.id}, {atc_cmd}")

                # Issue command
                p.set_path(chunk)

        # Update physics
        for p in self.planes:
            if p.state == "ARRIVED":
                self.scene.removeItem(p.item)
                self.planes.remove(p)
                continue
            
            p.update(1/60, set())




class MainWindow(QMainWindow):
    def __init__(self):
        # window setup
        super().__init__()
        self.setWindowTitle("Randomized Test Environment")
        centralwidget = QWidget()
        self.setCentralWidget(centralwidget)
        self.setMinimumWidth(1200)
        self.setMinimumHeight(800)


        # widgets
        self.simview = InteractiveGraphicsView()
        self.label = QLabel("Test")
        self.label2 = QLabel("Test2")
        self.sidebar1 = QWidget()
        self.sidebar2 = QWidget()
        sidebar1lay = QVBoxLayout()
        sidebar2lay = QVBoxLayout()
        self.btn1 = QPushButton(">", self.simview)
        self.btn2 = QPushButton("<", self.simview)
        self.sidebar2.setVisible(True) # Show sidebar by default now
        # load buttons for geojson
        self.loadNodesBtn = QPushButton("Load Nodes")
        self.loadEdgesBtn = QPushButton("Load Edges")
        self.startSimBtn = QPushButton("Start/Stop Sim")
        # positioning/scale UI removed (automatic georeference used)
        # Load world file for georeferencing
        self._load_world_file()
        # positioning/scale state removed
        self.scene = QGraphicsScene(0,0,self.simview.width(),self.simview.height())
        self.chicagohare = QPixmap("chicagohare.png")

        # simview
        self.scene.addPixmap(self.chicagohare)
        # ensure scene rect matches the background image so items are visible
        try:
            self.scene.setSceneRect(0, 0, self.chicagohare.width(), self.chicagohare.height())
        except Exception:
            pass
        self.simview.setScene(self.scene)



        

        # sidebar
        sidebar1lay.addWidget(self.label)
        sidebar1lay.addWidget(self.loadNodesBtn)
        sidebar1lay.addWidget(self.loadEdgesBtn)
        sidebar1lay.addWidget(self.startSimBtn)
        
        # Debug Controls
        self.collisionLabel = QLabel("Collisions: 0")
        self.standoffLabel = QLabel("Standoffs: 0")
        sidebar1lay.addWidget(self.collisionLabel)
        sidebar1lay.addWidget(self.standoffLabel)
        
        sidebar1lay.addWidget(QLabel("Sim Speed:"))
        self.speedSlider = QSlider(Qt.Orientation.Horizontal)
        self.speedSlider.setMinimum(1)
        self.speedSlider.setMaximum(100)
        self.speedSlider.setValue(1)
        self.speedSlider.valueChanged.connect(self.update_speed)
        sidebar1lay.addWidget(self.speedSlider)
        self.sidebar1.setLayout(sidebar1lay)
    
        # sidebar 2 (ATC Log)
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setPlaceholderText("ATC Communication Log...")
        sidebar2lay.addWidget(QLabel("ATC Frequency 118.7"))
        sidebar2lay.addWidget(self.log_output)
        self.sidebar2.setLayout(sidebar2lay)
        self.sidebar2.setMinimumWidth(300)
    
        self.btn1.clicked.connect(self.toggleSidebar1)
        self.btn2.clicked.connect(self.toggleSidebar2)
        self.loadNodesBtn.clicked.connect(self.open_nodes_dialog)
        self.loadEdgesBtn.clicked.connect(self.open_edges_dialog)
        self.startSimBtn.clicked.connect(self.toggle_simulation)
        # positioning/scale signals removed
        self.sidebar1.hide()
        # self.sidebar2.hide() # Keep log visible

        #main layout setup
        mainlay = QHBoxLayout()
        mainlay.addWidget(self.sidebar1)
        mainlay.addWidget(self.simview)
        mainlay.addWidget(self.sidebar2)
        centralwidget.setLayout(mainlay)

        # Simulation Init
        self.graph_manager = GraphManager()
        self.director = Director(self.graph_manager, self.scene, self.log_output, self.collisionLabel, self.standoffLabel)
        self.timer = QTimer()
        self.timer.timeout.connect(self.director.update)
        self.sim_running = False
        
        # Auto-load for debugging
        import os
        base_dir = os.path.dirname(os.path.abspath(__file__))
        nodes_path = os.path.join(base_dir, "nodesEXPORT.geojson")
        edges_path = os.path.join(base_dir, "linesEXPORT.geojson")
        
        if os.path.exists(nodes_path) and os.path.exists(edges_path):
            print("Auto-loading debug files...")
            self.load_nodes_file(nodes_path)
            self.load_edges_file(edges_path)
            self.toggle_simulation()

    def update_speed(self, value):
        # 1x to 100x
        # Base speed is 0.1
        # Slider 1 -> 0.1
        # Slider 100 -> 10.0
        multiplier = value
        self.director.set_speed_multiplier(multiplier)

    def toggle_simulation(self):
        self.sim_running = not self.sim_running
        if self.sim_running:
            self.timer.start(16) # ~60 FPS
            self.label.setText("Simulation: RUNNING")
        else:
            self.timer.stop()
            self.label.setText("Simulation: PAUSED")


    # sidebar functions
    def showEvent(self, event):
        super().showEvent(event)
        self.updateBtn2Pos()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.updateBtn2Pos()

    def updateBtn2Pos(self):
        self.btn2.move(self.simview.width() - self.btn1.width(), 0)

    def toggleSidebar1(self):
        if not self.sidebar1.isHidden():
            self.sidebar1.hide()
            QTimer.singleShot(0, self.updateBtn2Pos)
            self.btn1.setText(">")
        else:
            self.sidebar1.show()
            self.updateBtn2Pos()
            self.btn1.setText("<")

    def toggleSidebar2(self):
        if not self.sidebar2.isHidden():
            self.sidebar2.hide()
            QTimer.singleShot(0, self.updateBtn2Pos)
            self.btn2.setText("<")
        else:
            self.sidebar2.show()
            self.updateBtn2Pos()
            self.btn2.setText(">")
    # --- GeoJSON loading and drawing ---
    def _load_world_file(self):
        """Load georeferencing parameters from .pgw file."""
        try:
            with open("chicagohare.pgw", "r") as f:
                lines = f.readlines()
            self.pgw_pixel_width = float(lines[0].strip())
            self.pgw_rotation_x = float(lines[1].strip())
            self.pgw_rotation_y = float(lines[2].strip())
            self.pgw_pixel_height = float(lines[3].strip())
            self.pgw_top_left_x = float(lines[4].strip())
            self.pgw_top_left_y = float(lines[5].strip())
            # Prepare optional transformer (WGS84 lon/lat -> image projected coords)
            self.transformer = None
            if _HAVE_PYPROJ:
                # Try common projected CRSes used for Chicago (UTM zone 16N / NAD83)
                for tgt in ("EPSG:32616", "EPSG:26916"):
                    try:
                        t = Transformer.from_crs("EPSG:4326", tgt, always_xy=True)
                        # Test transform near average lat/lon for Chicago
                        tx, ty = t.transform(-87.9, 41.97)
                        # Accept transformer if results are in same ballpark as pgw values
                        if 0 < abs(tx) < 1e7 and 0 < abs(ty) < 1e8:
                            self.transformer = t
                            break
                    except Exception:
                        continue
        except Exception as e:
            print(f"Warning: Could not load world file: {e}")
            self.pgw_pixel_width = None

    def _geo_to_pixel(self, lon, lat):
        """Convert geographic coordinates to pixel coordinates using world file."""
        if self.pgw_pixel_width is None:
            # Fallback to old method if world file not available
            return None
        # Convert lon/lat (decimal degrees) to projected coordinates
        if hasattr(self, 'transformer') and self.transformer is not None:
            try:
                x_map, y_map = self.transformer.transform(lon, lat)
            except Exception:
                return None
        else:
            # No reliable transformer available
            return None
        # Transform using world file parameters
        pixel_x = (x_map - self.pgw_top_left_x) / self.pgw_pixel_width
        pixel_y = (y_map - self.pgw_top_left_y) / self.pgw_pixel_height
        return pixel_x, pixel_y

    def open_nodes_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Nodes GeoJSON", "", "GeoJSON Files (*.geojson *.json);;All Files (*)")
        if path:
            self.load_nodes_file(path)

    def open_edges_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Edges GeoJSON", "", "GeoJSON Files (*.geojson *.json);;All Files (*)")
        if path:
            self.load_edges_file(path)

    def load_nodes_file(self, path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        features = data.get("features", [])
        nodes = []
        for feat in features:
            props = feat.get("properties", {})
            geom = feat.get("geometry", {})
            coords = geom.get("coordinates")
            if not coords:
                continue
            node_id = props.get("node_id")
            node_type = props.get("node_type", "taxiway")
            lon, lat = coords[0], coords[1]
            nodes.append({"id": node_id, "type": node_type, "lon": lon, "lat": lat})
        if nodes:
            self._draw_nodes(nodes)

    def load_edges_file(self, path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        features = data.get("features", [])
        edges = []
        for feat in features:
            props = feat.get("properties", {})
            start_id = props.get("start_nodeID") or props.get("start_nodeId") or props.get("start_node")
            end_id = props.get("end_nodeID") or props.get("end_nodeId") or props.get("end_node")
            line_id = props.get("line_id")
            name = props.get("name") or props.get("ref") or "taxiway"
            
            if start_id is None or end_id is None:
                # try geometry-based edges (LineString with two coords)
                geom = feat.get("geometry", {})
                coords = geom.get("coordinates", [])
                if len(coords) >= 2:
                    edges.append({"id": line_id, "start_coord": coords[0], "end_coord": coords[-1], "name": name})
                continue
            edges.append({"id": line_id, "start": start_id, "end": end_id, "name": name})
        if edges:
            self._draw_edges(edges)

    def _draw_nodes(self, nodes):
        # clear previous node items
        for item in getattr(self, 'node_items', {}).values():
            self.scene.removeItem(item)
        self.node_items = {}
        self.node_positions = {}
        self.original_node_positions = {}  # Store original positions for scaling
        
        # If world file is loaded, try georeferencing; if that fails, fall back to bbox-fitting
        used_georef = False
        if self.pgw_pixel_width is not None:
            converted = []
            for n in nodes:
                res = self._geo_to_pixel(n["lon"], n["lat"])
                converted.append(res)
            if all(r is not None for r in converted):
                used_georef = True
                for n, res in zip(nodes, converted):
                    pixel_x, pixel_y = res
                    pt = QPointF(pixel_x, pixel_y)
                    self.node_positions[n["id"]] = pt
                    self.original_node_positions[n["id"]] = pt
                    
                    # POPULATE GRAPH
                    self.graph_manager.add_node(n["id"], (pixel_x, pixel_y), n["type"])
                    
                    color = Qt.GlobalColor.blue
                    if n["type"] == "runway":
                        color = Qt.GlobalColor.red
                    elif n["type"] == "spawn":
                        color = Qt.GlobalColor.green
                    r = 6
                    ellipse = QGraphicsEllipseItem(pixel_x - r / 2, pixel_y - r / 2, r, r)
                    ellipse.setBrush(QBrush(color))
                    ellipse.setPen(QPen(Qt.GlobalColor.black))
                    ellipse.setToolTip(f"id: {n['id']} type: {n['type']}")
                    self.scene.addItem(ellipse)
                    self.node_items[n["id"]] = ellipse
        # If georeferencing was not usable, fall back to bbox-fitting
        if not used_georef:
            lons = [n["lon"] for n in nodes]
            lats = [n["lat"] for n in nodes]
            min_lon, max_lon = min(lons), max(lons)
            min_lat, max_lat = min(lats), max(lats)
            # map into background image pixel dimensions so overlay aligns with image
            view_w = max(100, self.chicagohare.width())
            view_h = max(100, self.chicagohare.height())
            margin = 40
            lon_span = max_lon - min_lon if max_lon - min_lon != 0 else 1.0
            lat_span = max_lat - min_lat if max_lat - min_lat != 0 else 1.0
            scale = min((view_w - 2 * margin) / lon_span, (view_h - 2 * margin) / lat_span)
            scale *= 0.8
            for n in nodes:
                x = (n["lon"] - min_lon) * scale + margin
                y = (max_lat - n["lat"]) * scale + margin
                pt = QPointF(x, y)
                self.node_positions[n["id"]] = pt
                self.original_node_positions[n["id"]] = pt
                
                # POPULATE GRAPH
                self.graph_manager.add_node(n["id"], (x, y), n["type"])
                
                color = Qt.GlobalColor.blue
                if n["type"] == "runway":
                    color = Qt.GlobalColor.red
                elif n["type"] == "spawn":
                    color = Qt.GlobalColor.green
                r = 6
                ellipse = QGraphicsEllipseItem(x - r / 2, y - r / 2, r, r)
                ellipse.setBrush(QBrush(color))
                ellipse.setPen(QPen(Qt.GlobalColor.black))
                ellipse.setToolTip(f"id: {n['id']} type: {n['type']}")
                self.scene.addItem(ellipse)
                self.node_items[n["id"]] = ellipse
        
        # Find top-left reference point for manual scale (deprecated but kept)
        if self.node_positions:
            self.graph_ref_point = QPointF(
                min(pt.x() for pt in self.original_node_positions.values()),
                min(pt.y() for pt in self.original_node_positions.values())
            )

    def _draw_edges(self, edges):
        # remove previous edges
        for e in getattr(self, 'edge_items', []):
            self.scene.removeItem(e)
        self.edge_items = []
        self._edge_pairs = []  # Store edge pairs for repositioning
        pen = QPen(Qt.GlobalColor.darkGray)
        pen.setWidth(2)
        for ed in edges:
            if "start" in ed and "end" in ed:
                u = ed["start"]
                v = ed["end"]
                s = self.node_positions.get(u)
                t = self.node_positions.get(v)
                if s is not None and t is not None:
                     self.graph_manager.add_edge(u, v, {'name': ed.get('name', 'taxiway')})
                     
                     # Visual line
                     ux, uy = self.graph_manager.get_pos(u)
                     vx, vy = self.graph_manager.get_pos(v)
                     line = QGraphicsLineItem(ux, uy, vx, vy)
                     line.setPen(QPen(Qt.GlobalColor.gray, 2))
                     self.scene.addItem(line)
                     self.edge_items.append(line)
                self._edge_pairs.append((ed["start"], ed["end"]))
            else:
                # coords provided directly - skip for now
                continue

    # Positioning/scale functionality removed (automatic georeference used)
    # other shi
    

    
    




    
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.exec()

