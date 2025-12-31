
import pygame
import math
from enum import Enum

# Config
WINDOW_WIDTH = 900
WINDOW_HEIGHT = 700
FPS = 60
TITLE = "Generated Airport Simulation"

# Colors
COLOR_BG = (20, 20, 30)
COLOR_RWY = (80, 80, 80)
COLOR_TXT = (255, 255, 255)

# Captured Coordinates
RWY_MAIN_START = (100, 100)
RWY_MAIN_END = (400, 400)
RWY_CROSS_START = (100, 400)
RWY_CROSS_END = (400, 100)

GATE_1 = (50, 50)
GATE_2 = (60, 60)

HOLD_SHORT_MAIN = (120, 120)
HOLD_SHORT_CROSS = (120, 380)

RAMP_CENTER = (50, 250)

# Logic Constants
SPEED_TAXI = 2.0
SPEED_TAKEOFF = 4.0  # Slower as requested
ARRIVAL_THRESHOLD = 5

# --- VISUAL HELPERS ---
def draw_runway_detailed(screen, start, end, width, label_start, label_end):
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.sqrt(dx**2 + dy**2)
    if length == 0: return
    
    nx = -dy / length * (width / 2)
    ny = dx / length * (width / 2)
    
    corners = [
        (start[0] + nx, start[1] + ny),
        (start[0] - nx, start[1] - ny),
        (end[0] - nx, end[1] - ny),
        (end[0] + nx, end[1] + ny),
    ]
    
    # Body
    pygame.draw.polygon(screen, COLOR_RWY, corners)
    # Borders
    pygame.draw.line(screen, (200, 200, 200), corners[0], corners[3], 2)
    pygame.draw.line(screen, (200, 200, 200), corners[1], corners[2], 2)
    # Centerline
    pygame.draw.line(screen, (255, 255, 255), start, end, 2)

    # Labels
    font = pygame.font.SysFont('Arial', 12)
    screen.blit(font.render(label_start, True, COLOR_TXT), (start[0]-20, start[1]-20))
    screen.blit(font.render(label_end, True, COLOR_TXT), (end[0], end[1]))

def draw_label(screen, text, pos, color=(255,255,255)):
    font = pygame.font.SysFont('Arial', 12)
    screen.blit(font.render(text, True, color), (pos[0]+10, pos[1]))

def draw_airport(screen):
    draw_runway_detailed(screen, RWY_MAIN_START, RWY_MAIN_END, 50, "MAIN", "END")
    draw_runway_detailed(screen, RWY_CROSS_START, RWY_CROSS_END, 40, "CROSS", "END")
    
    pygame.draw.circle(screen, (0, 200, 0), GATE_1, 8); draw_label(screen, "G1", GATE_1)
    pygame.draw.circle(screen, (0, 200, 0), GATE_2, 8); draw_label(screen, "G2", GATE_2)
    
    pygame.draw.circle(screen, (255, 200, 0), HOLD_SHORT_MAIN, 6); draw_label(screen, "HS 1", HOLD_SHORT_MAIN)
    pygame.draw.circle(screen, (255, 200, 0), HOLD_SHORT_CROSS, 6); draw_label(screen, "HS 2", HOLD_SHORT_CROSS)
    
    pygame.draw.circle(screen, (100, 100, 100), RAMP_CENTER, 10); draw_label(screen, "RAMP", RAMP_CENTER)

# --- AIRCRAFT LOGIC ---
class AircraftState(Enum):
    RAMP = "RAMP"
    TAXI = "TAXI"
    HOLD = "HOLD"
    TAKEOFF = "TAKEOFF"
    DEPARTED = "DEPARTED"

class Aircraft:
    def __init__(self, callsign, start_pos, color):
        self.callsign = callsign
        self.pos = list(start_pos)
        self.target = None
        self.state = AircraftState.RAMP
        self.speed = 0.0
        self.color = color
        self.path = []

    def set_path(self, points):
        self.path = points
        if self.path:
            self.target = self.path.pop(0)
            self.state = AircraftState.TAXI
            self.speed = SPEED_TAXI

    def move(self):
        if not self.target: return
        dx = self.target[0] - self.pos[0]
        dy = self.target[1] - self.pos[1]
        dist = math.sqrt(dx**2 + dy**2)

        if dist < ARRIVAL_THRESHOLD:
            self.pos = list(self.target)
            if self.path:
                self.target = self.path.pop(0)
            else:
                self.target = None
                if self.state == AircraftState.TAXI: self.state = AircraftState.HOLD
                elif self.state == AircraftState.TAKEOFF: self.state = AircraftState.DEPARTED
            return

        step = min(self.speed, dist)
        self.pos[0] += (dx/dist) * step
        self.pos[1] += (dy/dist) * step

    def draw(self, screen):
        pygame.draw.circle(screen, (0,0,0), (int(self.pos[0])+2, int(self.pos[1])+2), 10)
        pygame.draw.circle(screen, self.color, (int(self.pos[0]), int(self.pos[1])), 10)
        draw_label(screen, self.callsign, self.pos)

def main():
    pygame.init()
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption(TITLE)
    clock = pygame.time.Clock()
    
    j1 = Aircraft("J-MAIN-1", GATE_1, (0, 200, 255))
    j2 = Aircraft("J-MAIN-2", (GATE_1[0]+20, GATE_1[1]), (0, 200, 255))
    j3 = Aircraft("J-CROSS-1", GATE_2, (255, 100, 200))
    j4 = Aircraft("J-CROSS-2", (GATE_2[0]+20, GATE_2[1]), (255, 100, 200))
    fleet = [j1, j2, j3, j4]
    
    stage = 0
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: running = False
            
        if stage == 0:
            print("ATC: All aircraft TAXI to Hold Short.")
            j1.set_path([RAMP_CENTER, HOLD_SHORT_MAIN])
            j2.set_path([RAMP_CENTER, (HOLD_SHORT_MAIN[0]-20, HOLD_SHORT_MAIN[1])])
            j3.set_path([RAMP_CENTER, HOLD_SHORT_CROSS])
            j4.set_path([RAMP_CENTER, (HOLD_SHORT_CROSS[0]-20, HOLD_SHORT_CROSS[1])])
            stage = 1
            
        elif stage == 1:
            if j1.state == AircraftState.HOLD and j3.state == AircraftState.HOLD:
                print("ATC: Line Up and Wait.")
                j1.set_path([RWY_MAIN_START])
                j3.set_path([RWY_CROSS_START])
                stage = 2
        
        elif stage == 2:
            if j1.state == AircraftState.HOLD and j3.state == AircraftState.HOLD:
                 print("ATC: Cleared for TAKEOFF.")
                 j1.target = RWY_MAIN_END
                 j1.state = AircraftState.TAKEOFF
                 j1.speed = SPEED_TAKEOFF
                 j3.target = RWY_CROSS_END
                 j3.state = AircraftState.TAKEOFF
                 j3.speed = SPEED_TAKEOFF
                 stage = 3
        
        for p in fleet: p.move()
        screen.fill(COLOR_BG)
        draw_airport(screen)
        for p in fleet: p.draw(screen)
        pygame.display.flip()
        clock.tick(FPS)
    pygame.quit()

if __name__ == "__main__":
    main()
