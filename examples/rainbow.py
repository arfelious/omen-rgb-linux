import time
import math
from omen_keyboard import OmenKeyboard

def rainbow():
    kb = OmenKeyboard()
    
    # Flatten all categories (row_0, numpad, etc.) into a single list of keys
    keys = {}
    for category in kb.key_map.values():
        keys.update(category)
        
    if not keys:
        print("No keys found in key_map!")
        return
        
    sorted_keys = sorted(keys.keys(), key=lambda k: keys[k]["offset"])
    
    print(f"Starting Rainbow on {len(sorted_keys)} keys...")
    
    t = 0
    try:
        while True:
            for i, name in enumerate(sorted_keys):
                # Calculate color based on time and position
                hue = (t + (i / len(sorted_keys))) % 1.0
                
                # Simple HSV to RGB conversion
                def hsv_to_rgb(h, s, v):
                    i = math.floor(h * 6)
                    f = h * 6 - i
                    p = v * (1 - s)
                    q = v * (1 - f * s)
                    t = v * (1 - (1 - f) * s)
                    if i % 6 == 0: return v, t, p
                    if i % 6 == 1: return q, v, p
                    if i % 6 == 2: return p, v, t
                    if i % 6 == 3: return p, q, v
                    if i % 6 == 4: return t, p, v
                    if i % 6 == 5: return v, p, q
                
                r, g, b = hsv_to_rgb(hue, 1.0, 1.0)
                kb.set_key_color(name, int(r * 255), int(g * 255), int(b * 255))
            
            kb.apply()
            t += 0.05
            time.sleep(0.02)
    except KeyboardInterrupt:
        print("\nStopping...")
        kb.set_all(0, 0, 0)
        kb.apply()

if __name__ == "__main__":
    rainbow()
