"""
dashboard_ui.py
Phase 5: Human-Assistive Dashboard
Split-screen layout with Flight Strips, Comms Log, and Human Override
"""
import pygame
import time
import random
import hashlib

# --- 1. FLIGHT STRIP DISPLAY (Right Panel) ---
class FlightStripDisplay:
    def __init__(self, x, y, width, height, font):
        self.rect = pygame.Rect(x, y, width, height)
        self.font = font
        self.strips = []  # List of dicts: {callsign, type, status, intention, direction}
        self.surface = pygame.Surface((width, height), pygame.SRCALPHA)
        
    def update_strip(self, callsign, aircraft_type, status, intention, direction="OUT"):
        """
        Updates or adds a flight strip.
        direction: "IN" (Inbound/Green), "OUT" (Outbound/Blue), "EMERG" (Red)
        """
        for strip in self.strips:
            if strip['callsign'] == callsign:
                strip['type'] = aircraft_type
                strip['status'] = status
                strip['intention'] = intention
                strip['direction'] = direction
                return
        # New strip
        self.strips.append({
            'callsign': callsign,
            'type': aircraft_type,
            'status': status,
            'intention': intention,
            'direction': direction
        })
        
    def draw(self, screen):
        self.surface.fill((20, 20, 30, 220))  # Dark translucent
        
        y_offset = 10
        strip_height = 80
        
        for strip in self.strips[:6]:  # Max 6 strips visible
            # Color based on direction
            if strip['direction'] == "IN":
                color = (50, 200, 100)  # Green
            elif strip['direction'] == "EMERG":
                color = (255, 80, 80)  # Red
            else:
                color = (100, 150, 255)  # Blue (Outbound)
            
            # Draw strip background
            strip_rect = pygame.Rect(5, y_offset, self.rect.width - 10, strip_height - 5)
            pygame.draw.rect(self.surface, color, strip_rect, border_radius=5)
            pygame.draw.rect(self.surface, (255, 255, 255), strip_rect, 2, border_radius=5)
            
            # Text
            cs_txt = self.font.render(strip['callsign'], True, (255, 255, 255))
            type_txt = self.font.render(strip['type'], True, (200, 200, 200))
            status_txt = self.font.render(strip['status'], True, (255, 255, 255))
            intent_txt = self.font.render(f"→ {strip['intention']}", True, (255, 255, 150))
            
            self.surface.blit(cs_txt, (10, y_offset + 5))
            self.surface.blit(type_txt, (120, y_offset + 5))
            self.surface.blit(status_txt, (10, y_offset + 25))
            self.surface.blit(intent_txt, (10, y_offset + 45))
            
            y_offset += strip_height
        
        screen.blit(self.surface, self.rect)

# --- 2. COMMS LOG (Bottom Panel) ---
class CommsLog:
    def __init__(self, x, y, width, height, font):
        self.rect = pygame.Rect(x, y, width, height)
        self.font = font
        self.messages = []  # List of (freq, callsign, text, is_ai)
        self.surface = pygame.Surface((width, height), pygame.SRCALPHA)
        
    def log(self, freq, callsign, text, is_ai=False):
        """Logs a radio message."""
        timestamp = time.strftime("%H:%M:%S")
        entry = (freq, callsign, text, is_ai, timestamp)
        self.messages.append(entry)
        print(f"[RADIO {freq}] [{callsign}]: {text}")
        
        # Keep last 5
        if len(self.messages) > 5:
            self.messages.pop(0)
            
    def draw(self, screen, human_override_active=False):
        self.surface.fill((10, 10, 20, 200))
        
        # Override indicator
        if human_override_active:
            pygame.draw.rect(self.surface, (255, 50, 50), (0, 0, self.rect.width, 25))
            tx_txt = self.font.render("*** HUMAN TRANSMITTING ***", True, (255, 255, 255))
            self.surface.blit(tx_txt, (10, 5))
            y_offset = 30
        else:
            y_offset = 5
        
        for freq, callsign, text, is_ai, ts in self.messages:
            if is_ai:
                color = (100, 200, 255)  # AI = Blue
                prefix = "[AI ATC]"
            else:
                color = (255, 255, 255)  # Human/Pilot = White
                prefix = f"[{callsign}]"
            
            line = f"[{freq}] {prefix}: \"{text}\""
            lbl = self.font.render(line, True, color)
            self.surface.blit(lbl, (10, y_offset))
            y_offset += 18
            
        screen.blit(self.surface, self.rect)

