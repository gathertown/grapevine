import math
from collections.abc import Iterable, Sized
from typing import Protocol, Self


# https://stackoverflow.com/a/79602086
class Sliceable(Sized, Protocol):
    def __getitem__(self: Self, key: slice, /) -> Self: ...


def split_even_chunks[T: Sliceable](initial: T, max_chunk_size: int) -> Iterable[T]:
    """
    Split a list into:
    - as few batches as possible,
    - each no larger than max_chunk_size,
    - and as evenly sized as possible.
    """

    if max_chunk_size <= 0:
        raise ValueError("max_chunk_size must be greater than 0")

    if initial:
        chunk_count = math.ceil(len(initial) / max_chunk_size)
        chunk_size = math.ceil(len(initial) / chunk_count)
        for i in range(0, len(initial), chunk_size):
            yield initial[i : i + chunk_size]
