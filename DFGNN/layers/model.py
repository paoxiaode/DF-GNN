import torch.nn as nn

from ogb.graphproppred.mol_encoder import AtomEncoder


def choose_Inproj(dataset_name, hidden_size):
    if dataset_name in [
        "ogbg-molhiv",
        "ogbg-molpcba",
        "Peptides-func",
        "Peptides-struct",
    ]:
        return AtomEncoder(hidden_size)
    elif dataset_name == "PATTERN":
        return nn.Embedding(3, hidden_size)
    elif dataset_name == "CLUSTER":
        return nn.Embedding(7, hidden_size)
    elif dataset_name == "MNIST":
        return nn.Linear(3, hidden_size)
    elif dataset_name == "CIFAR10":
        return nn.Linear(5, hidden_size)
    elif dataset_name in ["PascalVOC-SP", "COCO-SP"]:
        return nn.Linear(14, hidden_size)
    else:
        raise ValueError(f"unknown dataset {dataset_name}")


# For dataset with node feature: MNIST, CIFAR10, cora
class Model(nn.Module):
    """Module with specified graph conv on specified dataset"""

    def __init__(self, dataset_name, Conv, hidden_size):
        super().__init__()
        self.inproj = choose_Inproj(dataset_name, hidden_size)
        self.Conv = Conv

    def forward(self, params, X, fuse=False):
        h = self.inproj(X)
        h = self.Conv(params, h, fuse)
        return h