# --- 3. HUMAN OVERRIDE ---
class HumanOverride:
    def __init__(self):
        self.active = False
        self.last_transcript = None
        
    def start(self):
        self.active = True
        print("[OVERRIDE] Human transmitting...")
        
    def stop(self, transcript=None):
        self.active = False
        self.last_transcript = transcript
        if transcript:
            print(f"[OVERRIDE] Human said: {transcript}")
        
    def get_last_command(self):
        cmd = self.last_transcript
        self.last_transcript = None
        return cmd

# --- 5. STATUS PINGER (Bottom Right) ---
class StatusPinger:
    def __init__(self, x, y, font):
        self.x = x
        self.y = y
        self.font = font
        self.last_update_time = 0
        self.current_text = "System Ready"
        self.pending_text = None
        self.color = (0, 255, 100) # Matrix Green
        
    def push_status(self, text):
        """Queue a status update."""
        self.pending_text = text
        
    def update(self, current_time):
        """Updates display every 0.5s (500ms)."""
        if current_time - self.last_update_time > 500:
            if self.pending_text:
                self.current_text = f"[{time.strftime('%H:%M:%S')}] {self.pending_text}"
                self.pending_text = None # Clear queue
            else:
                # If no idle text, maybe just keep old one or show heartbeat
                # self.current_text = f"[{time.strftime('%H:%M:%S')}] Nominal"
                pass 
            self.last_update_time = current_time
            
    def draw(self, screen):
        # Draw background pill
        text_surf = self.font.render(self.current_text, True, self.color)
        bg_rect = pygame.Rect(self.x, self.y, text_surf.get_width() + 20, 30)
        # Right align logic: x passed should be the right edge? Or top-left?
        # Let's assume x,y is top-left.
        
        pygame.draw.rect(screen, (0, 20, 0, 200), bg_rect, border_radius=5)
        pygame.draw.rect(screen, self.color, bg_rect, 1, border_radius=5)
        screen.blit(text_surf, (self.x + 10, self.y + 5))

# --- 4. VOICE VARIETY ---
class VoiceProfile:
    """Assigns consistent voice settings per callsign."""
    
    def __init__(self):
        self.profiles = {}  # callsign -> {rate, pitch, voice_id}
        
    def get_profile(self, callsign, aircraft_type=""):
        """Returns TTS settings for a callsign."""
        if callsign in self.profiles:
            return self.profiles[callsign]
        
        # Generate deterministic profile from callsign hash
        h = int(hashlib.md5(callsign.encode()).hexdigest(), 16)
        
        # Base rate/pitch on aircraft type
        if "HEAVY" in aircraft_type.upper() or "B7" in aircraft_type.upper():
            rate = 120 + (h % 20)  # Slow
            pitch = 80 + (h % 30)  # Deep
        elif "CESSNA" in aircraft_type.upper() or "C1" in aircraft_type.upper():
            rate = 170 + (h % 30)  # Fast
            pitch = 130 + (h % 40)  # Higher
        else:
            rate = 150 + (h % 20)  # Standard
            pitch = 100 + (h % 30)
        
        profile = {'rate': rate, 'pitch': pitch, 'voice_id': h % 3}
        self.profiles[callsign] = profile
        return profile

# --- TESTING ---
if __name__ == "__main__":
    pygame.init()
    screen = pygame.display.set_mode((1200, 800))
    pygame.display.set_caption("Dashboard UI Test")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont('Arial', 14)
    
    # Init components
    strips = FlightStripDisplay(900, 10, 290, 500, font)
    comms = CommsLog(10, 700, 880, 90, font)
    override = HumanOverride()
    voices = VoiceProfile()
    
    # Sample data
    strips.update_strip("N172SP", "C172", "Taxiing", "Hold Short A", "OUT")
    strips.update_strip("UAL123", "B737", "Inbound", "Runway 23", "IN")
    strips.update_strip("EMERG1", "B737", "MAYDAY", "Priority Landing", "EMERG")
    
    comms.log("124.6", "N172SP", "Request taxi runway 23")
    comms.log("124.6", "AI ATC", "N172SP taxi via Alpha", is_ai=True)
    
    print(f"Voice Profile N172SP: {voices.get_profile('N172SP', 'C172')}")
    print(f"Voice Profile UAL123: {voices.get_profile('UAL123', 'B737')}")
    
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
        
        keys = pygame.key.get_pressed()
        if keys[pygame.K_SPACE]:
            if not override.active:
                override.start()
        else:
            if override.active:
                override.stop("Test override command")
        
        screen.fill((30, 30, 40))
        strips.draw(screen)
        comms.draw(screen, override.active)
        
        pygame.display.flip()
        clock.tick(60)
    
    pygame.quit()
