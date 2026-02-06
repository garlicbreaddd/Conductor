import math
import heapq
import random
import sys
import json
import os
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGraphicsView, QLabel, QPushButton,
    QGraphicsPixmapItem, QGraphicsScene, QFileDialog, QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsPolygonItem,
    QTextEdit, QGraphicsItem, QSlider
)
from PyQt6.QtGui import QPixmap, QPen, QBrush, QPolygonF
from PyQt6.QtCore import QTimer, Qt, QPointF
try:
    from pyproj import Transformer
    _HAVE_PYPROJ = True
except Exception:
    Transformer = None
    _HAVE_PYPROJ = False

PLANE_SPEED = 30.0
SEPARATION_TIME = 4.0

class ReservationManager:
    def __init__(self):
        self.node_res = {}
        self.edge_res = {}

    def is_free_node(self, node, start, end, exclude_pid=None):
        for s, e, pid in self.node_res.get(node, []):
            if pid == exclude_pid: continue
            if not (end <= s or start >= e): return False
        return True

    def is_free_edge(self, u, v, start, end, exclude_pid=None):
        key = tuple(sorted((u, v)))
        for s, e, pid in self.edge_res.get(key, []):
            if pid == exclude_pid: continue
            if not (end <= s or start >= e): return False
        return True

    def book_node(self, node, start, end, pid):
        if node not in self.node_res: self.node_res[node] = []
        self.node_res[node].append((start, end, pid))

    def book_edge(self, u, v, start, end, pid):
        key = tuple(sorted((u, v)))
        if key not in self.edge_res: self.edge_res[key] = []
        self.edge_res[key].append((start, end, pid))

    def cleanup(self, current_time):
        threshold = current_time - 10.0
        
        for k in list(self.node_res.keys()):
            self.node_res[k] = [r for r in self.node_res[k] if r[1] > threshold]
            if not self.node_res[k]: del self.node_res[k]
            
        for k in list(self.edge_res.keys()):
            self.edge_res[k] = [r for r in self.edge_res[k] if r[1] > threshold]
            if not self.edge_res[k]: del self.edge_res[k]

    def get_edge_reservations(self, u, v):
        key = tuple(sorted((u, v)))
        return list(self.edge_res.get(key, []))

    def cancel_future_reservations(self, pid, from_time=0.0):
        # remove any reservations for pid that start at or after from_time
        for k in list(self.node_res.keys()):
            self.node_res[k] = [r for r in self.node_res[k] if not (r[2] == pid and r[0] >= from_time)]
            if not self.node_res[k]:
                del self.node_res[k]
        for k in list(self.edge_res.keys()):
            self.edge_res[k] = [r for r in self.edge_res[k] if not (r[2] == pid and r[0] >= from_time)]
            if not self.edge_res[k]:
                del self.edge_res[k]

