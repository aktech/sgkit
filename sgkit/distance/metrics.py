"""
This module implements various distance metrics. To implement a new distance
metric, two methods needs to be written, one of them suffixed by 'map' and other
suffixed by 'reduce'. An entry for the same should be added in the N_MAP_PARAM
dictionary below.
"""

import math
from typing import Any

import numpy as np
from numba import cuda, guvectorize

from sgkit.typing import ArrayLike

# The number of parameters for the map step of the respective distance metric
N_MAP_PARAM = {
    "correlation": 6,
    "euclidean": 1,
}


@guvectorize(  # type: ignore
    [
        "void(float32[:], float32[:], float32[:], float32[:])",
        "void(float64[:], float64[:], float64[:], float64[:])",
        "void(int8[:], int8[:], int8[:], float64[:])",
    ],
    "(n),(n),(p)->(p)",
    nopython=True,
    cache=True,
)
def euclidean_map_cpu(
    x: ArrayLike, y: ArrayLike, _: ArrayLike, out: ArrayLike
) -> None:  # pragma: no cover
    """Euclidean distance "map" function for partial vector pairs.

    Parameters
    ----------
    x
        An array chunk, a partial vector
    y
        Another array chunk, a partial vector
    _
        A dummy variable to map the size of output
    out
        The output array, which has the squared sum of partial vector pairs.

    Returns
    -------
    An ndarray, which contains the output of the calculation of the application
    of euclidean distance on the given pair of chunks, without the aggregation.
    """
    square_sum = 0.0
    m = x.shape[0]
    # Ignore missing values
    for i in range(m):
        if x[i] >= 0 and y[i] >= 0:
            square_sum += (x[i] - y[i]) ** 2
    out[:] = square_sum


def euclidean_reduce_cpu(v: ArrayLike) -> ArrayLike:  # pragma: no cover
    """Corresponding "reduce" function for euclidean distance.

    Parameters
    ----------
    v
        The euclidean array on which map step of euclidean distance has been
        applied.

    Returns
    -------
    An ndarray, which contains square root of the sum of the squared sums obtained from
    the map step of `euclidean_map`.
    """
    out: ArrayLike = np.sqrt(np.einsum("ijkl -> ij", v))
    return out


