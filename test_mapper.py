"""
TEST SCRIPT FOR AIRPORT MAPPER
"""
from airport_mapper import AirportMapper
import os

def test_generation():
    print("Initializing Mapper...")
    # Initialize without GUI if possible, or just instantiate
    # pygame.init() and set_mode are in __init__, so it requires a display.
    # We can rely on the fact that we have a dummy display driver or just let it run headless if possible.
    # On this env, it might fail if no display.
    # Let's try.
    
    # Mocking pygame display to avoid window creation issues in headless env if necessary
    # But usually 'dummy' driver works. 
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    
    mapper = AirportMapper("dummy.png")
    
    # Inject Mock Data
    print("Injecting Mock Data...")
    mapper.captured_data = {
        'RWY_MAIN_START': (100, 100),
        'RWY_MAIN_END': (400, 400),
        'RWY_CROSS_START': (100, 400),
        'RWY_CROSS_END': (400, 100),
        'GATE_1': (50, 50),
        'GATE_2': (60, 60),
        'HOLD_SHORT_MAIN': (120, 120),
        'HOLD_SHORT_CROSS': (120, 380),
        'RAMP_CENTER': (50, 250)
    }
    
    # Generate Code
    print("Generating Code...")
    mapper.generate_code()
    
    # Verify File Exists
    if os.path.exists("generated_airport.py"):
        print("SUCCESS: generated_airport.py created.")
    else:
        print("FAILURE: File not created.")
        exit(1)

if __name__ == "__main__":
    test_generation()