class InteractiveGraphicsView(QGraphicsView):
    
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
        self.nodes = {}
        self.edges = {}
        self.adj = {}
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
        val = dot / (mag1 * mag2)
        val = max(-1.0, min(1.0, val))
        angle_rad = math.acos(val)
        return math.degrees(angle_rad)

    def cost(self, prev, curr, nxt, blocked_nodes, reserved_reversed_edges, node_congestion, final_dest=None):
        dist = self.heuristic(curr, nxt)
        penalty = 0
        if prev:
            angle = self.get_turn_angle(prev, curr, nxt)
            penalty += (angle ** 2) * 0.1
            if angle > 170:
                penalty += 1000000
        if self.nodes[curr]['type'] == 'runway' or self.nodes[nxt]['type'] == 'runway':
             penalty += 500
        if nxt in blocked_nodes:
            return float('inf')
        if reserved_reversed_edges and (nxt, curr) in reserved_reversed_edges:
            return float('inf')
        if node_congestion:
            penalty += node_congestion.get(nxt, 0) * 1000
        if self.nodes[nxt]['type'] == 'spawn':
             if final_dest and nxt != final_dest:
                 penalty += 5000000

        return dist + penalty

    def find_path(self, start, end, start_time, reservation_manager, pid, blocked_nodes=set(), reserved_reversed_edges=set(), node_congestion=None):
        
        queue = [(0, 0, start, 0.0, None)] 
        came_from = {}
        g_score = {start: 0}
        
        while queue:
            f, g, current, t_elapsed, prev = heapq.heappop(queue)
            
            if current == end:
                path = []
                
                curr = current
                while curr:
                    path.append(curr)
                    curr = came_from.get(curr)
                return path[::-1]

            current_real_time = start_time + t_elapsed

            for neighbor in self.adj.get(current, []):
                dist = self.heuristic(current, neighbor)
                travel_time = dist / PLANE_SPEED
                arrival_real_time = current_real_time + travel_time
                if not reservation_manager.is_free_edge(current, neighbor, current_real_time, arrival_real_time, pid):
                    continue
                if not reservation_manager.is_free_node(neighbor, arrival_real_time, arrival_real_time + SEPARATION_TIME, pid):
                    continue
                step_cost = self.cost(prev, current, neighbor, blocked_nodes, reserved_reversed_edges, node_congestion, end)
                
                if step_cost == float('inf'):
                    continue
                    
                tentative_g = g + step_cost
                
                if tentative_g < g_score.get(neighbor, float('inf')):
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    
                    new_t_elapsed = t_elapsed + travel_time
                    h = self.heuristic(neighbor, end)
                    heapq.heappush(queue, (tentative_g + h, tentative_g, neighbor, new_t_elapsed, current))
                    
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
        self.path = []
        self.target_node = None
        self.pos = list(self.graph.get_pos(start_node))
        self.speed = DEFAULT_SPEED
        self.res_manager = None
        self.assigned_reservations = []
        self.heading = 0.0
        self.state = "IDLE"
        self.color = Qt.GlobalColor.magenta
        self.stopped_timer = 0
        self.turn_delay = 0
        self.wait_time = 0
        self.hold_short_timer = 0
        scale = 0.6
        self.poly = QPolygonF([
            QPointF(0, -10*scale),
            QPointF(5*scale, 5*scale),
            QPointF(0, 2*scale),
            QPointF(-5*scale, 5*scale)
        ])
        
        self.item = ClickablePolygonItem(self.poly, self, director_callback)
        self.item.setBrush(QBrush(self.color))
        self.item.setPen(QPen(Qt.GlobalColor.black, 1))
        self.item.setZValue(10)
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
            if self.path[0] == self.current_node:
                self.path.pop(0)
                
        if len(self.path) > 0:
            self.target_node = self.path[0]
            self.path.pop(0)
            self.state = "MOVING"
        else:
             self.state = "AWAITING_INSTRUCTION"

    def update(self, dt_sec, obstacles, speed_mult=1.0):
        # compute distance to current node (used to decide if we are 'at node')
        try:
            curr_node_pos = self.graph.get_pos(self.current_node)
            dist_to_node = math.hypot(self.pos[0] - curr_node_pos[0], self.pos[1] - curr_node_pos[1])
        except Exception:
            dist_to_node = 0

        AT_NODE_EPS = 1e-3

        if self.state == "AWAITING_INSTRUCTION":
            self.item.setBrush(QBrush(Qt.GlobalColor.magenta))
            return

        if self.state == "STOPPED":
            # if at node, check whether the next edge is now free and resume
            if self.target_node and self.res_manager is not None and dist_to_node <= AT_NODE_EPS:
                travel_time = self.graph.heuristic(self.current_node, self.target_node) / PLANE_SPEED
                depart_time = getattr(self, 'current_time', 0.0)
                arrive_time = depart_time + travel_time
                if self.res_manager.is_free_edge(self.current_node, self.target_node, depart_time, arrive_time, exclude_pid=self.id):
                    self.state = "MOVING"
                else:
                    self.item.setBrush(QBrush(Qt.GlobalColor.red))
                    return
            else:
                self.item.setBrush(QBrush(Qt.GlobalColor.red))
                return

        if self.state == "HOLD":
            self.item.setBrush(QBrush(Qt.GlobalColor.yellow))
            return 
        
        if self.state == "HOLD_SHORT":
            self.item.setBrush(QBrush(Qt.GlobalColor.cyan))
            self.hold_short_timer -= 1
            if self.hold_short_timer <= 0:
                self.state = "DEPARTING"
            return
        
        if self.state == "TURNING":
            self.turn_delay -= (1 * speed_mult)
            if self.turn_delay <= 0:
                self.state = "MOVING"
            return
            
        self.item.setBrush(QBrush(self.color))
        
        if not self.target_node:
            return
        tx, ty = self.graph.get_pos(self.target_node)
        dx, dy = tx - self.pos[0], ty - self.pos[1]
        dist = math.hypot(dx, dy)
        target_angle = math.degrees(math.atan2(dy, dx)) + 90 
        
        self.heading = target_angle
        
        current_speed = self.speed * speed_mult
        
        # If we are at the node and about to depart to target, enforce that we hold a valid reservation
        if dist_to_node <= AT_NODE_EPS:
            travel_time = self.graph.heuristic(self.current_node, self.target_node) / PLANE_SPEED
            depart_time = getattr(self, 'current_time', 0.0)
            arrive_time = depart_time + travel_time
            # check for an assigned reservation that overlaps the desired interval
            has_own_res = False
            eps = 0.2
            for r in (self.assigned_reservations or []):
                if r.get('u') == self.current_node and r.get('v') == self.target_node:
                    # overlap test
                    r0 = r.get('depart', -1e9)
                    r1 = r.get('arrive', 1e9)
                    if not (arrive_time + eps < r0 or depart_time - eps > r1):
                        has_own_res = True
                        break

            if not has_own_res:
                # if we don't have an assigned reservation, but the edge is free now, book it atomically
                if self.res_manager.is_free_edge(self.current_node, self.target_node, depart_time, arrive_time, exclude_pid=None):
                    # book edge and arrival node for ourselves
                    self.res_manager.book_edge(self.current_node, self.target_node, depart_time, arrive_time, self.id)
                    self.res_manager.book_node(self.target_node, arrive_time, arrive_time + SEPARATION_TIME, self.id)
                    # attach to assigned reservations
                    self.assigned_reservations = (self.assigned_reservations or []) + [{'u': self.current_node, 'v': self.target_node, 'depart': depart_time, 'arrive': arrive_time}]
                    has_own_res = True

            if not has_own_res:
                self.state = "STOPPED"
                self.stopped_timer = 0.0
                self.item.setBrush(QBrush(Qt.GlobalColor.red))
                # log reason for stopping
                try:
                    blocker_list = [ (s,e,pid) for (s,e,pid) in self.res_manager.get_edge_reservations(self.current_node, self.target_node) if not (arrive_time <= s or depart_time >= e) ]
                    if blocker_list:
                        self.graph  # use to avoid lint
                        # append a short log to director if available
                        # (Director.log_msg expects ATC-style messages; use plane id)
                        # find director via item callback if possible
                except Exception:
                    pass
                return

        step = current_speed * dt_sec

        if dist <= step:
            self.pos = [tx, ty]
            self.current_node = self.target_node
            
            if self.path:
                next_node = self.path[0]
                angle_diff = 0
                if len(self.path) > 0:
                     pass
                
                self.target_node = next_node
                self.path.pop(0)
                    
            else:
                self.target_node = None
                self.state = "AWAITING_INSTRUCTION"
        else:
            move_x = (dx / dist) * step
            move_y = (dy / dist) * step
            self.pos[0] += move_x
            self.pos[1] += move_y

        self.update_visual_pos()

