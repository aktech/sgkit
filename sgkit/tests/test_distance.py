import dask.array as da
import numpy as np
import pytest
from scipy.spatial.distance import pdist as scipy_pdist  # type: ignore
from scipy.spatial.distance import squareform

from sgkit.distance.api import pairwise_distance
from sgkit.typing import ArrayLike


def get_vectors(array_type: str = "da") -> ArrayLike:
    if array_type == "da":
        rs = da.random.RandomState(0)
        x = rs.randint(0, 3, size=(18, 40), dtype="i1").rechunk((6, 10))
    else:
        x = np.random.rand(18, 40)
    return x


def test_distance_correlation() -> None:
    x = get_vectors()
    distance_matrix = pairwise_distance(x, metric="correlation")
    np.testing.assert_almost_equal(distance_matrix, np.corrcoef(x).compute())


def test_distance_euclidean() -> None:
    x = get_vectors()
    distance_matrix = pairwise_distance(x, metric="euclidean")
    distance_array = scipy_pdist(x)
    expected_matrix = squareform(distance_array)
    np.testing.assert_almost_equal(distance_matrix, expected_matrix)


def test_distance_ndarray() -> None:
    x = get_vectors(array_type="np")
    distance_matrix = pairwise_distance(x, metric="euclidean")
    distance_array = scipy_pdist(x)
    expected_matrix = squareform(distance_array)
    np.testing.assert_almost_equal(distance_matrix, expected_matrix)


def test_undefined_metric() -> None:
    x = get_vectors(array_type="np")
    with pytest.raises(NotImplementedError):
        pairwise_distance(x, metric="not-implemented-metric")
