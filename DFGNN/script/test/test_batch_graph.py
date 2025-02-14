import argparse
import os, pickle

import torch

from DFGNN.layers import load_graphconv_layer, load_prepfunc, Model
from DFGNN.utils import load_dataset_fn, mkdir, parser_argument, train_profile
from dgl.dataloading import GraphDataLoader


def test_format(args, dev, train_dataloader, train_fn):
    graphconv_layer = load_graphconv_layer(args)
    preprocess_func = load_prepfunc(args)
    model = Model(args.dataset, Conv=graphconv_layer, hidden_size=args.dim)
    model = model.to(dev)
    print("model", model)
    # profile mode
    if args.profile:
        train_profile(
            preprocess_func,
            model,
            train_dataloader,
            dev,
            args,
            dim=args.dim,
        )
    # normal run
    else:
        time_no_fuse, time_fuse = train_fn(
            preprocess_func, model, train_dataloader, dev
        )
        print("----------------------Result------------------------")
        print(
            "no-fuse average time {:.4f} ms".format(
                sum(time_no_fuse[:-1]) / (len(time_no_fuse) - 1)
            )
        )
        print(
            "fuse average time {:.4f} ms".format(
                sum(time_fuse[:-1]) / (len(time_fuse) - 1)
            )
        )
        print(sum(time_no_fuse[:-1]) / (len(time_no_fuse) - 1))
        print(sum(time_fuse[:-1]) / (len(time_fuse) - 1))

        if args.store_result:
            result_dir = os.path.join(os.getcwd(), "dataset", args.dataset, args.conv)
            mkdir(result_dir)
            result_path = os.path.join(
                result_dir,
                f"{args.format}_dim{args.dim}_bs{args.batch_size}_result.pkl",
            )
            print("store result at", result_path)
            with open(result_path, "wb") as f:
                pickle.dump([time_no_fuse[:-1], time_fuse[:-1]], f)
                print("-----------dump run result--------------------")


def main(args):
    # If CUDA is available, use GPU to accelerate the training, use CPU
    # otherwise.
    dev = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

    # init model
    dataset, train_fn = load_dataset_fn(args.dataset, args.data_dir)

    train_dataloader = GraphDataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=False,
    )
    if args.format == "all":
        if args.conv == "gat":
            formats = [
                "csr",
                "pyg",
                "cugraph",
                "softmax",
                "hyper_v2",
            ]
        else:
            formats = ["csr", "pyg", "cugraph", "softmax", "hyper"]
        for format in formats:
            args.format = format
            print("format", args.format)
            test_format(args, dev, train_dataloader, train_fn)
    else:
        test_format(args, dev, train_dataloader, train_fn)


if __name__ == "__main__":
    # parse argument
    parser = argparse.ArgumentParser(description="DOTGAT")
    args = parser_argument(parser)
    main(args)
