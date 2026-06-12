"""鍵盤模擬。

用 pydirectinput 送 DirectInput scan code，
一般 pyautogui 的 SendInput 虛擬鍵在很多遊戲裡會被忽略。
"""
import time

try:
    import pydirectinput
    pydirectinput.PAUSE = 0  # 我們自己控制節奏
except Exception:  # 非 Windows 環境（開發用）
    pydirectinput = None


class KeyController:
    """管理按住中的按鍵，確保切換動作/暫停時會把鍵放開。"""

    def __init__(self):
        self._held: set[str] = set()

    def tap(self, key: str):
        if pydirectinput is None:
            return
        pydirectinput.press(key)

    def hold(self, key: str):
        if pydirectinput is None or key in self._held:
            return
        pydirectinput.keyDown(key)
        self._held.add(key)

    def release(self, key: str):
        if pydirectinput is None or key not in self._held:
            return
        pydirectinput.keyUp(key)
        self._held.discard(key)

    def release_all(self):
        for key in list(self._held):
            self.release(key)

    def hold_only(self, keys: list[str]):
        """只按住指定的鍵，其餘全放開（移動動作切換用）。"""
        for k in list(self._held):
            if k not in keys:
                self.release(k)
        for k in keys:
            self.hold(k)


class Cooldown:
    """簡單的冷卻計時器。"""

    def __init__(self, seconds: float):
        self.seconds = seconds
        self._last = 0.0

    def ready(self) -> bool:
        return time.time() - self._last >= self.seconds

    def trigger(self):
        self._last = time.time()
