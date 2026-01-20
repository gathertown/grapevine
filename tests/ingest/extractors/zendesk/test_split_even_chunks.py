import pytest

from connectors.base.utils import split_even_chunks


class TestSplitEvenChunks:
    def test_max_chunk_size_zero(self):
        with pytest.raises(ValueError, match="max_chunk_size must be greater than 0"):
            list(split_even_chunks([1, 2, 3], 0))

    def test_negative_max_chunk_size(self):
        with pytest.raises(ValueError, match="max_chunk_size must be greater than 0"):
            list(split_even_chunks([1, 2, 3], -1))

    def test_max_chunk_size_of_one(self):
        result = list(split_even_chunks([1, 2, 3], 1))
        assert result == [[1], [2], [3]]

    def test_empty_list(self):
        input: list[int] = []
        result = list(split_even_chunks(input, 5))
        assert result == []

    def test_single_element(self):
        result = list(split_even_chunks([42], 5))
        assert result == [[42]]

    def test_exact_fit(self):
        result = list(split_even_chunks([1, 2, 3, 4, 5], 5))
        assert result == [[1, 2, 3, 4, 5]]

    def test_large_max_chunk_size(self):
        result = list(split_even_chunks([1, 2, 3], 10))
        assert result == [[1, 2, 3]]

    def test_even_distribution(self):
        # 6 items with max_chunk_size=4 should create 2 chunks of 3 each
        result = list(split_even_chunks([1, 2, 3, 4, 5, 6], 4))
        assert result == [[1, 2, 3], [4, 5, 6]]

    def test_minimizes_chunk_count(self):
        # 100 items with max_chunk_size=50 should create 2 chunks, not 3
        result = list(split_even_chunks(list(range(100)), 50))
        assert len(result) == 2
        assert all(len(chunk) == 50 for chunk in result)

        # 150 items with max_chunk_size=100 should create 2 chunks of 75 each
        result = list(split_even_chunks(list(range(150)), 100))
        assert len(result) == 2
        assert all(len(chunk) == 75 for chunk in result)
