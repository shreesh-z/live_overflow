"""
controller_mapper.py

A small pygame 2 module that maps Xbox-style controller inputs to callback
functions and keeps track of:

- pressed / released button states
- current axis values
- current dpad / hat values
- mapping state
- mapped callback functions

Designed around pygame._sdl2.controller for standardized controller inputs.
"""

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple, Any

import pygame
from pygame._sdl2 import controller as sdl2_controller


# ----------------------------
# Type aliases
# ----------------------------

ButtonCallback = Callable[["Controller", str], None]
AxisCallback = Callable[["Controller", str, float], None]
DPadCallback = Callable[["Controller", Tuple[int, int]], None]
AnyCallback = Callable[..., None]


# ----------------------------
# Helper conversion / defaults
# ----------------------------

def _default_button_name(button_value: int) -> str:
    """
    Convert pygame controller button integer constants to readable names.

    This follows the common SDL / pygame controller names. If a value is
    unknown, it falls back to 'button_<int>'.
    """
    mapping = {
        getattr(pygame, "CONTROLLER_BUTTON_A", -1): "a",
        getattr(pygame, "CONTROLLER_BUTTON_B", -1): "b",
        getattr(pygame, "CONTROLLER_BUTTON_X", -1): "x",
        getattr(pygame, "CONTROLLER_BUTTON_Y", -1): "y",
        getattr(pygame, "CONTROLLER_BUTTON_BACK", -1): "back",
        getattr(pygame, "CONTROLLER_BUTTON_GUIDE", -1): "guide",
        getattr(pygame, "CONTROLLER_BUTTON_START", -1): "start",
        getattr(pygame, "CONTROLLER_BUTTON_LEFTSTICK", -1): "left_stick",
        getattr(pygame, "CONTROLLER_BUTTON_RIGHTSTICK", -1): "right_stick",
        getattr(pygame, "CONTROLLER_BUTTON_LEFTSHOULDER", -1): "left_shoulder",
        getattr(pygame, "CONTROLLER_BUTTON_RIGHTSHOULDER", -1): "right_shoulder",
        getattr(pygame, "CONTROLLER_BUTTON_DPAD_UP", -1): "dpad_up",
        getattr(pygame, "CONTROLLER_BUTTON_DPAD_DOWN", -1): "dpad_down",
        getattr(pygame, "CONTROLLER_BUTTON_DPAD_LEFT", -1): "dpad_left",
        getattr(pygame, "CONTROLLER_BUTTON_DPAD_RIGHT", -1): "dpad_right",
        getattr(pygame, "CONTROLLER_BUTTON_MISC1", -1): "misc1",
        getattr(pygame, "CONTROLLER_BUTTON_PADDLE1", -1): "paddle1",
        getattr(pygame, "CONTROLLER_BUTTON_PADDLE2", -1): "paddle2",
        getattr(pygame, "CONTROLLER_BUTTON_PADDLE3", -1): "paddle3",
        getattr(pygame, "CONTROLLER_BUTTON_PADDLE4", -1): "paddle4",
        getattr(pygame, "CONTROLLER_BUTTON_TOUCHPAD", -1): "touchpad",
    }
    return mapping.get(button_value, f"button_{button_value}")


def _default_axis_name(axis_value: int) -> str:
    """
    Convert pygame controller axis integer constants to readable names.
    """
    mapping = {
        getattr(pygame, "CONTROLLER_AXIS_LEFTX", -1): "left_x",
        getattr(pygame, "CONTROLLER_AXIS_LEFTY", -1): "left_y",
        getattr(pygame, "CONTROLLER_AXIS_RIGHTX", -1): "right_x",
        getattr(pygame, "CONTROLLER_AXIS_RIGHTY", -1): "right_y",
        getattr(pygame, "CONTROLLER_AXIS_TRIGGERLEFT", -1): "left_trigger",
        getattr(pygame, "CONTROLLER_AXIS_TRIGGERRIGHT", -1): "right_trigger",
    }
    return mapping.get(axis_value, f"axis_{axis_value}")


def _normalize_axis(raw_value: int) -> float:
    """
    Convert SDL-style signed 16-bit axis value into roughly [-1.0, 1.0].

    Controller axis motion events typically arrive in signed integer range.
    """
    # Clamp to int16 just in case.
    if raw_value < -32768:
        raw_value = -32768
    elif raw_value > 32767:
        raw_value = 32767

    # Symmetric-ish conversion.
    if raw_value >= 0:
        return raw_value / 32767.0
    return raw_value / 32768.0


