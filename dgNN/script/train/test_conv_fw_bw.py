import argparse
import pdb

import torch
import torch.nn as nn

import torch.optim as optim

from dgl.dataloading import GraphDataLoader

from dgNN.layers import AGNNConv_forward, preprocess_Hyper_fw_bw, SparseMHA_forward
from dgNN.utils import load_dataset_fn, parser_argument, Timer


def average(list: list) -> float:
    return sum(list) / len(list)


def check_correct(logits, logits_fuse):
    check_same = torch.tensor(
        [all(i) for i in torch.isclose(logits, logits_fuse, atol=0.01)]
    )
    if all(check_same):
        print("the results are the same, success!!!!!!!!!!")
    else:
        print("check fail!!!!!!!!!!!")
        pdb.set_trace()
        exit()


class Model(nn.Module):
    def __init__(
        self,
        layer,
        out_size,
        hidden_size=64,
        num_layers=8,
        num_heads=1,
    ):
        super().__init__()
        # self.in_proj = choose_Inproj(dataset_name, hidden_size)
        self.layers = nn.ModuleList(
            [layer(hidden_size, hidden_size, num_heads) for _ in range(num_layers)]
        )
        self.predictor = nn.Linear(hidden_size, out_size)

    def forward(self, h, params, fuse=False):
        # h = self.in_proj(X)
        for layer in self.layers:
            h = layer(params, h, fuse)

        return self.predictor(h)


@torch.no_grad()
def evaluate(model, dataloader, device, fuse_flag):
    model.train()
    loss_fcn = nn.CrossEntropyLoss()
    with Timer() as t:
        for batched_g in dataloader:
            batched_g = batched_g.to(device)
            params = preprocess_Hyper_fw_bw(batched_g, fuse_flag)
            ## fuse
            y_hat = model(
                batched_g.ndata["feat"],
                params,
                fuse=fuse_flag,
            )
            loss = loss_fcn(y_hat.flatten(), batched_g.ndata["label"].float())

    print(f"evaluate time {t.elapsed_secs:}")


def check_grad(model, dataset, device, args):
    train_dataloader = GraphDataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=True,
    )
    loss_fcn = nn.CrossEntropyLoss()

    model.train()
    total_loss = 0.0
    for iter, batched_g in enumerate(train_dataloader):
        batched_g = batched_g.to(device)
        params = preprocess_Hyper_fw_bw(batched_g, True)
        ## nofuse
        logits = model(batched_g.ndata["feat"], params)
        labels = batched_g.ndata["label"]
        loss = loss_fcn(logits.flatten(), labels.float())
        model.zero_grad()
        loss.backward()

        q_grad = model.layers[0].q_proj.weight.grad
        k_grad = model.layers[0].k_proj.weight.grad
        v_grad = model.layers[0].v_proj.weight.grad

        ## fuse
        logits = model(batched_g.ndata["feat"], params, fuse=True)
        loss = loss_fcn(logits.flatten(), labels.float())
        total_loss += loss.item()
        model.zero_grad()
        loss.backward()

        print(f"iter {iter} check backward correct")
        print("V grad")
        check_correct(v_grad, model.layers[0].v_proj.weight.grad)
        print("Q grad")
        check_correct(q_grad, model.layers[0].q_proj.weight.grad)
        print("K grad")
        check_correct(k_grad, model.layers[0].k_proj.weight.grad)


def only_preprocess(model, dataset, device, args, fuse_flag):
    train_dataloader = GraphDataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=True,
    )
    num_epochs = 20
    epoch_times = []
    batch_gs = []
    for iter, batched_g in enumerate(train_dataloader):
        if iter == 20:
            break
        batch_gs.append(batched_g)

    for epoch in range(num_epochs):
        model.train()
        with Timer() as t:
            for iter, batched_g in enumerate(batch_gs):
                batched_g = batched_g.to(device)
                preprocess_Hyper_fw_bw(batched_g, fuse_flag)

        epoch_time = t.elapsed_secs
        if epoch > 0:
            epoch_times.append(epoch_time)
            print(
                f"epoch {epoch:03d} time {epoch_time:.2f} avg epoch time {average(epoch_times)}"
            )


def train(model, dataset, device, args, fuse_flag):
    train_dataloader = GraphDataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=True,
    )
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    num_epochs = 20
    loss_fcn = nn.BCEWithLogitsLoss()
    epoch_times = []

    batch_gs = []

    for iter, batched_g in enumerate(train_dataloader):
        if iter == 20:
            break
        batched_g.ndata["feat"] = torch.rand((batched_g.num_nodes(), args.dim))
        batch_gs.append(batched_g)

    for epoch in range(num_epochs):
        model.train()
        with Timer() as t:
            for iter, batched_g in enumerate(batch_gs):
                batched_g = batched_g.to(device)
                params = preprocess_Hyper_fw_bw(batched_g, fuse_flag)
                ## fuse
                logits = model(
                    batched_g.ndata["feat"],
                    params,
                    fuse=fuse_flag,
                )
                loss = loss_fcn(logits.flatten(), batched_g.ndata["label"].float())
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
        if epoch > 0:
            epoch_times.append(t.elapsed_secs)
            print(
                f"epoch {epoch:03d} time {t.elapsed_secs:.2f} avg epoch time {average(epoch_times)}"
            )
        evaluate(
            model,
            batch_gs,
            device,
            fuse_flag,
        )
    # model.train()
    # batched_g = batch_gs[0]
    # batched_g = batched_g.to(device)
    # params = preprocess_Hyper_fw_bw(batched_g, fuse_flag)
    # with Timer() as t:
    #     for i in range(100):
    #         ## fuse
    #         logits = model(
    #             batched_g.ndata["feat"],
    #             params,
    #             fuse=fuse_flag,
    #         )
    #         loss = loss_fcn(logits.flatten(), batched_g.ndata["label"].float())
    #         optimizer.zero_grad()
    #         loss.backward()
    #         # optimizer.step()
    # print(
    #     f"time {t.elapsed_secs/100:.2f} "
    # )
    # evaluate(
    #     model,
    #     batch_gs,
    #     device,
    #     fuse_flag,
    # )


if __name__ == "__main__":
    # parse argument
    parser = argparse.ArgumentParser(description="DOTGAT")
    parser.add_argument("--checkgrad", action="store_true")
    parser.add_argument("--num-layers", type=int, default=8)
    args = parser_argument(parser)

    # If CUDA is available, use GPU to accelerate the training, use CPU
    # otherwise.
    dev = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

    # load dataset
    dataset, train_fn = load_dataset_fn(args.dataset, args.data_dir)

    # choose conv layer
    if args.conv == "gt":
        layer = SparseMHA_forward
    elif args.conv == "agnn":
        layer = AGNNConv_forward
    else:
        raise ValueError(f"Unsupported conv {args.conv}")

    # Create model.
    model = Model(
        layer=layer,
        out_size=1,
        hidden_size=args.dim,
        num_heads=args.heads,
        num_layers=args.num_layers,
    ).to(dev)
    print(model)

    # Kick off training.
    if args.checkgrad:
        check_grad(model, dataset, dev, args)
    else:
        print("---------------fused--------------")
        train(model, dataset, dev, args, True)
        print("---------------fused preprocess--------------")
        only_preprocess(model, dataset, dev, args, True)

        print("---------------non-fused--------------")
        train(model, dataset, dev, args, False)
        print("---------------non-fused preprocess--------------")
        only_preprocess(model, dataset, dev, args, False)
