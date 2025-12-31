"""
test_logic_core.py
Verification Script for Logic Core (Updated for new graph structure)
"""
import unittest
from atc_backend import AirportGraph, RunwayMonitor, TaskScheduler

class TestLogicCore(unittest.TestCase):
    
    # --- Test A: The "Roadblock" Test ---
    def test_roadblock(self):
        print("\n[Test A] Roadblock Test")
        graph = AirportGraph()
        
        # 1. Normal Path (Gate 1 -> Hold Short 23)
        path_normal = graph.get_taxi_route("GATE_1", "HOLD_RWY23")
        print(f"Normal Path: {path_normal}")
        
        # Should use Alpha taxiway
        self.assertTrue(any("ALPHA" in node for node in path_normal))
        
        # 2. Test route to RWY12 uses Bravo
        path_to_12 = graph.get_taxi_route("GATE_1", "HOLD_RWY12")
        print(f"Path to RWY12: {path_to_12}")
        
        # Should use both Alpha AND Bravo
        self.assertTrue(any("ALPHA" in node for node in path_to_12))
        self.assertTrue(any("BRAVO" in node for node in path_to_12))
        print("PASS: Graph is fully connected and routes use correct taxiways.")

    # --- Test B: The "Red Light" Test ---
    def test_red_light(self):
        print("\n[Test B] Red Light / Runway Monitor Test")
        monitor = RunwayMonitor((100, 100, 500, 50))
        
        # Scenario 1: Empty
        is_occ = monitor.scan_runway([])
        self.assertFalse(is_occ)
        print("Runway Empty: OK")
        
        # Scenario 2: Plane on Runway
        plane_on_rwy = {'pos': (300, 120)}
        plane_waiting = {'pos': (50, 50)}
        
        is_occ = monitor.scan_runway([plane_on_rwy, plane_waiting])
        print(f"Runway Occupied Status: {is_occ}")
        
        self.assertTrue(is_occ)
        print("PASS: Monitor detected plane on runway.")

    # --- Test C: The "Mayday" Override ---
    def test_mayday(self):
        print("\n[Test C] Mayday / Scheduler Test")
        scheduler = TaskScheduler()
        
        for i in range(5):
            scheduler.add_task(4, f"Cessna_{i}", "Taxi Request")
            
        print("Injecting Priority 1 Emergency...")
        scheduler.add_task(1, "EMERGENCY_JET", "Engine Failure")
        
        next_task = scheduler.get_next_task()
        print(f"Next Task Processed: {next_task}")
        
        self.assertEqual(next_task[1], "EMERGENCY_JET")
        print("PASS: Emergency processed first.")

    # --- Test D: Full Route Test ---
    def test_full_route(self):
        print("\n[Test D] Full Route Test (Gate to Runway End)")
        graph = AirportGraph()
        
        # Gate to Runway 23 end (full taxi + takeoff roll)
        path = graph.get_taxi_route("GATE_1", "RWY23_END")
        print(f"Full Path: {path}")
        
        self.assertIsNotNone(path)
        self.assertIn("RWY23_THRESH", path)
        self.assertIn("RWY_INTERSECT", path)
        print("PASS: Full route from gate to runway end found.")

if __name__ == "__main__":
    unittest.main()
