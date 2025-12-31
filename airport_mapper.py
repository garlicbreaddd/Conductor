"""
airport_mapper.py
Interactive Node Placement Tool
Refactored for Integration with Full ATC Simulation
"""
import pygame
import sys

# Configuration
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 800
COLOR_TEXT = (255, 255, 255)
COLOR_POINT = (0, 255, 255)
COLOR_LINE = (50, 50, 50)

# Simplified Wizard Steps (Max ~10 inputs)
WIZARD_STEPS = [
    # 1. Main Runway (The "23")
    {'key': 'RWY23_THRESH', 'desc': 'Click Main Runway START'},
    {'key': 'RWY23_END',    'desc': 'Click Main Runway END'},
    
    # 2. Cross Runway (The "12")
    {'key': 'RWY12_THRESH', 'desc': 'Click Cross Runway START'},
    {'key': 'RWY12_END',    'desc': 'Click Cross Runway END'},
    
    # 3. Ramp & Gates
    {'key': 'RAMP_CENTER',  'desc': 'Click Ramp Center'},
    {'key': 'GATE_1',       'desc': 'Click Gate 1'},
    {'key': 'GATE_2',       'desc': 'Click Gate 2'},
    
    # 4. Taxiway Alpha (Parallel to Main)
    {'key': 'ALPHA_1',      'desc': 'Click Taxiway Alpha START (Near Ramp)'},
    {'key': 'ALPHA_5',      'desc': 'Click Taxiway Alpha END (Far End)'},
    
    # 5. Hold Point
    {'key': 'HOLD_RWY23',   'desc': 'Click Hold Short Point'},
]

class AirportMapper:
    def __init__(self, bg_image=None):
        # Auto-detect Fullscreen Resolution
        pygame.init() # Ensure init to get info
        info = pygame.display.Info()
        self.w = info.current_w
        self.h = info.current_h
        
        self.screen = pygame.display.set_mode((self.w, self.h), pygame.FULLSCREEN)
        pygame.display.set_caption("Setup: Map Your Airport Nodes")
        self.font = pygame.font.SysFont('Arial', 24)
        self.bg_image = bg_image
        self.captured_data = {}
        self.complete = False
        self.step_index = 0
        
        # Clear background behavior
        if not self.bg_image:
            self.bg_surface = pygame.Surface((self.w, self.h))
            self.bg_surface.fill((20, 30, 20)) # Dark Grass
            
            # Draw subtle guide grid
            for x in range(0, self.w, 100):
                 pygame.draw.line(self.bg_surface, (30, 40, 30), (x, 0), (x, self.h))
            for y in range(0, self.h, 100):
                 pygame.draw.line(self.bg_surface, (30, 40, 30), (0, y), (self.w, y))
        else:
            self.bg_surface = pygame.transform.scale(self.bg_image, (self.w, self.h))

    def interpolate_nodes(self):
        """Mathematically generates the missing nodes."""
        import math
        d = self.captured_data
        
        # 1. Runway Intersection
        # Simple Midpoint fallback if line intersection is too complex for now
        # Ideally: Line-Line intersection.
        # Approximation: Average of all 4 runway points
        rx = (d['RWY23_THRESH'][0] + d['RWY23_END'][0] + d['RWY12_THRESH'][0] + d['RWY12_END'][0]) / 4
        ry = (d['RWY23_THRESH'][1] + d['RWY23_END'][1] + d['RWY12_THRESH'][1] + d['RWY12_END'][1]) / 4
        d['RWY_INTERSECT'] = (int(rx), int(ry))
        
        # 2. Taxiway Alpha Internals (2, 3, 4)
        # Interpolate between 1 and 5
        start = d['ALPHA_1']
        end = d['ALPHA_5']
        for i, key in enumerate(['ALPHA_2', 'ALPHA_3', 'ALPHA_4'], 1):
             ratio = i * 0.25 # 0.25, 0.50, 0.75
             nx = start[0] + (end[0] - start[0]) * ratio
             ny = start[1] + (end[1] - start[1]) * ratio
             d[key] = (int(nx), int(ny))
             
        # 3. Taxiway Bravo (Cross Connector)
        # Create Bravo simplified: Just duplicating Alpha nodes or offset
        # For simplicity, let's map Bravo to Alpha nodes slightly offset?
        # No, connecting Alpha 3 to Hold 12.
        # Let's infer BRAVO from RAMP -> RWY 12 logic.
        # Start: Alpha 3. End: Hold 12 (Need to create hold 12 if missing)
        
        # Create Hold 12 (Near Rwy 12 Thresh)
        d['HOLD_RWY12'] = (d['RWY12_THRESH'][0] - 20, d['RWY12_THRESH'][1] + 20)
        
        # BRAVO: Connects Alpha 3 -> Hold 12
        bravo_start = d['ALPHA_3']
        bravo_end = d['HOLD_RWY12']
        mid_x = (bravo_start[0] + bravo_end[0]) / 2
        mid_y = (bravo_start[1] + bravo_end[1]) / 2
        
        d['BRAVO_1'] = (int(bravo_start[0] + 10), int(bravo_start[1] + 10))
        d['BRAVO_2'] = (int(mid_x), int(mid_y))
        d['BRAVO_3'] = (int(bravo_end[0] - 10), int(bravo_end[1] - 10))
        
        # Gate 3 (Duplicate Gate 2)
        d['GATE_3'] = (d['GATE_2'][0] + 50, d['GATE_2'][1])

        return d

    def run(self):
        clock = pygame.time.Clock()
        while not self.complete:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if self.step_index < len(WIZARD_STEPS):
                        step = WIZARD_STEPS[self.step_index]
                        self.captured_data[step['key']] = event.pos
                        print(f"Mapped {step['key']}: {event.pos}")
                        self.step_index += 1
                        
                        if self.step_index >= len(WIZARD_STEPS):
                            self.complete = True
                            # AUTO INTERPOLATE
                            self.captured_data = self.interpolate_nodes()
                            print("Mapping Complete! Autogenerated details.")
            
            # Draw
            self.screen.blit(self.bg_surface, (0, 0))
            
            # Draw mapped points
            for key, pos in self.captured_data.items():
                color = (0, 255, 0) if "GATE" in key else (0, 255, 255)
                if "RWY" in key: color = (255, 100, 255)
                pygame.draw.circle(self.screen, color, pos, 5)
                
                # Label
                lbl = self.font.render(key, True, (200, 200, 200))
                self.screen.blit(lbl, (pos[0]+10, pos[1]-10))

                # Helper lines
                keys = list(self.captured_data.keys())
                ix = keys.index(key)
                if ix > 0:
                     pygame.draw.line(self.screen, (50, 50, 50), self.captured_data[keys[ix-1]], pos, 1)

            # Overlay instruction
            if self.step_index < len(WIZARD_STEPS):
                instr = WIZARD_STEPS[self.step_index]['desc']
                # Semi-transparent box
                box = pygame.Surface((self.w, 60))
                box.set_alpha(200)
                box.fill((0, 0, 0))
                self.screen.blit(box, (0, 0))
                
                txt = self.font.render(f"STEP {self.step_index + 1}/{len(WIZARD_STEPS)}: {instr}", True, (255, 255, 0))
                self.screen.blit(txt, (20, 15))
            
            pygame.display.flip()
            clock.tick(60)
            
        return self.captured_data

if __name__ == "__main__":
    pygame.init()
    m = AirportMapper()
    data = m.run()
    print("Final Data:", data)
    pygame.quit()
