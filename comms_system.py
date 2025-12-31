"""
comms_system.py
Phase 3: Communications Layer
Handles Pilot-ATC voice/radio interaction
"""
import re
import random
import threading
import time

# Try to import voice libraries (graceful degradation if not available)
try:
    import pyttsx3
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False
    print("[COMMS] Warning: pyttsx3 not available. TTS disabled.")

try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    SR_AVAILABLE = False
    print("[COMMS] Warning: speech_recognition not available. Using mock input.")

# --- 1. RADIO CHANNEL (Interference Simulation) ---
class RadioChannel:
    def __init__(self, signal_quality=1.0):
        """
        signal_quality: 0.0 (worst) to 1.0 (perfect)
        """
        self.signal_quality = signal_quality
    
    def transmit(self, message):
        """
        Simulates radio transmission with potential interference.
        Returns distorted message or None if signal too weak.
        """
        if self.signal_quality < 0.5:
            # Signal too weak - message dropped
            return None
        
        if self.signal_quality < 0.8:
            # Moderate interference - add static
            words = message.split()
            distorted = []
            for word in words:
                if random.random() > self.signal_quality:
                    distorted.append("[static]")
                else:
                    distorted.append(word)
            return " ".join(distorted)
        
        # Good signal
        return message

# --- 2. COMMAND PARSER (NLP) ---
class CommandParser:
    def __init__(self):
        # Regex patterns for command extraction
        # Supports:
        # 1. N-Numbers (N172SP, N123)
        # 2. Airline/Military styles (Beta 123, Delta 454)
        self.callsign_pattern = r'\b([N][0-9]{1,5}[A-Z]{0,2}|[A-Z]+[ \-]?[0-9]+)\b'
        
        # Intent patterns
        self.intent_patterns = {
            'request_taxi': r'\b(taxi|taxiing|ready to taxi)\b',
            'request_takeoff': r'\b(takeoff|take off|ready for takeoff|cleared for takeoff)\b',
            'request_landing': r'\b(land|landing|inbound|approach)\b',
            'emergency': r'\b(emergency|mayday|pan pan|7700)\b'
        }
        
        # Priority mapping
        self.priority_map = {
            'emergency': 1,
            'request_landing': 2,
            'request_takeoff': 3,
            'request_taxi': 4
        }
    
    def parse(self, text):
        """
        Extracts structured command from pilot transmission.
        Returns dict or error string.
        """
        if not text or text == "[static]":
            return "SAY_AGAIN"
        
        text_lower = text.lower()
        
        # Extract callsign (Case insensitive search)
        callsign_match = re.search(self.callsign_pattern, text, re.IGNORECASE)
        callsign = callsign_match.group(1).upper() if callsign_match else None
        
        # Extract intent
        intent = None
        for action, pattern in self.intent_patterns.items():
            if re.search(pattern, text_lower):
                intent = action
                break
        
        # Debugging / Feedback for user
        if not callsign or not intent:
            if not callsign:
                # If we have intent but no callsign, maybe say "Aircraft calling [Action]..."
                return "MISSING_CALLSIGN"
            if not intent:
                return "MISSING_INTENT"
            return "SAY_AGAIN"
        
        # Build structured command
        return {
            'callsign': callsign,
            'action': intent,
            'priority': self.priority_map.get(intent, 4),
            'raw_text': text
        }

