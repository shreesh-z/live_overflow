# Python dependencies:
Pygame, OpenCV, mido. Preferably run it in linux.
Tested only on arch linux & ubuntu studio.

# For audio reactivity:
Run mixxx in developer mode and use the "MIDI for light" mapping on the Midi through port-0 in preferences. Run mixxx as "mixxx --developer" in the terminal for dev mode.
This mapping will report current bpm, deck change, beat detection and average mono volume thru midi.

# For live VJ'ing:
Connect an xbox controller. This will run as a controller even if pg window is out of focus.
    For Video Input:
        Start  : go to next video bank
        Select : go to prev video bank
        DLeft  : go to prev video inside a given bank
        DRight : go to next video inside a given bank
        LT     : change framerate between 15-30fps
    For filters:
        DUp : prev filter
        DDn : next filter
        A   : toggle filter change based on midi beat detection
        LS  : Change brightness (LSY) and contrast (LSX)
    Visuals meta-modes:
        X   : toggle blending
        Y   : toggle overflow
        RSB : rgb channel roll increment
        B   : toggle rgb channel roll based on midi beat detection
        RS  : Change channel roll based on stick angle (every 60 degrees)
	    RT  : change audio reactivity factor between (1-32)/32

Keyboard controls (won't run asynchronously if pygame window not in focus):
    For video input
        tab  : increment video bank (rolls back to 0)
        shft : go to prev video inside a given bank
        ctrl : go to next video inside a given bank
        [    : decrease framerate
        ]    : increase framerate
        =    : reset framerate to 15
    For filters:
        q  : ip chain mode back
        a  : ip chain mode front
        s  : toggle filter change based on midi beat detection
    Visuals meta-modes:
        w  : toggle blending
        o  : toggle overflow
        x  : rgb channel roll increment
        d  : toggle rgb channel roll based on midi beat detection
    Audio reactivity related
        z  : toggle audio reactivity
        ;  : reduce audio reactivity factor
        '  : increase audio reactivity factor
        /  : reset audio reactivity to lowest factor
    
    esc  : quit

# How to run
Load your own videos into a folder named "videos", add their references in the config file.
Add camera numbers to the "cameras" section.
Add your own filters on top of the placeholder filters.

Run "python main_mp.py" in the terminal.
Run mixxx in dev mode (as mentioned above) to get audio reactivity.
Closing the pygame window closes the app. If not fully closed, use ctrl+C.