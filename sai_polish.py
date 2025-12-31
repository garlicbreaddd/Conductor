"""
sai_polish.py
Phase 4: sAI Polish & Human Factors
Includes Thought Bubble UI, Weather, and Pilot Verification Logic
"""
import pygame
import random
import time

# --- 1. THOUGHT BUBBLE UI (The "Brain Scan") ---
class ThoughtBubble:
    def __init__(self, x, y, width, height, font):
        self.rect = pygame.Rect(x, y, width, height)
        self.font = font
        self.logs = [] # List of (text, color, timestamp)
        self.surface = pygame.Surface((width, height), pygame.SRCALPHA)
        self.surface.fill((0, 0, 0, 180)) # Translucent black
        
    def log(self, text, level="INFO"):
        """
        Pushes a thought to the display.
        Level: INFO (White), CALC (Blue), WARNING (Red)
        """
        color = (255, 255, 255) # INFO
        if level == "CALC":
            color = (100, 200, 255) # Blue
        elif level == "WARNING":
            color = (255, 50, 50) # Red
            
        timestamp = time.strftime("%H:%M:%S")
        print(f"[sAI {level}] {text}") # Console Mirror
        entry = (f"[{timestamp}] {text}", color, time.time())
        self.logs.append(entry)
        
        # Keep last 15 logs
        if len(self.logs) > 15:
            self.logs.pop(0)
            
    def draw(self, screen):
        # Refresh background
        self.surface.fill((0, 0, 0, 180))
        
        y_offset = 10
        for text, color, _ in self.logs:
            lbl = self.font.render(text, True, color)
            self.surface.blit(lbl, (10, y_offset))
            y_offset += 20
            
        screen.blit(self.surface, self.rect)

# --- 2. ENVIRONMENT MONITOR (The "Gale Force" Test) ---
class WeatherStation:
    def __init__(self):
        self.wind_speed = 10 # Knots
        self.last_update = time.time()
        
    def update(self):
        """Randomly changes wind every 30 seconds"""
        if time.time() - self.last_update > 30:
            self.wind_speed = random.randint(0, 30)
            self.last_update = time.time()
            return True # Changed
        return False
        
    def force_wind(self, speed):
        """For testing"""
        self.wind_speed = speed
        
    def check_constraints(self, aircraft_type):
        """
        Returns (Allowed: bool, Reason: str)
        Rule: Cessna grounded if wind > 20 knots
        """
        if aircraft_type.upper() == "CESSNA" and self.wind_speed > 20:
            return False, f"Wind {self.wind_speed}kt > 20kt Limit"
        return True, "OK"

# --- 3. HUMAN FACTORS (The "Bad Pilot" Test) ---
class PilotAgent:
    def __init__(self, callsign, confusion_rate=0.1):
        """
        confusion_rate: 0.0 to 1.0 (Default 10% chance of error)
        """
        self.callsign = callsign
        self.confusion_rate = confusion_rate
        
    def readback(self, instructions):
        """
        Simulates pilot response. Occasionally gets runway wrong.
        instructions: "Taxi to Runway 23"
        """
        if random.random() < self.confusion_rate:
            # Generate ERROR response
            # e.g., Swap 23 with 05
            if "23" in instructions:
                return instructions.replace("23", "05") + " [READBACK ERROR]"
            elif "12" in instructions:
                return instructions.replace("12", "30") + " [READBACK ERROR]"
            else:
                return instructions + " ...uh..."
        
        return instructions # Correct readback

class ReadbackVerifier:
    @staticmethod
    def verify(issued, received):
        """
        Returns True if matched, False if mismatch
        """
        # Simple cleanup
        clean_issued = issued.replace(" ", "").upper()
        clean_received = received.replace(" ", "").upper()
        clean_received = clean_received.replace("[READBACKERROR]", "") # Remove debug tag
        
        # Check for core Numbers (runway IDs)
        # Verify 23 vs 05
        if "23" in clean_issued and "23" not in clean_received:
            return False
            
        return True
