# TODO: rename module to utils not _utils
import inspect
from functools import wraps

import numpy as np
import xarray as xr

from .xarray_wrapper import _handle_labelled_dataset, is_labelled_cp


def _alias_mode_axis():
    def decorator(func):
        func_sig = inspect.signature(func)
        if "axis" not in func_sig.parameters or "mode" not in func_sig.parameters:
            raise TypeError(f"Function {func} needs both ``mode`` and ``axis`` as possible arguments.")
        mode_default_value = func_sig.parameters["mode"].default
        if mode_default_value == inspect._empty:
            mode_default_value = None

        @wraps(func)
        def new_func(*args, **kwargs):
            bound_arguments = func_sig.bind_partial(*args, **kwargs)

            mode = bound_arguments.arguments.get("mode", mode_default_value)
            axis = bound_arguments.arguments.get("axis", None)
            if mode is None and axis is None:
                raise TypeError(
                    f"Function {func} needs either ``mode`` or ``axis`` to be set to a value different than None."
                )
            elif mode != mode_default_value and axis is not None:
                raise TypeError("Either ``mode`` or ``axis`` can be specified, not both.")
            elif axis is not None:
                bound_arguments.arguments["mode"] = axis
            return func(**bound_arguments.arguments)

        return new_func

    return decorator


def extract_singleton(x):
    """Extracts a singleton from an array.

    This is useful whenever XArray or Pandas is used, since many NumPy functions that
    return a number may return a singleton array instead.

    Parameters
    ----------
    x : float, numpy.ndarray, xarray.DataArray or pandas.DataFrame
        Singleton array to extract value from.

    Returns
    -------
    float
        Singleton value extracted from ``x``.
    """
    return np.asarray(x).reshape(-1).item()


@_handle_labelled_dataset("tensor", None)
@_alias_mode_axis()
def unfold_tensor(tensor, mode, axis=None):
    """Unfolds (matricises) a potentially labelled data tensor into a numpy array along given mode.

    Arguments
    ---------
    tensor : np.ndarray or xarray.DataArray
        Dataset to unfold
    mode : int
        Which mode (axis) to unfold the dataset along.
    axis : int (optional)
        Which mode (axis) to unfold the dataset along. If set, then the mode-argument is unused.

    Returns
    -------
    np.ndarray
        The unfolded dataset as a numpy array.
    """
    # TODO: return xarray or dataframe if tensor is labelled
    dataset = np.asarray(tensor)
    return np.moveaxis(dataset, mode, 0).reshape(dataset.shape[mode], -1)


def cp_to_tensor(cp_tensor):
    """Construct a CP tensor, equivalent to ``cp_to_tensor`` in TensorLy, but supports dataframes.

    If the factor matrices are data frames, then the tensor will be returned as a labelled
    xarray. Otherwise, it will be returned as a numpy array.

    Parameters
    ----------
    cp_tensor : CPTensor or tuple
        TensorLy-style CPTensor object or tuple with weights as first
        argument and a tuple of components as second argument.

    Returns
    -------
    xarray or np.ndarray
        Dense tensor represented by the decomposition.
    """
    # TODO: Tests (1 component for example)
    # TODO: Example with and without labels

    if cp_tensor[0] is None:
        weights = np.ones(cp_tensor[1][0].shape[1])
    else:
        weights = cp_tensor[0].reshape(-1)

    einsum_input = "R"
    einsum_output = ""
    for mode in range(len(cp_tensor[1])):
        idx = chr(ord("a") + mode)

        # We cannot use einsum with letters outside the alphabet
        if ord(idx) > ord("z"):
            max_modes = ord("a") - ord("z") - 1
            raise ValueError(f"Cannot have more than {max_modes} modes. Current components have {len(cp_tensor[1])}.")

        einsum_input += f", {idx}R"
        einsum_output += idx

    tensor = np.einsum(f"{einsum_input} -> {einsum_output}", weights, *cp_tensor[1])

    if not is_labelled_cp(cp_tensor):
        return tensor

    # Convert to labelled xarray DataArray:
    coords_dict = {}
    dims = []
    for mode, fm in enumerate(cp_tensor[1]):
        mode_name = f"Mode {mode}"
        if fm.index.name is not None:
            mode_name = fm.index.name

        coords_dict[mode_name] = fm.index.values
        dims.append(mode_name)

    return xr.DataArray(tensor, dims=dims, coords=coords_dict)


def tucker_to_tensor(tucker_tensor):
    """Construct a Tucker tensor, equivalent to ``tucker_to_tensor`` in TensorLy, but supports dataframes.

    If the factor matrices are data frames, then the tensor will be returned as a labelled
    xarray. Otherwise, it will be returned as a numpy array.

    Parameters
    ----------
    tucker : CPTensor or tuple
        TensorLy-style TuckerTensor object or tuple with weights as first
        argument and a tuple of components as second argument.

    Returns
    -------
    xarray or np.ndarray
        Dense tensor represented by the decomposition.
    """
    # TODO: NEXT Handle dataframes
    einsum_core = ""
    einsum_input = ""
    einsum_output = ""

    for mode in range(len(tucker_tensor[1])):
        idx = chr(ord("a") + mode)
        rank_idx = chr(ord("A") + mode)

        # We cannot use einsum with letters outside the alphabet
        if ord(idx) > ord("z"):
            max_modes = ord("a") - ord("z")
            raise ValueError(
                f"Cannot have more than {max_modes} modes. Current components have {len(tucker_tensor[1])}."
            )

        einsum_core += rank_idx
        einsum_input += f", {idx}{rank_idx}"
        einsum_output += idx

    return np.einsum(f"{einsum_core}{einsum_input} -> {einsum_output}", tucker_tensor[0], *tucker_tensor[1],)