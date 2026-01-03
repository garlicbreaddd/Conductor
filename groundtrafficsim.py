import pygame
import random
import math
import heapq
import sys
from collections import defaultdict

#!/usr/bin/env python3
"""
groundtrafficsim.py

A simple 2D airport ground traffic simulator using Pygame.

- Renders runways, taxiways, and gates.
- Spawns planes at random gates.
- Planes taxi via a waypoint graph to a chosen runway, may receive random hold-short delays,
    then perform takeoff roll and become airborne (removed).
- Displays each plane's heading, position, and velocity.
- Configurable spawn rates and delay probabilities.

Requires: pygame
Run: python groundtrafficsim.py
"""


# ----------------- Configuration -----------------
SCREEN_W, SCREEN_H = 1200, 800
FPS = 60

PLANE_COLORS = [(200, 40, 40), (40, 120, 200), (40, 200, 100), (180, 80, 200)]
GATE_COLOR = (180, 180, 40)
TAXI_COLOR = (150, 150, 150)
RUNWAY_COLOR = (40, 40, 40)
HOLD_LINE_COLOR = (255, 160, 0)

PLANE_MAX_SPEED = 140.0  # pixels per second for taxi/high accel
TAXI_SPEED = 60.0
TAKEOFF_SPEED = 300.0
TAKEOFF_ACCEL = 400.0  # px/s^2

SPAWN_INTERVAL = (3.0, 8.0)  # seconds between spawns (random range)
GATE_PUSHBACK_DELAY = (2.0, 7.0)  # random gate delay before taxi
HOLD_PROBABILITY = 0.12  # chance to get a hold-short at intersections
HOLD_DURATION = (3.0, 10.0)

WAYPOINT_RADIUS = 6
PLANE_RADIUS = 8

# -------------------------------------------------

pygame.init()
screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
clock = pygame.time.Clock()
font = pygame.font.SysFont("Consolas", 14)
small_font = pygame.font.SysFont("Consolas", 12)
random.seed()

# Camera/zoom helper
class Camera:
        def __init__(self, scale=1.0):
                self.scale = scale

        def clamp(self, v):
                return max(0.25, min(4.0, v))

        def zoom_in(self, factor=1.15):
                self.scale = self.clamp(self.scale * factor)

        def zoom_out(self, factor=1.15):
                self.scale = self.clamp(self.scale / factor)

        def world_to_screen(self, pos):
                cx, cy = SCREEN_W / 2.0, SCREEN_H / 2.0
                return ((pos[0] - cx) * self.scale + cx, (pos[1] - cy) * self.scale + cy)

        def scale_value(self, v):
                return max(1, int(v * self.scale))

# ----------------- Utility functions -----------------
def vec_sub(a, b):
        return (a[0] - b[0], a[1] - b[1])

def vec_add(a, b):
        return (a[0] + b[0], a[1] + b[1])

def vec_mul(a, s):
        return (a[0] * s, a[1] * s)

def vec_len(a):
        return math.hypot(a[0], a[1])

def vec_norm(a):
        l = vec_len(a)
        if l == 0:
                return (0.0, 0.0)
        return (a[0] / l, a[1] / l)

def angle_deg_from_vec(v):
        return (math.degrees(math.atan2(-v[1], v[0])) + 360) % 360

# Simple A* for waypoint graph
def astar(graph, positions, start, goal):
        frontier = [(0, start)]
        came_from = {start: None}
        cost_so_far = {start: 0}
        while frontier:
                _, current = heapq.heappop(frontier)
                if current == goal:
                        break
                for nbr in graph[current]:
                        new_cost = cost_so_far[current] + vec_len(vec_sub(positions[current], positions[nbr]))
                        if nbr not in cost_so_far or new_cost < cost_so_far[nbr]:
                                cost_so_far[nbr] = new_cost
                                priority = new_cost + vec_len(vec_sub(positions[nbr], positions[goal]))
                                heapq.heappush(frontier, (priority, nbr))
                                came_from[nbr] = current
        if goal not in came_from:
                return []
        # reconstruct
        path = []
        cur = goal
        while cur is not None:
                path.append(cur)
                cur = came_from[cur]
        path.reverse()
        return path

