import random
import time
import datetime
from dataclasses import dataclass
from typing import List, Dict, Optional

# --- Data Structures ---

@dataclass
class Aircraft:
    callsign: str
    weight_class: str  # "Super", "Heavy", "Large", "Small"
    status: str        # "Inbound", "Outbound", "Taxiing"
    location: str      # "Runway 1", "Gate A1", etc.

@dataclass
class WeatherData:
    timestamp: datetime.datetime
    wind_speed_knots: float
    wind_direction_deg: int
    visibility_miles: float
    temperature_c: float
    precipitation: str # "None", "Rain", "Snow", "Fog"

@dataclass
class PilotUpdate:
    callsign: str
    message: str
    timestamp: datetime.datetime
    priority: str # "Normal", "High", "Critical"

# --- Modules ---

class WeatherSystem:
    def __init__(self):
        self.current_weather = self._generate_initial_weather()

    def _generate_initial_weather(self) -> WeatherData:
        return WeatherData(
            timestamp=datetime.datetime.now(),
            wind_speed_knots=5.0,
            wind_direction_deg=180,
            visibility_miles=10.0,
            temperature_c=25.0,
            precipitation="None"
        )

    def update(self) -> WeatherData:
        # Simulate slight changes in weather
        w = self.current_weather
        w.timestamp = datetime.datetime.now()
        w.wind_speed_knots = max(0, w.wind_speed_knots + random.uniform(-2, 2))
        w.wind_direction_deg = (w.wind_direction_deg + random.randint(-10, 10)) % 360
        w.visibility_miles = max(0.1, min(10.0, w.visibility_miles + random.uniform(-0.5, 0.5)))
        w.temperature_c = w.temperature_c + random.uniform(-0.5, 0.5)
        
        # Random chance for precip change
        if random.random() < 0.05:
            w.precipitation = random.choice(["None", "Rain", "Fog"])
            
        self.current_weather = w
        return w
    
    def get_weather(self) -> WeatherData:
        return self.current_weather

class WakeTurbulenceManager:
    # Separation matrix (leading_weight -> following_weight: separation_miles)
    # Simplified standard ICAO/FAA based values for demo
    SEPARATION_MATRIX = {
        "Super": {"Super": 2.5, "Heavy": 6.0, "Large": 7.0, "Small": 8.0},
        "Heavy": {"Super": 2.5, "Heavy": 4.0, "Large": 5.0, "Small": 5.0},
        "Large": {"Super": 2.5, "Heavy": 2.5, "Large": 2.5, "Small": 4.0},
        "Small": {"Super": 2.5, "Heavy": 2.5, "Large": 2.5, "Small": 2.5}
    }

    def calculate_separation(self, leader: Aircraft, follower: Aircraft) -> float:
        leader_cls = leader.weight_class
        follower_cls = follower.weight_class
        
        # Default fallback
        if leader_cls not in self.SEPARATION_MATRIX: return 3.0 
        
        required_dist = self.SEPARATION_MATRIX.get(leader_cls, {}).get(follower_cls, 3.0)
        return required_dist

class SafetyPredictorML:
    """
    Mock ML model to predict safety score based on weather.
    """
    def predict_safety_score(self, weather: WeatherData) -> float:
        # Logic: High wind + Low Vis + Rain = Low Safety Score (0.0 to 1.0)
        score = 1.0
        
        if weather.wind_speed_knots > 20: score -= 0.3
        if weather.wind_speed_knots > 35: score -= 0.5
        
        if weather.visibility_miles < 3.0: score -= 0.2
        if weather.visibility_miles < 1.0: score -= 0.4
        
        if weather.precipitation == "Rain": score -= 0.1
        if weather.precipitation == "Snow": score -= 0.2
        if weather.precipitation == "Fog": score -= 0.3
        
        return max(0.0, score)

class EnvironmentMonitor:
    def __init__(self):
        self.weather_sys = WeatherSystem()
        self.wake_mgr = WakeTurbulenceManager()
        self.ml_predictor = SafetyPredictorML()
        
    def generate_pilot_update(self, aircraft: Aircraft, leader: Optional[Aircraft] = None) -> List[PilotUpdate]:
        updates = []
        current_weather = self.weather_sys.get_weather()
        safety_score = self.ml_predictor.predict_safety_score(current_weather)
        
        # 1. Weather Update
        wx_msg = (f"Wind {current_weather.wind_direction_deg:03d}@{current_weather.wind_speed_knots:.1f}kt, "
                  f"Vis {current_weather.visibility_miles:.1f}sm, {current_weather.precipitation}. "
                  f"Safety Index: {safety_score:.2f}")
        
        prio = "Normal"
        if safety_score < 0.5: prio = "High"
        if safety_score < 0.2: prio = "Critical"
        
        updates.append(PilotUpdate(
            callsign=aircraft.callsign,
            message=f"WEATHER UPDATE: {wx_msg}",
            timestamp=datetime.datetime.now(),
            priority=prio
        ))
        
        # 2. Wake Turbulence
        if leader and aircraft.status == "Outbound":
            sep = self.wake_mgr.calculate_separation(leader, aircraft)
            updates.append(PilotUpdate(
                callsign=aircraft.callsign,
                message=f"CAUTION WAKE TURBULENCE: Departing behind {leader.weight_class} {leader.callsign}. Maintain {sep}nm separation.",
                timestamp=datetime.datetime.now(),
                priority="High"
            ))
            
        return updates

# --- Simulation Logic ---


def format_custom_timestamp(dt: datetime.datetime) -> str:
    # Format: 12/29/25 - 12:47:52:30
    # MS is 2 digits here based on user example
    ms = int(dt.microsecond / 10000)
    return dt.strftime(f"%m/%d/%y - %H:%M:%S:{ms:02d}")

def run_simulation():
    monitor = EnvironmentMonitor()
    
    # Mock Traffic
    schedule = [
        Aircraft("UA882", "Heavy", "Outbound", "Runway 27L"),
        Aircraft("DL123", "Large", "Outbound", "Taxiway B"), 
        Aircraft("AA445", "Small", "Inbound", "Final Approach"),
        Aircraft("LH456", "Super", "Outbound", "Runway 27L")
    ]
    
    print("--- STARTING ENVIRONMENTAL MONITOR SIMULATION ---")
    print("--- Location: Leesburg Private Hangar, Northern Virginia ---\n")
    
    for i in range(10): # increased iterations since it's faster
        current_time = datetime.datetime.now()
        ts_str = format_custom_timestamp(current_time)
        print(f"\n[{ts_str}] Updating Environment (Leesburg Private Hangar)...")
        monitor.weather_sys.update()
        
        # Simulate processing each aircraft
        last_outbound = None
        
        for ac in schedule:
            # For demo, assume sequential departures on same runway for wake calc
            updates = monitor.generate_pilot_update(ac, leader=last_outbound if ac.status == "Outbound" else None)
            
            for u in updates:
                prefix = ""
                if u.priority == "High": prefix = "⚠️  "
                if u.priority == "Critical": prefix = "🛑 "
                
                # In real output we might want the timestamp on the message too
                print(f"To {u.callsign}: {prefix}{u.message}")
            
            if ac.status == "Outbound":
                last_outbound = ac
                
        time.sleep(0.5) # Update every 0.5 seconds

if __name__ == "__main__":
    run_simulation()