# ----------------------------
# State containers
# ----------------------------

@dataclass
class MappingState:
    """
    Stores the callback mappings currently registered.
    """
    on_press: Dict[str, List[ButtonCallback]] = field(default_factory=dict)
    on_release: Dict[str, List[ButtonCallback]] = field(default_factory=dict)
    on_axis: Dict[str, List[AxisCallback]] = field(default_factory=dict)
    on_dpad: List[DPadCallback] = field(default_factory=list)
    on_any_event: List[AnyCallback] = field(default_factory=list)


@dataclass
class ControllerState:
    """
    Live state for one opened controller.
    """
    buttons_down: Dict[str, bool] = field(default_factory=dict)
    buttons_pressed_this_frame: Dict[str, bool] = field(default_factory=dict)
    buttons_released_this_frame: Dict[str, bool] = field(default_factory=dict)
    axes: Dict[str, float] = field(default_factory=dict)
    dpad: Tuple[int, int] = (0, 0)

    def begin_frame(self) -> None:
        self.buttons_pressed_this_frame.clear()
        self.buttons_released_this_frame.clear()


# ----------------------------
# Main controller object
# ----------------------------

class Controller:
    """
    Wraps a pygame SDL2 controller and maps its inputs to callbacks.

    Responsibilities:
    - open a controller device
    - keep current button / axis / dpad state
    - track per-frame press/release transitions
    - register callbacks for buttons, axes, and dpad
    - process pygame events
    """

    def __init__(
        self,
        device_index: int = 0,
        *,
        deadzone: float = 0.15,
        auto_init: bool = True,
    ) -> None:
        self.device_index = device_index
        self.deadzone = max(0.0, min(deadzone, 1.0))
        self.mapping = MappingState()
        self.state = ControllerState()

        self._controller: Optional[sdl2_controller.Controller] = None
        self.instance_id: Optional[int] = None
        self.name: Optional[str] = None
        self.attached: bool = False

        if auto_init:
            self.open(device_index)

    # ------------------------
    # Lifecycle
    # ------------------------

    @staticmethod
    def init_pygame() -> None:
        """
        Initialize pygame and the controller subsystem if needed.
        """
        if not pygame.get_init():
            pygame.init()

        # A display is strongly recommended because pygame's event system
        # depends on the video/event loop being alive in normal use.
        if not pygame.display.get_init():
            pygame.display.init()
            pygame.display.set_mode((320, 180))

        # Explicit init for controller layer
        if not sdl2_controller.get_init():
            sdl2_controller.init()

    @staticmethod
    def available_count() -> int:
        """
        Return number of detectable controllers.
        """
        Controller.init_pygame()
        return sdl2_controller.get_count()

    def open(self, device_index: int = 0) -> None:
        """
        Open the controller at the given device index.
        """
        self.init_pygame()

        count = self.available_count()
        if count <= 0:
            raise RuntimeError("No compatible controller detected.")

        if device_index < 0 or device_index >= count:
            raise IndexError(
                f"Controller index {device_index} is out of range. "
                f"Detected controllers: {count}"
            )

        self.device_index = device_index
        self._controller = sdl2_controller.Controller(device_index)
        self.name = self._controller.name
        self.attached = True

        # pygame 2 controller events carry an instance_id
        joystick_obj = self._controller.as_joystick()
        self.instance_id = joystick_obj.get_instance_id()

        # Prime known state buckets so users can inspect them immediately.
        for axis_name in (
            "left_x",
            "left_y",
            "right_x",
            "right_y",
            "left_trigger",
            "right_trigger",
        ):
            self.state.axes.setdefault(axis_name, 0.0)

    def close(self) -> None:
        """
        Close the opened controller.
        """
        # if self._controller is not None:
        #     self._controller.quit()

        self._controller = None
        self.instance_id = None
        self.attached = False
        self.name = None

    # ------------------------
    # Callback registration
    # ------------------------

    def map_button_press(self, button_name: str, callback: ButtonCallback) -> None:
        self.mapping.on_press.setdefault(button_name, []).append(callback)

    def map_button_release(self, button_name: str, callback: ButtonCallback) -> None:
        self.mapping.on_release.setdefault(button_name, []).append(callback)

    def map_axis(self, axis_name: str, callback: AxisCallback) -> None:
        self.mapping.on_axis.setdefault(axis_name, []).append(callback)

    def map_dpad(self, callback: DPadCallback) -> None:
        self.mapping.on_dpad.append(callback)

    def map_any_event(self, callback: AnyCallback) -> None:
        self.mapping.on_any_event.append(callback)

    def unmap_button_press(
        self, button_name: str, callback: Optional[ButtonCallback] = None
    ) -> None:
        self._remove_callback(self.mapping.on_press, button_name, callback)

    def unmap_button_release(
        self, button_name: str, callback: Optional[ButtonCallback] = None
    ) -> None:
        self._remove_callback(self.mapping.on_release, button_name, callback)

    def unmap_axis(
        self, axis_name: str, callback: Optional[AxisCallback] = None
    ) -> None:
        self._remove_callback(self.mapping.on_axis, axis_name, callback)

    def clear_all_mappings(self) -> None:
        self.mapping = MappingState()

    @staticmethod
    def _remove_callback(
        mapping_dict: Dict[str, List[AnyCallback]],
        key: str,
        callback: Optional[AnyCallback],
    ) -> None:
        if key not in mapping_dict:
            return

        if callback is None:
            del mapping_dict[key]
            return

        mapping_dict[key] = [cb for cb in mapping_dict[key] if cb != callback]
        if not mapping_dict[key]:
            del mapping_dict[key]

    # ------------------------
    # State query helpers
    # ------------------------

    def is_down(self, button_name: str) -> bool:
        return self.state.buttons_down.get(button_name, False)

    def was_pressed(self, button_name: str) -> bool:
        return self.state.buttons_pressed_this_frame.get(button_name, False)

    def was_released(self, button_name: str) -> bool:
        return self.state.buttons_released_this_frame.get(button_name, False)

    def axis(self, axis_name: str) -> float:
        return self.state.axes.get(axis_name, 0.0)

    def get_mapping_state(self) -> Dict[str, Any]:
        """
        Return an inspection-friendly snapshot of the callback mapping state.
        """
        return {
            "on_press": {k: len(v) for k, v in self.mapping.on_press.items()},
            "on_release": {k: len(v) for k, v in self.mapping.on_release.items()},
            "on_axis": {k: len(v) for k, v in self.mapping.on_axis.items()},
            "on_dpad": len(self.mapping.on_dpad),
            "on_any_event": len(self.mapping.on_any_event),
        }

    # ------------------------
    # Event handling
    # ------------------------

    def begin_frame(self) -> None:
        """
        Call once per update tick before processing events.
        """
        self.state.begin_frame()

    def process_events(self, events: Optional[List[pygame.event.Event]] = None) -> None:
        """
        Process pygame events for this controller.

        If `events` is None, pulls all current events from pygame.event.get().
        """
        if events is None:
            events = pygame.event.get()

        for event in events:
            self.process_event(event)

    def process_event(self, event: pygame.event.Event) -> None:
        """
        Process one pygame event.
        """
        for cb in self.mapping.on_any_event:
            cb(self, event)

        if self.instance_id is None:
            return

        event_type = event.type

        # Button pressed
        if event_type == pygame.CONTROLLERBUTTONDOWN:
            if getattr(event, "instance_id", None) != self.instance_id:
                return

            button_name = _default_button_name(event.button)
            self.state.buttons_down[button_name] = True
            self.state.buttons_pressed_this_frame[button_name] = True

            for cb in self.mapping.on_press.get(button_name, []):
                cb(self, button_name)
            return

        # Button released
        if event_type == pygame.CONTROLLERBUTTONUP:
            if getattr(event, "instance_id", None) != self.instance_id:
                return

            button_name = _default_button_name(event.button)
            self.state.buttons_down[button_name] = False
            self.state.buttons_released_this_frame[button_name] = True

            for cb in self.mapping.on_release.get(button_name, []):
                cb(self, button_name)
            return

        # Axis moved
        if event_type == pygame.CONTROLLERAXISMOTION:
            if getattr(event, "instance_id", None) != self.instance_id:
                return

            axis_name = _default_axis_name(event.axis)
            value = _normalize_axis(event.value)

            if abs(value) < self.deadzone:
                value = 0.0

            self.state.axes[axis_name] = value

            for cb in self.mapping.on_axis.get(axis_name, []):
                cb(self, axis_name, value)
            return

        # Device added / removed handling
        if event_type == pygame.CONTROLLERDEVICEREMOVED:
            if getattr(event, "instance_id", None) == self.instance_id:
                self.attached = False
            return

        if event_type == pygame.CONTROLLERDEVICEADDED:
            # Optional: auto-reopen if controller was removed and a new one appears.
            # Not doing silent remap magic here because that gets annoying fast.
            return

    # ------------------------
    # Polling helpers
    # ------------------------

    def poll_live_state(self) -> None:
        """
        Optional direct polling from the underlying controller object.

        Useful if you want current state without waiting for a motion event.
        """
        if self._controller is None or not self.attached:
            return

        # Buttons
        for button_name, button_const in (
            ("a", getattr(pygame, "CONTROLLER_BUTTON_A", None)),
            ("b", getattr(pygame, "CONTROLLER_BUTTON_B", None)),
            ("x", getattr(pygame, "CONTROLLER_BUTTON_X", None)),
            ("y", getattr(pygame, "CONTROLLER_BUTTON_Y", None)),
            ("back", getattr(pygame, "CONTROLLER_BUTTON_BACK", None)),
            ("guide", getattr(pygame, "CONTROLLER_BUTTON_GUIDE", None)),
            ("start", getattr(pygame, "CONTROLLER_BUTTON_START", None)),
            ("left_stick", getattr(pygame, "CONTROLLER_BUTTON_LEFTSTICK", None)),
            ("right_stick", getattr(pygame, "CONTROLLER_BUTTON_RIGHTSTICK", None)),
            ("left_shoulder", getattr(pygame, "CONTROLLER_BUTTON_LEFTSHOULDER", None)),
            ("right_shoulder", getattr(pygame, "CONTROLLER_BUTTON_RIGHTSHOULDER", None)),
            ("dpad_up", getattr(pygame, "CONTROLLER_BUTTON_DPAD_UP", None)),
            ("dpad_down", getattr(pygame, "CONTROLLER_BUTTON_DPAD_DOWN", None)),
            ("dpad_left", getattr(pygame, "CONTROLLER_BUTTON_DPAD_LEFT", None)),
            ("dpad_right", getattr(pygame, "CONTROLLER_BUTTON_DPAD_RIGHT", None)),
        ):
            if button_const is None:
                continue
            self.state.buttons_down[button_name] = bool(
                self._controller.get_button(button_const)
            )

        # Axes
        for axis_name, axis_const in (
            ("left_x", getattr(pygame, "CONTROLLER_AXIS_LEFTX", None)),
            ("left_y", getattr(pygame, "CONTROLLER_AXIS_LEFTY", None)),
            ("right_x", getattr(pygame, "CONTROLLER_AXIS_RIGHTX", None)),
            ("right_y", getattr(pygame, "CONTROLLER_AXIS_RIGHTY", None)),
            ("left_trigger", getattr(pygame, "CONTROLLER_AXIS_TRIGGERLEFT", None)),
            ("right_trigger", getattr(pygame, "CONTROLLER_AXIS_TRIGGERRIGHT", None)),
        ):
            if axis_const is None:
                continue
            value = _normalize_axis(self._controller.get_axis(axis_const))
            if abs(value) < self.deadzone:
                value = 0.0
            self.state.axes[axis_name] = value

        # D-pad as a tuple reconstructed from button state
        x = int(self.is_down("dpad_right")) - int(self.is_down("dpad_left"))
        y = int(self.is_down("dpad_down")) - int(self.is_down("dpad_up"))
        self.state.dpad = (x, y)

        for cb in self.mapping.on_dpad:
            cb(self, self.state.dpad)