# ----------------- Airport Layout -----------------
class Airport:
        def __init__(self):
                # Define some runways, taxiways, gates as coordinates.
                # Coordinates are in pixels.
                self.runways = [
                        # (x, y, width, height, heading_degrees)
                        (180, 60, 240, 18, 0),   # small runway top (horizontal)
                        # long runway right (vertical) - x centered at 980, height spans thresholds 80->720
                        (980 - 11, 80, 22, 640, 90),
                ]
                # Taxiway nodes (waypoint graph)
                self.wp_pos = {}
                self.graph = defaultdict(list)
                self.gates = []
                self.gate_idx = []
                self.build_layout()


        def add_wp(self, name, pos):
                self.wp_pos[name] = pos

        def connect(self, a, b):
                self.graph[a].append(b)
                self.graph[b].append(a)

        def build_layout(self):
                # Create a set of taxiway nodes roughly around the airport
                # Central ramp area
                self.add_wp("ramp_center", (420, 360))
                self.add_wp("ramp_north", (400, 260))
                self.add_wp("ramp_south", (420, 460))
                # Place taxi nodes exactly on runway centerlines so edges feed straight into runways
                # small horizontal runway center y = ry + rh/2 => 60 + 18/2 = 69
                self.add_wp("taxi_north_runway", (400, 69))
                # a southern taxi connector (left of the vertical runway)
                self.add_wp("taxi_south_runway", (420, 580))
                self.add_wp("taxi_east_stub", (740, 360))
                self.add_wp("taxi_runway_right_north", (980, 140))
                self.add_wp("taxi_runway_right_south", (980, 580))
                self.add_wp("runway_right_threshold_north", (980, 80))
                self.add_wp("runway_right_threshold_south", (980, 720))
                # Connect graph
                self.connect("ramp_center", "ramp_north")
                self.connect("ramp_center", "ramp_south")
                self.connect("ramp_north", "taxi_north_runway")
                self.connect("ramp_south", "taxi_south_runway")
                self.connect("ramp_center", "taxi_east_stub")
                self.connect("taxi_east_stub", "taxi_runway_right_north")
                self.connect("taxi_east_stub", "taxi_runway_right_south")
                self.connect("taxi_runway_right_north", "runway_right_threshold_north")
                self.connect("taxi_runway_right_south", "runway_right_threshold_south")
                # Gates along ramp_center / ramp_north
                gate_start_x, gate_start_y = 320, 300
                for i in range(8):
                        gx = gate_start_x + i * 20
                        gy = gate_start_y + (-1)**i * 10 + (i // 4) * 18
                        name = f"Gate_{i+1}"
                        self.gates.append((name, (gx, gy)))
                        self.gate_idx.append(name)
                        # connect each gate virtually to ramp_center (they taxi onto ramp_center)
                        self.add_wp(name, (gx, gy))
                        self.connect(name, "ramp_center")

        def nearest_wp(self, pos):
                best = None
                bestd = 1e9
                for k, v in self.wp_pos.items():
                        d = vec_len(vec_sub(pos, v))
                        if d < bestd:
                                bestd = d
                                best = k
                return best

        def runway_center_segment(self, idx):
                rx, ry, rw, rh, heading = self.runways[idx]
                if rw > rh:
                        a = (rx, ry + rh / 2)
                        b = (rx + rw, ry + rh / 2)
                else:
                        a = (rx + rw / 2, ry)
                        b = (rx + rw / 2, ry + rh)
                return a, b

        def runway_vector_for(self, wp_name=None, pos=None):
                # choose runway by explicit target name or nearest to pos
                idx = None
                if wp_name and "runway_right" in wp_name:
                        idx = 1
                else:
                        if pos is None:
                                pos = (SCREEN_W / 2.0, SCREEN_H / 2.0)
                        bestd = 1e9
                        for i, rw in enumerate(self.runways):
                                cx = rw[0] + rw[2] / 2
                                cy = rw[1] + rw[3] / 2
                                d = vec_len(vec_sub(pos, (cx, cy)))
                                if d < bestd:
                                        bestd = d
                                        idx = i
                heading = self.runways[idx][4]
                rad = math.radians(heading)
                return (math.cos(rad), math.sin(rad)), idx

        def project_onto_runway(self, pos, idx):
                a, b = self.runway_center_segment(idx)
                ab = vec_sub(b, a)
                ap = vec_sub(pos, a)
                denom = ab[0] * ab[0] + ab[1] * ab[1]
                if denom == 0:
                        return a
                t = (ap[0] * ab[0] + ap[1] * ab[1]) / denom
                t = max(0.0, min(1.0, t))
                return (a[0] + ab[0] * t, a[1] + ab[1] * t)

        def draw(self, surf, camera: Camera):
                # Background (unscaled)
                surf.fill((80, 160, 80))
                s = camera.scale
                # Draw runways (scale rectangle coords)
                for rx, ry, rw, rh, heading in self.runways:
                        p1 = camera.world_to_screen((rx, ry))
                        p2 = camera.world_to_screen((rx + rw, ry + rh))
                        rect = pygame.Rect(int(min(p1[0], p2[0])), int(min(p1[1], p2[1])),
                                           int(abs(p2[0] - p1[0])), int(abs(p2[1] - p1[1])))
                        pygame.draw.rect(surf, RUNWAY_COLOR, rect)
                        # centerline (draw dashed using transformed coords)
                        if rw > rh:
                                # horizontal runway
                                step = max(6, int(20 * s))
                                for i in range(int(rx), int(rx + rw), max(10, step)):
                                        a = camera.world_to_screen((i, ry + rh / 2 - 1))
                                        pygame.draw.rect(surf, (200, 200, 200), (int(a[0]), int(a[1]), max(2, int(10 * s)), max(1, int(2 * s))))
                        else:
                                step = max(6, int(20 * s))
                                for i in range(int(ry), int(ry + rh), max(10, step)):
                                        a = camera.world_to_screen((rx + rw / 2 - 1, i))
                                        pygame.draw.rect(surf, (200, 200, 200), (int(a[0]), int(a[1]), max(1, int(2 * s)), max(2, int(10 * s))))
                        # label
                        lbl_font = pygame.font.SysFont("Consolas", max(10, int(14 * s)))
                        lbl = lbl_font.render(f"RWY {int(heading):02}", True, (240, 240, 240))
                        surf.blit(lbl, (int(camera.world_to_screen((rx + 6, ry + 6))[0]), int(camera.world_to_screen((rx + 6, ry + 6))[1])))
                # Draw taxiways (edges)
                for a, nbrs in self.graph.items():
                        for b in nbrs:
                                if a < b:  # draw once
                                        pa = camera.world_to_screen(self.wp_pos[a])
                                        pb = camera.world_to_screen(self.wp_pos[b])
                                        pygame.draw.line(surf, TAXI_COLOR, pa, pb, max(1, int(6 * s)))
                                        mid = ((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2)
                                        pygame.draw.circle(surf, (120, 120, 120), (int(mid[0]), int(mid[1])), max(1, int(3 * s)))
                # Draw waypoints and gates with label collision avoidance
                placed = []
                for k, v in self.wp_pos.items():
                        sv = camera.world_to_screen(v)
                        if k.startswith("Gate"):
                                size = max(4, int(12 * s))
                                pygame.draw.rect(surf, GATE_COLOR, pygame.Rect(int(sv[0]-size/2), int(sv[1]-size/2), size, size))
                                fs = max(8, int(10 * s))
                                txt_font = pygame.font.SysFont("Consolas", fs)
                                txt = txt_font.render(k, True, (20, 20, 20))
                                tr = txt.get_rect(topleft=(int(sv[0] - 10 * s), int(sv[1] + 10 * s)))
                                collide = any(tr.colliderect(r) for r in placed)
                                if not collide:
                                        surf.blit(txt, tr.topleft)
                                        placed.append(tr)
                        else:
                                rsize = max(2, int(WAYPOINT_RADIUS * s))
                                pygame.draw.circle(surf, (220, 220, 220), (int(sv[0]), int(sv[1])), rsize)

# ----------------- Plane class -----------------
class Plane:
        id_counter = 1
        def __init__(self, gate_name, gate_pos, dest_runway_point, path_nodes):
                self.id = Plane.id_counter
                Plane.id_counter += 1
                self.color = random.choice(PLANE_COLORS)
                self.pos = gate_pos
                self.heading = 0.0
                self.vel = (0.0, 0.0)
                self.speed = 0.0
                self.state = "at_gate"
                self.gate = gate_name
                self.dest_runway_point = dest_runway_point
                self.path_nodes = list(path_nodes)  # waypoint names
                self.current_wp_idx = 1 if len(self.path_nodes) > 1 else 0
                self.delay_timer = random.uniform(*GATE_PUSHBACK_DELAY)
                self.hold_timer = 0.0
                self.takeoff_speed = TAKEOFF_SPEED
                self.accel = 0.0
                self.on_runway = False
                self.takeoff_accel = TAKEOFF_ACCEL

        def update(self, dt, airport):
                if self.state == "at_gate":
                        self.delay_timer -= dt
                        if self.delay_timer <= 0:
                                # pushback complete, start taxiing
                                self.state = "taxiing"
                                self.speed = TAXI_SPEED * 0.3
                elif self.state == "taxiing":
                        # follow path nodes
                        if self.current_wp_idx >= len(self.path_nodes):
                                # arrived at runway threshold, enter runway and begin takeoff roll
                                self.state = "takeoff_roll"
                                self.speed = TAXI_SPEED * 0.5
                                self.accel = self.takeoff_accel
                                self.on_runway = True
                                return
                        target_name = self.path_nodes[self.current_wp_idx]
                        target_pos = airport.wp_pos[target_name]
                        to_target = vec_sub(target_pos, self.pos)
                        dist = vec_len(to_target)
                        dirv = vec_norm(to_target)
                        # random hold-short behavior when reaching nodes (simulate ATC hold short)
                        if dist < 14:
                                # maybe hold
                                if random.random() < HOLD_PROBABILITY:
                                        self.state = "hold_short"
                                        self.hold_timer = random.uniform(*HOLD_DURATION)
                                else:
                                        self.current_wp_idx += 1
                                return
                        # accelerate to taxi speed
                        target_speed = TAXI_SPEED
                        # ramp speed gently
                        if self.speed < target_speed:
                                self.speed += 80.0 * dt
                        else:
                                self.speed -= 10.0 * dt
                        self.vel = vec_mul(dirv, self.speed)
                        self.pos = vec_add(self.pos, vec_mul(self.vel, dt))
                        self.heading = angle_deg_from_vec(self.vel) if vec_len(self.vel) > 1e-3 else self.heading
                elif self.state == "hold_short":
                        self.hold_timer -= dt
                        if self.hold_timer <= 0:
                                self.state = "taxiing"
                                # resume slightly slowly
                                self.speed = TAXI_SPEED * 0.3
                elif self.state == "takeoff_roll":
                        # determine runway direction and project onto its centerline
                        runway_dir, ridx = airport.runway_vector_for(self.dest_runway_point, self.pos)
                        if not self.on_runway:
                                # snap to runway centerline so takeoff roll starts on runway
                                self.pos = airport.project_onto_runway(self.pos, ridx)
                                self.on_runway = True
                        dirv = vec_norm(runway_dir)
                        # accelerate
                        self.speed += self.accel * dt
                        if self.speed > self.takeoff_speed:
                                # takeoff, become airborne and mark for removal
                                self.state = "airborne"
                                self.vel = vec_mul(dirv, self.speed)
                                return
                        self.vel = vec_mul(dirv, self.speed)
                        self.pos = vec_add(self.pos, vec_mul(self.vel, dt))
                        self.heading = angle_deg_from_vec(self.vel)
                elif self.state == "airborne":
                        # simple climb-out: move along vel and fade
                        self.pos = vec_add(self.pos, vec_mul(self.vel, dt))
                        # no rotation change
                        self.speed = vec_len(self.vel)
                # End update

        def draw(self, surf, camera: Camera):
                sx, sy = camera.world_to_screen(self.pos)
                x, y = int(sx), int(sy)
                # plane body as triangle pointing along heading (scale radius)
                rad = math.radians(self.heading)
                r = max(3, int(PLANE_RADIUS * camera.scale))
                p1 = (x + math.cos(rad) * r * 1.8, y - math.sin(rad) * r * 1.8)
                p2 = (x + math.cos(rad + 2.5) * r, y - math.sin(rad + 2.5) * r)
                p3 = (x + math.cos(rad - 2.5) * r, y - math.sin(rad - 2.5) * r)
                pygame.draw.polygon(surf, self.color, [p1, p2, p3])
                # heading line
                hx = x + math.cos(rad) * (r * 3)
                hy = y - math.sin(rad) * (r * 3)
                pygame.draw.line(surf, (10, 10, 10), (x, y), (hx, hy), max(1, int(2 * camera.scale)))
                # velocity vector
                vlen = vec_len(self.vel)
                if vlen > 1:
                        vdir = vec_norm(self.vel)
                        vx = x + vdir[0] * min(vlen * 0.15 * camera.scale, 60 * camera.scale)
                        vy = y + vdir[1] * min(vlen * 0.15 * camera.scale, 60 * camera.scale)
                        pygame.draw.line(surf, (10, 200, 10), (x, y), (vx, vy), max(1, int(2 * camera.scale)))
                # text info (scaled, avoid overlap handled by airport draw for gates)
                info = f"ID{self.id} {self.state[:6]} H:{int(self.heading)}° P:({int(self.pos[0])},{int(self.pos[1])}) V:{int(vec_len(self.vel))} px/s"
                fs = max(8, int(10 * camera.scale))
                txt_font = pygame.font.SysFont("Consolas", fs)
                txt = txt_font.render(info, True, (20, 20, 20))
                surf.blit(txt, (x + int(12 * camera.scale), y - int(10 * camera.scale)))

# ----------------- Simulation -----------------
class Sim:
        def __init__(self):
                self.airport = Airport()
                self.planes = []
                self.spawn_timer = random.uniform(*SPAWN_INTERVAL)
                # prepare runway threshold waypoint names to target
                self.runway_targets = [
                        "runway_right_threshold_north",
                        "runway_right_threshold_south",
                        "taxi_north_runway",  # allow takeoff from top small runway too
                        "taxi_south_runway",
                ]
                self.camera = Camera()

        def spawn_plane(self):
                # pick a random gate
                gate_name, gate_pos = random.choice(self.airport.gates)
                # pick a runway target waypoint randomly
                dest_rwy = random.choice(self.runway_targets)
                # build path via A*
                start_wp = gate_name
                goal_wp = dest_rwy
                path = astar(self.airport.graph, self.airport.wp_pos, start_wp, goal_wp)
                if not path:
                        return
                plane = Plane(gate_name, self.airport.wp_pos[gate_name], dest_rwy, path)
                self.planes.append(plane)

        def update(self, dt):
                # spawn logic
                self.spawn_timer -= dt
                if self.spawn_timer <= 0:
                        self.spawn_plane()
                        self.spawn_timer = random.uniform(*SPAWN_INTERVAL)
                # update planes
                to_remove = []
                for pl in self.planes:
                        pl.update(dt, self.airport)
                        # remove airborne too far or out of bounds
                        if pl.state == "airborne":
                                x, y = pl.pos
                                if x < -200 or x > SCREEN_W + 200 or y < -200 or y > SCREEN_H + 200:
                                        to_remove.append(pl)
                for p in to_remove:
                        self.planes.remove(p)

        def draw(self, surf):
                self.airport.draw(surf, self.camera)
                for pl in self.planes:
                        pl.draw(surf, self.camera)
                # HUD
                hud = font.render(f"Planes: {len(self.planes)}  Next spawn in: {self.spawn_timer:.1f}s", True, (10, 10, 10))
                surf.blit(hud, (10, 10))
                inst = small_font.render("Random holds & gate delays simulated. Green vector shows current velocity.", True, (10, 10, 10))
                surf.blit(inst, (10, 36))

# ----------------- Main loop -----------------
def main():
        sim = Sim()
        running = True
        while running:
                dt = clock.tick(FPS) / 1000.0
                for ev in pygame.event.get():
                        if ev.type == pygame.QUIT:
                                running = False
                        elif ev.type == pygame.KEYDOWN:
                                if ev.key == pygame.K_ESCAPE:
                                        running = False
                                elif ev.key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
                                        sim.camera.zoom_in()
                                elif ev.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                                        sim.camera.zoom_out()
                        elif ev.type == pygame.MOUSEWHEEL:
                                # ev.y > 0 = up (zoom in)
                                if ev.y > 0:
                                        sim.camera.zoom_in()
                                else:
                                        sim.camera.zoom_out()
                sim.update(dt)
                sim.draw(screen)
                pygame.display.flip()
        pygame.quit()
        sys.exit()

if __name__ == "__main__":
        main()