DEFAULT_SPEED = 0.17
MIN_SEPARATION_DIST = 60
CRITICAL_DIST = 25
FOV_ANGLE = 70

class Director:
    def __init__(self, graph_manager, scene, log_widget, coll_label, stand_label, telemetry_label):
        self.graph = graph_manager
        self.scene = scene
        self.log_widget = log_widget
        self.coll_lbl = coll_label
        self.stand_lbl = stand_label
        self.telemetry_lbl = telemetry_label
        self.planes = []
        self.spawn_timer = 0
        self.spawn_interval = 2
        self.plane_id_counter = 100
        self.selected_plane_id = None
        self.plane_logs = {}
        
        self.speed_multiplier = 1.0
        
        self.collision_count = 0
        self.standoff_count = 0
        self.flight_plans = {}
        self.res_manager = ReservationManager()
        self.global_time = 0.0
        
    def select_plane(self, pid):
        self.selected_plane_id = pid
        self.log_widget.clear()
        logs = self.plane_logs.get(pid, [])
        self.log_widget.setText("\n".join(logs))
        for p in self.planes:
            if p.id == pid:
                p.item.setPen(QPen(Qt.GlobalColor.magenta, 2))
            else:
                p.item.setPen(QPen(Qt.GlobalColor.black, 1))

    def set_speed_multiplier(self, val):
        self.speed_multiplier = val
        for p in self.planes:
            p.speed = PLANE_SPEED * self.speed_multiplier

    def spawn_plane(self):
        if len(self.planes) >= 50: 
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
        if not self.res_manager.is_free_node(start, self.global_time, self.global_time + SEPARATION_TIME, self.plane_id_counter):
            return

        p = Plane(self.plane_id_counter, start, end, self.graph, self.select_plane, is_arrival)
        p.speed = PLANE_SPEED * self.speed_multiplier
        p.res_manager = self.res_manager
        full_path = self.graph.find_path(
            start, end, 
            start_time=self.global_time, 
            reservation_manager=self.res_manager, 
            pid=self.plane_id_counter
        )
        
        if full_path:
            curr_t = self.global_time
            reservations = []
            for i in range(len(full_path) - 1):
                u = full_path[i]
                v = full_path[i+1]
                dist = self.graph.heuristic(u, v)
                arrival_t = curr_t + (dist / PLANE_SPEED)
                self.res_manager.book_edge(u, v, curr_t, arrival_t, self.plane_id_counter)
                reservations.append({'u': u, 'v': v, 'depart': curr_t, 'arrive': arrival_t})
                self.res_manager.book_node(v, arrival_t, arrival_t + SEPARATION_TIME, self.plane_id_counter)
                
                curr_t = arrival_t
            self.res_manager.book_node(start, self.global_time, self.global_time + SEPARATION_TIME, self.plane_id_counter)

            p.assigned_reservations = reservations

            self.flight_plans[self.plane_id_counter] = {
                'full_path': full_path,
                'next_index': 0, 
                'cleared_to': 0
            }
            
            self.planes.append(p)
            self.scene.addItem(p.item)
            self.log_msg(f"UKN{p.id}: Requesting taxi.", p.id)
            p.state = "AWAITING_INSTRUCTION"
            
            self.plane_id_counter += 1
            
        else:
            pass

    def spawn_headon_test(self):
        """Spawn two planes at ends of a path so they will attempt head-on traversal.
        This uses naive planning (no prior reservations) and then books both plans
        into the real reservation table to reproduce and test conflicts."""
        # find a pair of nodes with a path length >= 2
        nodes = list(self.graph.nodes.keys())
        pair = None
        # BFS from each node to find any reachable other node
        for a in nodes:
            visited = {a}
            queue = [a]
            parent = {a: None}
            while queue:
                x = queue.pop(0)
                for y in self.graph.adj.get(x, []):
                    if y not in visited:
                        visited.add(y)
                        parent[y] = x
                        queue.append(y)
                        # require at least 2 edges between endpoints
                        # reconstruct path length
                        path = [y]
                        cur = y
                        while parent[cur] is not None:
                            cur = parent[cur]
                            path.append(cur)
                        if len(path) >= 3:
                            pair = (a, y)
                            break
                if pair: break
            if pair: break

        if not pair:
            self.log_msg("Head-on test: could not find suitable node pair")
            return

        a, b = pair
        # create two planes
        pid1 = self.plane_id_counter
        pid2 = self.plane_id_counter + 1

        p1 = Plane(pid1, a, b, self.graph, self.select_plane, is_arrival=False)
        p2 = Plane(pid2, b, a, self.graph, self.select_plane, is_arrival=False)
        p1.speed = PLANE_SPEED * self.speed_multiplier
        p2.speed = PLANE_SPEED * self.speed_multiplier
        p1.res_manager = self.res_manager
        p2.res_manager = self.res_manager

        # plan naively without considering other reservations
        temp_res = ReservationManager()
        path1 = self.graph.find_path(a, b, start_time=self.global_time, reservation_manager=temp_res, pid=pid1)
        path2 = self.graph.find_path(b, a, start_time=self.global_time, reservation_manager=temp_res, pid=pid2)

        if not path1 or not path2:
            self.log_msg("Head-on test: could not compute naive paths")
            return

        # book both plans into the real reservation manager so they overlap
        def book_plan(path, pid):
            curr_t = self.global_time
            reservations = []
            self.res_manager.book_node(path[0], curr_t, curr_t + SEPARATION_TIME, pid)
            for i in range(len(path)-1):
                u = path[i]; v = path[i+1]
                dist = self.graph.heuristic(u, v)
                arrival_t = curr_t + (dist / PLANE_SPEED)
                # add small margins so overlap is likely
                eps = 0.01
                self.res_manager.book_edge(u, v, curr_t - eps, arrival_t + eps, pid)
                self.res_manager.book_node(v, arrival_t, arrival_t + SEPARATION_TIME, pid)
                reservations.append({'u': u, 'v': v, 'depart': curr_t - eps, 'arrive': arrival_t + eps})
                curr_t = arrival_t
            return reservations

        res1 = book_plan(path1, pid1)
        res2 = book_plan(path2, pid2)

        # store flight plans
        self.flight_plans[pid1] = {'full_path': path1, 'next_index': 0, 'cleared_to': 0}
        self.flight_plans[pid2] = {'full_path': path2, 'next_index': 0, 'cleared_to': 0}

        # add to scene and plane list
        p1.assigned_reservations = res1
        p2.assigned_reservations = res2
        self.planes.append(p1); self.scene.addItem(p1.item)
        self.planes.append(p2); self.scene.addItem(p2.item)
        self.plane_id_counter += 2
        self.log_msg(f"Head-on test: spawned {pid1} at {a} -> {b}")
        self.log_msg(f"Head-on test: spawned {pid2} at {b} -> {a}")

    def log_msg(self, msg, pid=None):
        target_pid = pid
        if not target_pid:
             if "UKN" in msg:
                 try:
                     parts = msg.split("UKN")
                     sub = parts[1].split(",")[0].split(":")[0]
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
            pass

    def update(self):
        self.global_time += (1/60) * self.speed_multiplier
        self.res_manager.cleanup(self.global_time)
        
        self.spawn_timer += 1
        if self.spawn_timer > self.spawn_interval:
            self.spawn_plane()
            self.spawn_timer = 0
        if self.selected_plane_id:
            found = False
            for p in self.planes:
                if p.id == self.selected_plane_id:
                     self.telemetry_lbl.setText(f"Plane {p.id}\nSpeed: {p.speed*self.speed_multiplier:.1f} px/s\nHeading: {p.heading:.1f}")
                     found = True
                     break
            if not found:
                self.telemetry_lbl.setText("Plane Lost / Departed")
        else:
             self.telemetry_lbl.setText("No Plane Selected")
        for p in self.planes:
            if p.state == "AWAITING_INSTRUCTION":
                plan = self.flight_plans.get(p.id)
                if not plan: continue
                
                full = plan['full_path']
                curr_idx = plan['next_index']
                
                if curr_idx >= len(full):
                    self.log_msg(f"ATC: UKN{p.id}, Frequency change approved. Good day.")
                    p.state = "ARRIVED"
                    continue
                
                end_idx = len(full)
                found_decision = False
                for i in range(curr_idx + 1, len(full)):
                    node_id = full[i]
                    degree = len(self.graph.adj.get(node_id, []))
                    
                    if degree > 2:
                        end_idx = i + 1
                        found_decision = True
                        break
                
                chunk = full[curr_idx : end_idx]
                plan['next_index'] = end_idx
                
                if not chunk:
                    continue

                target_node = chunk[-1]
                target_type = self.graph.nodes[target_node]['type']
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
                    route_str = " via " + " ".join(used_taxiways)
                else:
                    route_str = " via taxiways"
                crossing_instruction = ""
                for n in chunk[:-1]:
                    if self.graph.nodes[n]['type'] == 'runway':
                        crossing_instruction += f"; Cross Runway {n}"
                atc_cmd = ""
                if target_type == 'runway' and target_node == full[-1]:
                     atc_cmd = f"Runway {target_node}, Line up and wait{crossing_instruction}."
                elif target_type == 'runway':
                     atc_cmd = f"Hold short of Runway {target_node}{route_str}{crossing_instruction}."
                elif found_decision:
                     atc_cmd = f"Taxi to intersection {target_node}{route_str}{crossing_instruction}."
                else:
                     atc_cmd = f"Continue taxi to {target_node}{route_str}{crossing_instruction}."

                self.log_msg(f"ATC: UKN{p.id}, {atc_cmd}")
                p.set_path(chunk)
        for p in self.planes:
            if p.state == "ARRIVED":
                self.scene.removeItem(p.item)
                self.planes.remove(p)
                continue
            
            if p.state == "DEPARTING":
                self.log_msg(f"ATC: UKN{p.id}, Cleared for takeoff. Good day.")
                self.scene.removeItem(p.item)
                self.planes.remove(p)
                continue
            if p.state == "AWAITING_INSTRUCTION":
                plan = self.flight_plans.get(p.id)
                if plan:
                    full = plan['full_path']
                    if p.current_node == full[-1] and self.graph.nodes[p.current_node]['type'] == 'runway':
                        if p.hold_short_timer == 0:
                            p.hold_short_timer = random.randint(60, 300)
                            p.state = "HOLD_SHORT"
                            self.log_msg(f"ATC: UKN{p.id}, Hold position, traffic on final.")
                            continue
            p.current_time = self.global_time
            dt = (1/60) * self.speed_multiplier
            p.update(dt, self.planes)
            if p.state == "STOPPED":
                p.stopped_timer = getattr(p, 'stopped_timer', 0.0) + dt
                if p.stopped_timer > 1.0:
                    self.resolve_block(p)
            else:
                p.stopped_timer = 0.0

    def resolve_block(self, p):
        # Attempt simple resolution: find blocking reservation on next edge and replan that blocker
        if not p.target_node:
            return
        u = p.current_node
        v = p.target_node
        travel_time = self.graph.heuristic(u, v) / PLANE_SPEED
        depart = self.global_time
        arrive = depart + travel_time
        # find conflicting reservations on the same undirected edge
        conflicts = []
        for s, e, pid in self.res_manager.get_edge_reservations(u, v):
            if pid == p.id: continue
            if not (arrive <= s or depart >= e):
                conflicts.append(pid)
        if not conflicts:
            return
        # choose a blocker to delay (simple heuristic: highest pid)
        blocker_pid = max(conflicts)
        self.log_msg(f"Resolving block: plane {p.id} blocked on edge {u}-{v} by {blocker_pid}")
        # cancel future reservations for blocker and attempt to replan blocker from its current node
        self.res_manager.cancel_future_reservations(blocker_pid, from_time=self.global_time)
        blocker = next((q for q in self.planes if q.id == blocker_pid), None)
        if not blocker:
            return
        # compute a new path for blocker avoiding current reservations
        new_path = self.graph.find_path(blocker.current_node, blocker.destination_node, start_time=self.global_time, reservation_manager=self.res_manager, pid=blocker.id)
        if not new_path:
            # if replan fails, keep blocker stopped a bit longer
            self.log_msg(f"Resolving block: could not replan blocker {blocker_pid}")
            return
        # book new reservations for blocker along new_path
        curr_t = self.global_time
        new_res = []
        for i in range(len(new_path) - 1):
            uu = new_path[i]; vv = new_path[i+1]
            dist = self.graph.heuristic(uu, vv)
            arrival_t = curr_t + (dist / PLANE_SPEED)
            self.res_manager.book_edge(uu, vv, curr_t, arrival_t, blocker.id)
            new_res.append({'u': uu, 'v': vv, 'depart': curr_t, 'arrive': arrival_t})
            self.res_manager.book_node(vv, arrival_t, arrival_t + SEPARATION_TIME, blocker.id)
            curr_t = arrival_t
        # update blocker flight plan and reset its state so it can resume
        self.flight_plans[blocker.id] = {'full_path': new_path, 'next_index': 0, 'cleared_to': 0}
        blocker.set_path(new_path)
        blocker.assigned_reservations = new_res
        blocker.stopped_timer = 0.0

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Randomized Test Environment")
        centralwidget = QWidget()
        self.setCentralWidget(centralwidget)
        self.setMinimumWidth(1200)
        self.setMinimumHeight(800)
        self.simview = InteractiveGraphicsView()
        self.label = QLabel("Test")
        self.label2 = QLabel("Test2")
        self.sidebar1 = QWidget()
        self.sidebar2 = QWidget()
        sidebar1lay = QVBoxLayout()
        sidebar2lay = QVBoxLayout()
        self.btn1 = QPushButton(">", self.simview)
        self.btn2 = QPushButton("<", self.simview)
        self.sidebar2.setVisible(True)
        self.loadMapBtn = QPushButton("Load Map Image")
        self.loadNodesBtn = QPushButton("Load Nodes")
        self.loadEdgesBtn = QPushButton("Load Edges")
        self.headonTestBtn = QPushButton("Head-on Test")
        self.startSimBtn = QPushButton("Start/Stop Sim")
        self.pgw_pixel_width = None
        self.pgw_rotation_x = None
        self.pgw_rotation_y = None
        self.pgw_pixel_height = None
        self.pgw_top_left_x = None
        self.pgw_top_left_y = None
        self.transformer = None
        
        self.scene = QGraphicsScene(0,0,self.simview.width(),self.simview.height())
        self.simview.setScene(self.scene)
        sidebar1lay.addWidget(self.label)
        sidebar1lay.addWidget(self.loadMapBtn)
        sidebar1lay.addWidget(self.loadNodesBtn)
        sidebar1lay.addWidget(self.loadEdgesBtn)
        sidebar1lay.addWidget(self.headonTestBtn)
        sidebar1lay.addWidget(self.startSimBtn)
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
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setPlaceholderText("ATC Communication Log...")
        sidebar2lay.addWidget(QLabel("ATC Frequency 67.67"))
        sidebar2lay.addWidget(self.log_output)
        self.telemetry_label = QLabel("No Plane Selected")
        self.telemetry_label.setStyleSheet("font-weight: bold; border: 1px solid gray; padding: 5px;")
        sidebar2lay.addWidget(QLabel("Telemetry Data:"))
        sidebar2lay.addWidget(self.telemetry_label)
        
        self.sidebar2.setLayout(sidebar2lay)
        self.sidebar2.setMinimumWidth(300)
    
        self.btn1.clicked.connect(self.toggleSidebar1)
        self.btn2.clicked.connect(self.toggleSidebar2)
        self.loadMapBtn.clicked.connect(self.open_map_dialog)
        self.loadNodesBtn.clicked.connect(self.open_nodes_dialog)
        self.loadEdgesBtn.clicked.connect(self.open_edges_dialog)
        self.headonTestBtn.clicked.connect(lambda: self.director.spawn_headon_test())
        self.startSimBtn.clicked.connect(self.toggle_simulation)
        self.sidebar1.hide()
        mainlay = QHBoxLayout()
        mainlay.addWidget(self.sidebar1)
        mainlay.addWidget(self.simview)
        mainlay.addWidget(self.sidebar2)
        centralwidget.setLayout(mainlay)
        self.graph_manager = GraphManager()
        self.director = Director(self.graph_manager, self.scene, self.log_output, self.collisionLabel, self.standoffLabel, self.telemetry_label)
        self.timer = QTimer()
        self.timer.timeout.connect(self.director.update)
        self.sim_running = False

    def update_speed(self, value):
        multiplier = value / 2.0
        self.director.set_speed_multiplier(multiplier)

    def toggle_simulation(self):
        self.sim_running = not self.sim_running
        if self.sim_running:
            self.timer.start(16)
            self.label.setText("Simulation: RUNNING")
        else:
            self.timer.stop()
            self.label.setText("Simulation: PAUSED")
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
    def open_map_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Map Image", "", "Images (*.png *.jpg *.jpeg *.tif *.tiff);;All Files (*)")
        if path:
            self.load_map_file(path)

    def load_map_file(self, path):
        self.scene.clear()
        self.graph_manager = GraphManager()
        self.director = Director(self.graph_manager, self.scene, self.log_output, self.collisionLabel, self.standoffLabel, self.telemetry_label)
        self.timer.timeout.disconnect()
        self.timer.timeout.connect(self.director.update)
        
        self.map_pixmap = QPixmap(path)
        self.scene.addPixmap(self.map_pixmap)
        try:
            self.scene.setSceneRect(0, 0, self.map_pixmap.width(), self.map_pixmap.height())
        except: pass
        base, ext = os.path.splitext(path)
        possible_pgw = base + ".pgw"
        if os.path.exists(possible_pgw):
             self._load_world_file(possible_pgw)
        else:
             print("No world file found, manual scaling might be needed (not implemented).")
             self.pgw_pixel_width = None

    def _load_world_file(self, path):
        
        try:
            with open(path, "r") as f:
                lines = f.readlines()
            self.pgw_pixel_width = float(lines[0].strip())
            self.pgw_rotation_x = float(lines[1].strip())
            self.pgw_rotation_y = float(lines[2].strip())
            self.pgw_pixel_height = float(lines[3].strip())
            self.pgw_top_left_x = float(lines[4].strip())
            self.pgw_top_left_y = float(lines[5].strip())
            self.transformer = None
            if _HAVE_PYPROJ:
                candidates = ["EPSG:32616", "EPSG:26916", "EPSG:32618", "EPSG:26918"] 
                for tgt in candidates:
                    try:
                        t = Transformer.from_crs("EPSG:4326", tgt, always_xy=True)
                        self.transformer = t 
                        break
                    except Exception:
                        continue
        except Exception as e:
            print(f"Warning: Could not load world file: {e}")
            self.pgw_pixel_width = None

    def _geo_to_pixel(self, lon, lat):
        
        if self.pgw_pixel_width is None:
            return None
        if hasattr(self, 'transformer') and self.transformer is not None:
            try:
                x_map, y_map = self.transformer.transform(lon, lat)
            except Exception:
                return None
        else:
            return None
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
                geom = feat.get("geometry", {})
                coords = geom.get("coordinates", [])
                if len(coords) >= 2:
                    edges.append({"id": line_id, "start_coord": coords[0], "end_coord": coords[-1], "name": name})
                continue
            edges.append({"id": line_id, "start": start_id, "end": end_id, "name": name})
        if edges:
            self._draw_edges(edges)

    def _draw_nodes(self, nodes):
        for item in getattr(self, 'node_items', {}).values():
            self.scene.removeItem(item)
        self.node_items = {}
        self.node_positions = {}
        self.original_node_positions = {}
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
        if not used_georef:
            lons = [n["lon"] for n in nodes]
            lats = [n["lat"] for n in nodes]
            min_lon, max_lon = min(lons), max(lons)
            min_lat, max_lat = min(lats), max(lats)
            if hasattr(self, 'map_pixmap') and self.map_pixmap:
                view_w = max(100, self.map_pixmap.width())
                view_h = max(100, self.map_pixmap.height())
            else:
                view_w = 2000
                view_h = 2000
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
        if self.node_positions:
            self.graph_ref_point = QPointF(
                min(pt.x() for pt in self.original_node_positions.values()),
                min(pt.y() for pt in self.original_node_positions.values())
            )

    def _draw_edges(self, edges):
        for e in getattr(self, 'edge_items', []):
            self.scene.removeItem(e)
        self.edge_items = []
        self._edge_pairs = []
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
                     ux, uy = self.graph_manager.get_pos(u)
                     vx, vy = self.graph_manager.get_pos(v)
                     line = QGraphicsLineItem(ux, uy, vx, vy)
                     line.setPen(QPen(Qt.GlobalColor.gray, 2))
                     self.scene.addItem(line)
                     self.edge_items.append(line)
                self._edge_pairs.append((ed["start"], ed["end"]))
            else:
                continue
    

    
    

    
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.exec()

