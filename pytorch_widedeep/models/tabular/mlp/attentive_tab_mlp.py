import torch
from torch import nn

from pytorch_widedeep.wdtypes import *  # noqa: F403
from pytorch_widedeep.models.embeddings_layers import (
    SameSizeCatAndContEmbeddings,
)
from pytorch_widedeep.models._get_activation_fn import allowed_activations
from pytorch_widedeep.models.tabular.mlp._layers import MLP
from pytorch_widedeep.models.tabular.mlp._encoders import AttentionEncoder


class AttentiveTabMlp(nn.Module):
    r"""Defines an ``AttentiveTabMlp`` model. This is an extension of the
    ``TabMlp`` model with attention mechanisms

    Parameters
    ----------
    column_idx: Dict
        Dict containing the index of the columns that will be passed through
        the ``TabMlp`` model. Required to slice the tensors. e.g. {'education':
        0, 'relationship': 1, 'workclass': 2, ...}
    cat_embed_input: List, Optional, default = None
        List of Tuples with the column name, number of unique values and
        embedding dimension. e.g. [(education, 11, 32), ...]
    cat_embed_dropout: float, default = 0.1
        embeddings dropout
    full_embed_dropout: bool, default = False
        Boolean indicating if an entire embedding (i.e. the representation of
        one column) will be dropped in the batch. See:
        :obj:`pytorch_widedeep.models.embeddings_layers.FullEmbeddingDropout`.
         If ``full_embed_dropout = True``, ``cat_embed_dropout`` is ignored.
    shared_embed: bool, default = False
        The of sharing part of the embeddings per column is to enable the
        model to distinguish the classes in one column from those in the
        other columns'`. In other words, the idea is to let the model learn
        which column is embedded at the time.
    add_shared_embed: bool, default = False,
        The two embedding sharing strategies are: 1) add the shared embeddings
        to the column embeddings or 2) to replace the first
        ``frac_shared_embed`` with the shared embeddings.
        See :obj:`pytorch_widedeep.models.embeddings_layers.SharedEmbeddings`
    frac_shared_embed: float, default = 0.25
        The fraction of embeddings that will be shared (if ``add_shared_embed
        = False``) by all the different categories for one particular
        column.
    continuous_cols: List, Optional, default = None
        List with the name of the numeric (aka continuous) columns
    cont_embed_dropout: float, default = 0.1,
        Dropout for the continuous embeddings
    cont_embed_activation: Optional, str, default = None,
        Activation function for the continuous embeddings
    cont_norm_layer: str, default =  "batchnorm"
        Type of normalization layer applied to the continuous features. Options
        are: 'layernorm', 'batchnorm' or None.
    input_dim: int, default = 32
        The so-called *dimension of the model*. In general is the number of
        embeddings used to encode the categorical and/or continuous columns
    attention_name: str, default = "context_attention",
        The type of attention used. Options are 'context_attention'
        and 'self_attention'. The former is inspired by the attention
        mechanism described in `Hierarchical Attention Networks for Document
        Classification
        <https://paperswithcode.com/paper/hierarchical-attention-networks-for-document>`_.
        While the second one is a simplication of the well known multihead
        attention described in `Attention is all you need
        <https://arxiv.org/abs/1706.03762>_` , where only query and key projections
        are used.
    with_residual: bool = False,
        Boolean indicating if residual connections will be used in the attention blocks
    n_heads: int, default = 8
        Number of attention heads per FastFormer block
    use_bias: bool, default = False
        Boolean indicating whether or not to use bias in the Q, K, and V
        projection layers
    n_blocks: int, default = 2
        Number of FastFormer blocks
    attn_dropout: float = 0.2,
        Dropout within the attention blocks
    mlp_hidden_dims: Optional, List, default = None
        List with the number of neurons per dense layer in the mlp.
    mlp_activation: str, default = "relu"
        Activation function for the dense layers of the MLP. Currently
        ``tanh``, ``relu``, ``leaky_relu`` and ``gelu`` are supported
    mlp_dropout: float or List, default = 0.1
        float or List of floats with the dropout between the dense layers.
        e.g: [0.5,0.5]
    mlp_batchnorm: bool, default = False
        Boolean indicating whether or not batch normalization will be applied
        to the dense layers
    mlp_batchnorm_last: bool, default = False
        Boolean indicating whether or not batch normalization will be applied
        to the last of the dense layers
    mlp_linear_first: bool, default = False
        Boolean indicating the order of the operations in the dense
        layer. If ``True: [LIN -> ACT -> BN -> DP]``. If ``False: [BN -> DP ->
        LIN -> ACT]``

    Attributes
    ----------
    cat_and_cont_embed: ``nn.Module``
        This is the module that processes the categorical and continuous columns
    attention_blks: ``nn.Sequential``
        Sequence of attention encoders.
    tab_mlp: ``nn.Sequential``
        mlp model that will receive the concatenation of the embeddings and
        the continuous columns
    output_dim: int
        The output dimension of the model. This is a required attribute
        neccesary to build the WideDeep class

    Example
    --------
    >>> import torch
    >>> from pytorch_widedeep.models import TabMlp
    >>> X_tab = torch.cat((torch.empty(5, 4).random_(4), torch.rand(5, 1)), axis=1)
    >>> colnames = ['a', 'b', 'c', 'd', 'e']
    >>> cat_embed_input = [(u,i,j) for u,i,j in zip(colnames[:4], [4]*4, [8]*4)]
    >>> column_idx = {k:v for v,k in enumerate(colnames)}
    >>> model = TabMlp(mlp_hidden_dims=[8,4], column_idx=column_idx, cat_embed_input=cat_embed_input,
    ... continuous_cols = ['e'])
    >>> out = model(X_tab)
    """

    def __init__(
        self,
        column_idx: Dict[str, int],
        cat_embed_input: Optional[List[Tuple[str, int]]] = None,
        cat_embed_dropout: float = 0.1,
        full_embed_dropout: bool = False,
        shared_embed: bool = False,
        add_shared_embed: bool = False,
        frac_shared_embed: float = 0.25,
        continuous_cols: Optional[List[str]] = None,
        embed_continuous_activation: str = None,
        cont_embed_dropout: float = 0.0,
        cont_embed_activation: str = None,
        cont_norm_layer: str = None,
        input_dim: int = 32,
        attention_name: str = "context_attention",
        attn_dropout: float = 0.2,
        with_residual: bool = False,
        n_heads: int = 8,
        use_bias: bool = False,
        n_blocks: int = 2,
        mlp_hidden_dims: Optional[List[int]] = None,
        mlp_activation: str = "relu",
        mlp_dropout: float = 0.1,
        mlp_batchnorm: bool = False,
        mlp_batchnorm_last: bool = False,
        mlp_linear_first: bool = True,
    ):
        super(AttentiveTabMlp, self).__init__()

        self.column_idx = column_idx
        self.cat_embed_input = cat_embed_input
        self.cat_embed_dropout = cat_embed_dropout
        self.full_embed_dropout = full_embed_dropout
        self.shared_embed = shared_embed
        self.add_shared_embed = add_shared_embed
        self.frac_shared_embed = frac_shared_embed

        self.continuous_cols = continuous_cols
        self.embed_continuous_activation = embed_continuous_activation
        self.cont_embed_dropout = cont_embed_dropout
        self.cont_embed_activation = cont_embed_activation
        self.cont_norm_layer = cont_norm_layer

        self.input_dim = input_dim
        self.attention_name = attention_name
        self.attn_dropout = attn_dropout
        self.with_residual = with_residual
        self.n_heads = n_heads
        self.use_bias = use_bias
        self.n_blocks = n_blocks

        self.mlp_hidden_dims = mlp_hidden_dims
        self.mlp_activation = mlp_activation
        self.mlp_dropout = mlp_dropout
        self.mlp_batchnorm = mlp_batchnorm
        self.mlp_batchnorm_last = mlp_batchnorm_last
        self.mlp_linear_first = mlp_linear_first

        self.with_cls_token = "cls_token" in column_idx
        self.n_cat = len(cat_embed_input) if cat_embed_input is not None else 0
        self.n_cont = len(continuous_cols) if continuous_cols is not None else 0

        if self.mlp_activation not in allowed_activations:
            raise ValueError(
                "Currently, only the following activation functions are supported "
                "for for the MLP's dense layers: {}. Got {} instead".format(
                    ", ".join(allowed_activations), self.mlp_activation
                )
            )

        self.cat_and_cont_embed = SameSizeCatAndContEmbeddings(
            input_dim,
            column_idx,
            cat_embed_input,
            cat_embed_dropout,
            full_embed_dropout,
            shared_embed,
            add_shared_embed,
            frac_shared_embed,
            False,  # use_embed_bias
            continuous_cols,
            True,  # embed_continuous,
            cont_embed_dropout,
            embed_continuous_activation,
            True,  # use_cont_bias
            cont_norm_layer,
        )

        # Attention blocks
        self.attention_blks = nn.Sequential()
        for i in range(n_blocks):
            self.attention_blks.add_module(
                "attention_block" + str(i),
                AttentionEncoder(
                    input_dim,
                    attn_dropout,
                    with_residual,
                    attention_name,
                    use_bias,
                    n_heads,
                ),
            )

        # Mlp
        if mlp_hidden_dims is not None:
            attn_output_dim = (
                self.input_dim
                if self.with_cls_token
                else (self.n_cat + self.n_cont) * self.input_dim
            )
            self.attn_tab_mlp = MLP(
                [attn_output_dim] + mlp_hidden_dims,
                mlp_activation,
                mlp_dropout,
                mlp_batchnorm,
                mlp_batchnorm_last,
                mlp_linear_first,
            )
            # the output_dim attribute will be used as input_dim when "merging" the models
            self.output_dim = mlp_hidden_dims[-1]
        else:
            self.attn_tab_mlp = None
            self.output_dim = (
                input_dim
                if self.with_cls_token
                else ((self.n_cat + self.n_cont) * input_dim)
            )

    def forward(self, X: Tensor) -> Tensor:

        x_cat, x_cont = self.cat_and_cont_embed(X)

        if x_cat is not None:
            x = x_cat
        if x_cont is not None:
            x = torch.cat([x, x_cont], 1) if x_cat is not None else x_cont

        x = self.attention_blks(x)

        if self.with_cls_token:
            out = x[:, 0, :]
        else:
            out = x.flatten(1)

        if self.mlp_hidden_dims is not None:
            out = self.attn_tab_mlp(out)

        return out

    @property
    def attention_weights(self) -> List:
        r"""List with the attention weights

        The shape of the attention weights if the attention mechanism
        is "self_attention" is:

        :math:`(N, H, F, F)`

        Where *N* is the batch size, *H* is the number of attention heads
        and *F* is the number of features/columns in the dataset

        On the other hand if the attention mechanism is "context_attention",
        the shape of the attention weights is:

        :math:`(N, F)`

        Where *N* is the batch size and *F* is the number of features/columns
        in the dataset
        """
        return [blk.attn.attn_weights for blk in self.attention_blks]
