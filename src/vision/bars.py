"""HP/MP 條偵測：算血條區域內「填充色」像素的佔比。"""
import cv2
import numpy as np


def bar_ratio(frame_bgr: np.ndarray, region: dict, fill_color_bgr, tolerance: int) -> float:
    """回傳 0~1 的填充比例。

    做法：取血條區域的中間一列，從左往右找最後一個符合填充色的像素。
    比單純數像素更能容忍血條上的文字/光影。
    """
    x, y, w, h = region["x"], region["y"], region["w"], region["h"]
    roi = frame_bgr[y:y + h, x:x + w]
    if roi.size == 0:
        return 1.0
    color = np.array(fill_color_bgr, dtype=np.int16)
    lower = np.clip(color - tolerance, 0, 255).astype(np.uint8)
    upper = np.clip(color + tolerance, 0, 255).astype(np.uint8)
    mask = cv2.inRange(roi, lower, upper)
    # 任一列有填充色就算該 x 位置有血
    cols = mask.max(axis=0)
    filled = np.nonzero(cols)[0]
    if filled.size == 0:
        return 0.0
    return float(filled[-1] + 1) / w