# ----------------------------
# Example usage
# ----------------------------

# if __name__ == "__main__":
#     pygame.init()
#     pygame.display.set_caption("Controller Mapper Demo")
#     screen = pygame.display.set_mode((640, 360))
#     clock = pygame.time.Clock()

#     ctrl = Controller(0, deadzone=0.15)

#     def on_a_press(c: Controller, button: str) -> None:
#         print(f"{button} pressed")

#     def on_a_release(c: Controller, button: str) -> None:
#         print(f"{button} released")

#     def on_left_x(c: Controller, axis_name: str, value: float) -> None:
#         print(f"{axis_name}: {value:.3f}")

#     def on_left_y(c: Controller, axis_name: str, value: float) -> None:
#         print(f"{axis_name}: {value:.3f}")

#     ctrl.map_button_press("a", on_a_press)
#     ctrl.map_button_release("a", on_a_release)
#     ctrl.map_axis("left_x", on_left_x)
#     ctrl.map_axis("left_y", on_left_y)

#     running = True
#     while running:
#         ctrl.begin_frame()

#         for event in pygame.event.get():
#             if event.type == pygame.QUIT:
#                 running = False
#             ctrl.process_event(event)

#         # Optional polling if you want continuously updated state
#         ctrl.poll_live_state()

#         screen.fill((20, 20, 20))
#         pygame.display.flip()
#         clock.tick(60)

#     ctrl.close()
#     pygame.quit()