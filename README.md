# Live Overflow – Setup & Controls

## Dependencies
- Python libraries:
  - `pygame`
  - `opencv-python`
  - `mido`
- Recommended environment:
  - Linux (tested on **Arch Linux** and **Ubuntu Studio**)

---

## Audio Reactivity Setup

1. Run mixxx in developer mode:
```bash
mixxx --developer
```

2. In Mixxx:
- Select MIDI Through Port-0 in preferences
- Enable "MIDI for light" mapping
- This mapping sends (via midi):
  - BPM
  - Deck changes
  - Beat detection
  - Average mono volume

## Xbox Controller (Live VJ Controls)

Works even if the Pygame window is out of focus.

# Video Input
  - Start: Next video bank
  - Select: Previous video bank
  - D-Left: Previous video in bank
  - D-Right: Next video in bank
  - LT: Toggle framerate (15-30 FPS)
# Filters
  - D-Up: Previous filter
  - D-Down: Next filter
  - A: Toggle beat-based filter switching
  - Left Stick (LS)
    - LSY: Brightness
    - LSX: Contrast
# Visual Meta Modes
  - X: Toggle blending
  - Y: Toggle overflow
  - RSB: Increment RGB channel roll
  - B: Toggle beat-based RGB roll
  - Right Stick (RS): Change RGB roll via angle (every 60°)
  - RT: Adjust audio reactivity factor (1–32)/32

## Keyboard Controls

Only works when Pygame window is in focus.

# Video Input
  - Tab: Next video bank (loops to 0)
  - Shift: Previous video in bank
  - Ctrl: Next video in bank
  - [: Decrease framerate
  - ]: Increase framerate
  - =: Reset framerate to 15 FPS
# Filters
  - Q: Previous IP chain mode
  - A: Next IP chain mode
  - S: Toggle beat-based filter switching
# Visual Meta Modes
  - W: Toggle blending
  - O: Toggle overflow
  - X: Increment RGB channel roll
  - D: Toggle beat-based RGB roll
# Audio Reactivity
  - Z: Toggle audio reactivity
  - ;: Decrease audio reactivity factor
  - ': Increase audio reactivity factor
  - /: Reset to lowest factor
# Exit
  - Esc: Quit application

## How to Run
# Add your media:
  - Place videos inside a videos/ folder
  - Register them in the config file
  - Add camera indices in the "cameras" section
  - Add/modify filters as needed in the filters.py file

# Run the app:

```bash
python main_mp.py
```

Start Mixxx in dev mode for audio reactivity:

```bash
mixxx --developer
```

Closing the Pygame window should terminate the app. If it hangs, force quit with Ctrl + C.