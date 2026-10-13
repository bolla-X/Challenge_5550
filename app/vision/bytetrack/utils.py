class IdCounter:
    def __init__(self, start_id: int = 0) -> None:
        """
        Initialize the ID counter.

        Args:
            start_id: The starting integer for the counter.

        Raises:
            ValueError: If start_id is less than or equal to -1.
        """
        self.start_id = start_id
        if self.start_id <= self.NO_ID:
            raise ValueError(f"start_id must be greater than {self.NO_ID}")
        self.reset()

    def reset(self) -> None:
        """Reset the counter to the initial start_id."""
        self._id = self.start_id

    def new_id(self) -> int:
        """
        Get the current ID and increment the counter.

        Returns:
            The newly assigned ID.
        """
        returned_id = self._id
        self._id += 1
        return returned_id

    @property
    def NO_ID(self) -> int:
        return -1


def box_iou_batch(boxes_true, boxes_detection):
    """IoU par a par entre (N, 4) e (M, 4) em xyxy. Substitui o
    `supervision.detection.utils.iou_and_nms.box_iou_batch` (só o modo IoU)."""
    import numpy as np

    a = np.asarray(boxes_true, dtype=np.float32).reshape(-1, 4)
    b = np.asarray(boxes_detection, dtype=np.float32).reshape(-1, 4)
    area_a = (a[:, 2] - a[:, 0]).clip(0) * (a[:, 3] - a[:, 1]).clip(0)
    area_b = (b[:, 2] - b[:, 0]).clip(0) * (b[:, 3] - b[:, 1]).clip(0)
    tl = np.maximum(a[:, None, :2], b[None, :, :2])
    br = np.minimum(a[:, None, 2:], b[None, :, 2:])
    inter = (br - tl).clip(0).prod(axis=2)
    uniao = area_a[:, None] + area_b[None, :] - inter
    return np.where(uniao > 0, inter / np.maximum(uniao, 1e-9), 0.0).astype(np.float32)
