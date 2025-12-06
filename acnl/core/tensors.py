"""
ACNL Core — Tensor Adapters

Convert fields to numpy/torch tensors for agent consumption.
Keeps torch optional — numpy is always available.
"""

from __future__ import annotations
from typing import List, Optional, Callable, Tuple, Literal, TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .fields import LocalField
    from .ids import EntityID

import numpy as np


def field_to_tensor(
    field: "LocalField",
    feature_keys: List[str],
    subject_filter: Optional[Callable[["EntityID"], bool]] = None,
    backend: Literal["numpy", "torch"] = "numpy",
) -> Tuple[List["EntityID"], Any]:
    """
    Convert LocalField to tensor.

    Args:
        field: LocalField to convert
        feature_keys: List of metric keys to include as features
        subject_filter: Optional filter for subjects
        backend: "numpy" or "torch"

    Returns:
        (subject_ids, tensor) where tensor has shape (n_subjects, n_features)
    """
    points = field.all_points()

    if subject_filter:
        points = [p for p in points if subject_filter(p.subject)]

    if not points:
        empty = np.zeros((0, len(feature_keys)), dtype=np.float32)
        if backend == "torch":
            import torch
            return [], torch.from_numpy(empty)
        return [], empty

    # Build matrix
    n_subjects = len(points)
    n_features = len(feature_keys)

    data = np.zeros((n_subjects, n_features), dtype=np.float32)
    subject_ids = []

    for i, point in enumerate(points):
        subject_ids.append(point.subject)
        for j, key in enumerate(feature_keys):
            data[i, j] = point.get(key, 0.0)

    if backend == "torch":
        import torch
        return subject_ids, torch.from_numpy(data)

    return subject_ids, data


def normalize_tensor(tensor: Any, dim: int = 0, eps: float = 1e-8) -> Any:
    """Normalize tensor along dimension."""
    if hasattr(tensor, 'numpy'):  # torch
        import torch
        mean = tensor.mean(dim=dim, keepdim=True)
        std = tensor.std(dim=dim, keepdim=True)
        return (tensor - mean) / (std + eps)
    else:  # numpy
        mean = np.mean(tensor, axis=dim, keepdims=True)
        std = np.std(tensor, axis=dim, keepdims=True)
        return (tensor - mean) / (std + eps)


def softmax(tensor: Any, dim: int = -1, temperature: float = 1.0) -> Any:
    """Softmax with temperature."""
    if hasattr(tensor, 'numpy'):  # torch
        import torch
        return torch.softmax(tensor / temperature, dim=dim)
    else:  # numpy
        x = tensor / temperature
        x = x - np.max(x, axis=dim, keepdims=True)
        exp_x = np.exp(x)
        return exp_x / np.sum(exp_x, axis=dim, keepdims=True)
