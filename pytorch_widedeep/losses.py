import torch
import torch.nn as nn
import torch.nn.functional as F

from .wdtypes import *  # noqa: F403

use_cuda = torch.cuda.is_available()

method_to_objec = {
    "binary": [
        "binary",
        "logistic",
        "binary_logloss",
        "binary_cross_entropy",
        "binary_focal_loss",
    ],
    "multiclass": [
        "multiclass",
        "multi_logloss",
        "cross_entropy",
        "categorical_cross_entropy",
        "multiclass_focal_loss",
    ],
    "regression": [
        "regression",
        "mse",
        "l2",
        "mean_squared_error",
        "mean_absolute_error",
        "mae",
        "l1",
        "mean_squared_log_error",
        "msle",
        "root_mean_squared_error",
        "rmse",
        "root_mean_squared_log_error",
        "rmsle",
    ],
}


objective_to_method = {
    obj: method for method, objs in method_to_objec.items() for obj in objs
}


loss_aliases = {
    "binary": ["binary", "logistic", "binary_logloss", "binary_cross_entropy"],
    "multiclass": [
        "multiclass",
        "multi_logloss",
        "cross_entropy",
        "categorical_cross_entropy",
    ],
    "regression": ["regression", "mse", "l2", "mean_squared_error"],
    "mean_absolute_error": ["mean_absolute_error", "mae", "l1"],
    "mean_squared_log_error": ["mean_squared_log_error", "msle"],
    "root_mean_squared_error": ["root_mean_squared_error", "rmse"],
    "root_mean_squared_log_error": ["root_mean_squared_log_error", "rmsle"],
}


def get_loss_function(loss_fn: str, **kwargs):
    if loss_fn not in objective_to_method.keys():
        raise ValueError(
            "objective or loss function is not supported. Please consider passing a callable "
            "directly to the compile method (see docs) or use one of the supported objectives "
            "or loss functions: {}".format(", ".join(objective_to_method.keys()))
        )
    if loss_fn in loss_aliases["binary"]:
        return nn.BCEWithLogitsLoss(weight=kwargs["weight"])
    if loss_fn in loss_aliases["multiclass"]:
        return nn.CrossEntropyLoss(weight=kwargs["weight"])
    if loss_fn in loss_aliases["regression"]:
        return nn.MSELoss()
    if loss_fn in loss_aliases["mean_absolute_error"]:
        return nn.L1Loss()
    if loss_fn in loss_aliases["mean_squared_log_error"]:
        return MSLELoss()
    if loss_fn in loss_aliases["root_mean_squared_error"]:
        return RMSELoss()
    if loss_fn in loss_aliases["root_mean_squared_log_error"]:
        return RMSLELoss()
    if "focal_loss" in loss_fn:
        return FocalLoss(**kwargs)


class FocalLoss(nn.Module):
    r"""Implementation of the `focal loss
    <https://arxiv.org/pdf/1708.02002.pdf>`_ for both binary and
    multiclass classification

    Parameters
    ----------
    alpha: float
        Focal Loss ``alpha`` parameter
    gamma: float
        Focal Loss ``gamma`` parameter
    """

    def __init__(self, alpha: float = 0.25, gamma: float = 1.0):
        super().__init__()
        self.alpha = alpha
        self.gamma = gamma

    def _get_weight(self, p: Tensor, t: Tensor) -> Tensor:
        pt = p * t + (1 - p) * (1 - t)  # type: ignore
        w = self.alpha * t + (1 - self.alpha) * (1 - t)  # type: ignore
        return (w * (1 - pt).pow(self.gamma)).detach()  # type: ignore

    def forward(self, input: Tensor, target: Tensor) -> Tensor:
        r"""Focal Loss computation

        Parameters
        ----------
        input: Tensor
            input tensor with predictions (not probabilities)
        target: Tensor
            target tensor with the actual classes

        Examples
        --------
        >>> import torch
        >>>
        >>> from pytorch_widedeep.losses import FocalLoss
        >>>
        >>> # BINARY
        >>> target = torch.tensor([0, 1, 0, 1]).view(-1, 1)
        >>> input = torch.tensor([[0.6, 0.7, 0.3, 0.8]]).t()
        >>> FocalLoss()(input, target)
        tensor(0.1762)
        >>>
        >>> # MULTICLASS
        >>> target = torch.tensor([1, 0, 2]).view(-1, 1)
        >>> input = torch.tensor([[0.2, 0.5, 0.3], [0.8, 0.1, 0.1], [0.7, 0.2, 0.1]])
        >>> FocalLoss()(input, target)
        tensor(0.2573)
        """
        input_prob = torch.sigmoid(input)
        if input.size(1) == 1:
            input_prob = torch.cat([1 - input_prob, input_prob], axis=1)  # type: ignore
            num_class = 2
        else:
            num_class = input_prob.size(1)
        binary_target = torch.eye(num_class)[target.squeeze().long()]
        if use_cuda:
            binary_target = binary_target.cuda()
        binary_target = binary_target.contiguous()
        weight = self._get_weight(input_prob, binary_target)
        return F.binary_cross_entropy(
            input_prob, binary_target, weight, reduction="mean"
        )


class MSLELoss(nn.Module):
    def __init__(self):
        super().__init__()
        self.mse = nn.MSELoss()

    def forward(self, input: Tensor, target: Tensor) -> Tensor:
        return self.mse(torch.log(input + 1), torch.log(target + 1))


class RMSELoss(nn.Module):
    def __init__(self):
        super().__init__()
        self.mse = nn.MSELoss()

    def forward(self, input: Tensor, target: Tensor) -> Tensor:
        return torch.sqrt(self.mse(input, target))


class RMSLELoss(nn.Module):
    def __init__(self):
        super().__init__()
        self.mse = nn.MSELoss()

    def forward(self, input: Tensor, target: Tensor) -> Tensor:
        return torch.sqrt(self.mse(torch.log(input + 1), torch.log(target + 1)))