# --- 3. VOICE I/O SYSTEM ---
class VoiceIO:
    def __init__(self):
        self.tts_engine = None
        self.recognizer = None
        self.microphone = None
        
        # Initialize TTS
        if TTS_AVAILABLE:
            try:
                self.tts_engine = pyttsx3.init()
                self.tts_engine.setProperty('rate', 150)  # Slower for clarity
            except Exception as e:
                print(f"[COMMS] TTS initialization failed: {e}")
        
        # Initialize Speech Recognition
        if SR_AVAILABLE:
            try:
                self.recognizer = sr.Recognizer()
                # Microphone requires pyaudio - now available
                self.microphone = sr.Microphone()
            except Exception as e:
                print(f"[COMMS] SR initialization failed: {e}")
    
    def speak(self, text):
        """ATC speaks to pilot via TTS"""
        print(f"[ATC RADIO] {text}")
        if self.tts_engine:
            try:
                self.tts_engine.say(text)
                self.tts_engine.runAndWait()
            except Exception as e:
                print(f"[COMMS] TTS error: {e}")
    
    def listen_mock(self, prompt="Pilot:"):
        """
        Mock listener for testing without microphone.
        Returns text input from console.
        """
        return input(f"{prompt} ")
    
    def listen_threaded(self, callback, duration=5):
        """
        Non-blocking listener (runs in thread).
        Calls callback(text) when speech detected.
        """
        def listen_worker():
            if self.recognizer and self.microphone:
                try:
                    with self.microphone as source:
                        print("[COMMS] Listening...")
                        audio = self.recognizer.listen(source, timeout=duration)
                        text = self.recognizer.recognize_google(audio)
                        callback(text)
                except sr.WaitTimeoutError:
                    print("[COMMS] No speech detected")
                except Exception as e:
                    print(f"[COMMS] Listen error: {e}")
            else:
                # Fallback to mock
                text = self.listen_mock()
                callback(text)
        
        thread = threading.Thread(target=listen_worker, daemon=True)
        thread.start()

# --- 4. INTEGRATED COMMS SYSTEM ---
class CommsSystem:
    def __init__(self, scheduler, signal_quality=1.0):
        """
        scheduler: TaskScheduler from Phase 2
        """
        self.radio = RadioChannel(signal_quality)
        self.parser = CommandParser()
        self.voice = VoiceIO()
        self.scheduler = scheduler
        self.listening = False
    
    def process_pilot_message(self, raw_text):
        """
        Full pipeline: Radio -> Parser -> Scheduler
        """
        # 1. Simulate radio transmission
        received = self.radio.transmit(raw_text)
        
        if received is None:
            self.voice.speak("Station calling, signal unreadable, say again.")
            return None
        
        # 2. Parse command
        result = self.parser.parse(received)
        
        # Handle parsing errors (Strings)
        if isinstance(result, str):
            if result == "MISSING_CALLSIGN":
                 self.voice.speak("Station calling, callsign not recognized.")
            elif result == "MISSING_INTENT":
                 self.voice.speak("Station calling, verify intentions.")
            else:
                 self.voice.speak("Station calling, say again your last transmission.")
            return None
        
        # 3. Add to scheduler
        self.scheduler.add_task(
            result['priority'],
            result['callsign'],
            result['action']
        )
        
        # 4. Acknowledge
        ack_msg = f"{result['callsign']}, roger, {result['action'].replace('request_', '')} request received."
        self.voice.speak(ack_msg)
        
        return result
    
    def start_listening(self, callback=None):
        """
        Start non-blocking listener.
        callback: optional function to call with parsed command
        """
        def on_speech(text):
            result = self.process_pilot_message(text)
            if callback and result:
                callback(result)
        
        self.listening = True
        self.voice.listen_threaded(on_speech)

# --- TESTING HELPERS ---
if __name__ == "__main__":
    print("--- Communications System Test ---")
    
    # Mock scheduler for testing
    class MockScheduler:
        def add_task(self, priority, aircraft_id, request):
            print(f"[SCHEDULER] Added: P{priority} - {aircraft_id} - {request}")
    
    scheduler = MockScheduler()
    
    # Test A: Static Test (Low Signal)
    print("\n[Test A] Static Test (signal_quality=0.4)")
    comms_low = CommsSystem(scheduler, signal_quality=0.4)
    comms_low.process_pilot_message("November 123 requesting taxi")
    
    # Test B: NLP Test (Perfect Signal)
    print("\n[Test B] NLP Test (signal_quality=1.0)")
    comms_good = CommsSystem(scheduler, signal_quality=1.0)
    comms_good.process_pilot_message("Tower, this is N172SP, we are ready for takeoff")
    
    # Test C: Interactive Mock Test
    print("\n[Test C] Interactive Test")
    print("Type a pilot transmission (or 'quit' to exit):")
    while True:
        text = input("Pilot: ")
        if text.lower() == 'quit':
            break
        comms_good.process_pilot_message(text)