@guvectorize(  # type: ignore
    [
        "void(float32[:], float32[:], float32[:], float32[:])",
        "void(float64[:], float64[:], float64[:], float64[:])",
        "void(int8[:], int8[:], int8[:], float64[:])",
    ],
    "(n),(n),(p)->(p)",
    nopython=True,
    cache=True,
)
def correlation_map_cpu(
    x: ArrayLike, y: ArrayLike, _: ArrayLike, out: ArrayLike
) -> None:  # pragma: no cover
    """Pearson correlation "map" function for partial vector pairs.

    Parameters
    ----------
    x
        An array chunk, a partial vector
    y
        Another array chunk, a partial vector
    _
        A dummy variable to map the size of output
    out
        The output array, which has the output of pearson correlation.

    Returns
    -------
    An ndarray, which contains the output of the calculation of the application
    of pearson correlation on the given pair of chunks, without the aggregation.
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

    out[:] = np.array(
        [
            np.sum(_x),
            np.sum(_y),
            np.sum(_x * _x),
            np.sum(_y * _y),
            np.sum(_x * _y),
            len(_x),
        ]
    )


@guvectorize(  # type: ignore
    [
        "void(float32[:, :], float32[:])",
        "void(float64[:, :], float64[:])",
    ],
    "(p, m)->()",
    nopython=True,
    cache=True,
)
def correlation_reduce_cpu(v: ArrayLike, out: ArrayLike) -> None:  # pragma: no cover
    """Corresponding "reduce" function for pearson correlation
    Parameters
    ----------
    v
        The correlation array on which pearson corrections has been
        applied on chunks
    out
        An ndarray, which is a symmetric matrix of pearson correlation

    Returns
    -------
    An ndarray, which contains the result of the calculation of the application
    of euclidean distance on all the chunks.
    """
    v = v.sum(axis=0)
    n = v[5]
    num = n * v[4] - v[0] * v[1]
    denom1 = np.sqrt(n * v[2] - v[0] ** 2)
    denom2 = np.sqrt(n * v[3] - v[1] ** 2)
    denom = denom1 * denom2
    value = np.nan
    if denom > 0:
        value = 1 - (num / denom)
    out[0] = value


def call_metric_kernel(
    f: ArrayLike, g: ArrayLike, metric: str, metric_kernel: Any
) -> ArrayLike:
    # Numba's 0.54.0 version is required, which is not released yet
    # We install numba from numba conda channel: conda install -c numba/label/dev numba
    # Relevant issue https://github.com/numba/numba/issues/6824
    f = np.ascontiguousarray(f)
    g = np.ascontiguousarray(g)

    # move input data to the device
    d_a = cuda.to_device(f)
    d_b = cuda.to_device(g)
    # create output data on the device
    out = np.zeros((f.shape[0], g.shape[0], N_MAP_PARAM[metric]), dtype=f.dtype)
    d_out = cuda.to_device(out)

    # TODO: Consider using cupy for directly creating zeros on GPU
    # d_out = cp.zeros((f.shape[0], g.shape[0], N_MAP_PARAM[metric]), dtype=f.dtype)

    threads_per_block = (32, 32)
    blocks_per_grid = (
        math.ceil(out.shape[0] / threads_per_block[0]),
        math.ceil(out.shape[1] / threads_per_block[1]),
    )

    metric_kernel[blocks_per_grid, threads_per_block](d_a, d_b, d_out)
    # copy the output array back to the host system
    d_out_host = d_out.copy_to_host()
    return d_out_host


@cuda.jit(device=True)  # type: ignore
def _correlation(x: ArrayLike, y: ArrayLike, out: ArrayLike) -> None:
    m = x.shape[0]
    # Note: assigning variable and only saving the final value in the
    # array made this significantly faster.
    v0 = 0.0
    v1 = 0.0
    v2 = 0.0
    v3 = 0.0
    v4 = 0.0
    v5 = 0.0

    for i in range(m):
        if x[i] >= 0 and y[i] >= 0:
            v0 += x[i]
            v1 += y[i]
            v2 += x[i] * x[i]
            v3 += y[i] * y[i]
            v4 += x[i] * y[i]
            v5 += 1

    out[0] = v0
    out[1] = v1
    out[2] = v2
    out[3] = v3
    out[4] = v4
    out[5] = v5


@cuda.jit  # type: ignore
def correlation_map_kernel(x: ArrayLike, y: ArrayLike, out: ArrayLike) -> None:
    i1, i2 = cuda.grid(2)
    if i1 >= out.shape[0] or i2 >= out.shape[1]:
        # Quit if (x, y) is outside of valid output array boundary
        return

    _correlation(x[i1], y[i2], out[i1][i2])


def correlation_map_gpu(f: ArrayLike, g: ArrayLike) -> ArrayLike:
    """Pearson correlation "map" function for partial vector pairs on GPU

    Parameters
    ----------
    f
        An array chunk, a partial vector
    g
        Another array chunk, a partial vector

    Returns
    -------
    An ndarray, which contains the output of the calculation of the application
    of pearson correlation on the given pair of chunks, without the aggregation.
    """

    return call_metric_kernel(f, g, "correlation", correlation_map_kernel)


def correlation_reduce_gpu(v: ArrayLike) -> None:
    return correlation_reduce_cpu(v)  # type: ignore


@cuda.jit(device=True)  # type: ignore
def _euclidean_distance(a: ArrayLike, b: ArrayLike, out: ArrayLike) -> None:
    square_sum = 0.0
    for i in range(a.shape[0]):
        if a[i] >= 0 and b[i] >= 0:
            square_sum += (a[i] - b[i]) ** 2
    out[0] = square_sum


@cuda.jit  # type: ignore
def euclidean_map_kernel(x: ArrayLike, y: ArrayLike, out: ArrayLike) -> None:
    i1, i2 = cuda.grid(2)
    if i1 >= out.shape[0] or i2 >= out.shape[1]:
        # Quit if (x, y) is outside of valid output array boundary
        return
    _euclidean_distance(x[i1], y[i2], out[i1][i2])


def euclidean_map_gpu(f: ArrayLike, g: ArrayLike) -> ArrayLike:
    return call_metric_kernel(f, g, "euclidean", euclidean_map_kernel)


def euclidean_reduce_gpu(v: ArrayLike) -> ArrayLike:
    return euclidean_reduce_cpu(v)
