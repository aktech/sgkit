"""This module implements various distance metrics."""

import math

import numpy as np
from numba import guvectorize

from sgkit.typing import ArrayLike


@guvectorize(  # type: ignore
    [
        "void(float32[:], float32[:], float32[:])",
        "void(float64[:], float64[:], float64[:])",
        "void(int8[:], int8[:], float64[:])",
    ],
    "(n),(n)->()",
)
def correlation(x: ArrayLike, y: ArrayLike, out: ArrayLike) -> None:
    """Calculates the correlation between two vectors.

    Parameters
    ----------
    x
        [array-like, shape: (M,)]
        A vector
    y
        [array-like, shape: (M,)]
        Another vector
    out
        The output array, which has the output of pearson correlation.

    Returns
    -------
    A scalar representing the pearson correlation coefficient between two vectors x and y.

    Examples
    --------
    >>> from sgkit.distance.metrics import correlation
    >>> import dask.array as da
    >>> import numpy as np
    >>> x = da.array([4, 3, 2, 3], dtype='i1')
    >>> y = da.array([5, 6, 7, 0], dtype='i1')
    >>> correlation(x, y).compute()
    1.2626128

    >>> correlation(x, x).compute()
    -1.1920929e-07
    """
    m = x.shape[0]
    valid_indices = np.zeros(m, dtype=np.float64)

    for i in range(m):
        if x[i] >= 0 and y[i] >= 0:
            valid_indices[i] = 1

    valid_shape = valid_indices.sum()
    _x = np.zeros(int(valid_shape), dtype=x.dtype)
    _y = np.zeros(int(valid_shape), dtype=y.dtype)

    # Ignore missing values
    valid_idx = 0
    for i in range(valid_indices.shape[0]):
        if valid_indices[i] > 0:
            _x[valid_idx] = x[i]
            _y[valid_idx] = y[i]
            valid_idx += 1

    cov = ((_x - _x.mean()) * (_y - _y.mean())).sum()
    denom = (_x.std() * _y.std()) / _x.shape[0]

    value = np.nan
    if denom > 0:
        value = 1.0 - (cov / (_x.std() * _y.std()) / _x.shape[0])
    out[0] = value


@guvectorize(  # type: ignore
    [
        "void(float32[:, :], float32[:, :], float32[:, :])",
        "void(float64[:, :], float64[:, :], float64[:, :])",
        "void(int8[:, :], int8[:, :], float64[:, :])",
    ],
    "(m, k),(n, k)->(m, n)",
)
def euclidean(x: ArrayLike, y: ArrayLike, out: ArrayLike) -> None:
    """Calculates the euclidean distance between two vectors.

    Parameters
    ----------
    x
        [array-like, shape: (M,)]
        A vector
    y
        [array-like, shape: (M,)]
        Another vector
    out
        The output scalar, which has the output of euclidean between two vectors.

    Returns
    -------
    A scalar representing the euclidean distance between two vectors x and y.

    Examples
    --------
    >>> from sgkit.distance.metrics import euclidean
    >>> import dask.array as da
    >>> import numpy as np
    >>> x = da.array([4, 3, 2, 3], dtype='i1')
    >>> y = da.array([5, 6, 7, 0], dtype='i1')
    >>> euclidean(x, y).compute()
    6.6332495807108

    >>> euclidean(x, x).compute()
    0.0

    """
    o = x.shape[-1]
    m = x.shape[0]
    n = y.shape[0]

    for j in range(m):
        for k in range(n):
            square_sum = 0.0
            for i in range(o):
                if x[j, i] >= 0 and y[k, i] >= 0:
                    square_sum += (x[j, i] - y[k, i]) ** 2
            out[j, k] = math.sqrt(square_sum)
