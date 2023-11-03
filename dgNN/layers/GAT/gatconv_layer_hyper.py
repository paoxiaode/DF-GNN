from dgNN.operators.fused_gatconv import GATConvFuse_inference_hyper
from dgNN.utils import Timer

from .gatconv_layer import GATConvDGL


class GATConv_hyper(GATConvDGL):
    def forward(self, params, feat, fuse=False):
        N = len(feat)
        A, indptr, indices, rows, _, smem_consume = params
        if fuse:
            for i in range(3):
                h = self.W(feat).view(-1, self.out_size, self.num_heads)
                attn_row = (self.a_l * h).sum(dim=1)
                attn_col = (self.a_r * h).sum(dim=1)
                h = h.view(-1, self.num_heads, self.out_size)
                out = GATConvFuse_inference_hyper(
                    smem_consume,
                    attn_row,
                    attn_col,
                    indptr,
                    indices,
                    rows,
                    self.negative_slope,
                    h,
                )
            with Timer() as t:
                for i in range(100):
                    h = self.W(feat).view(-1, self.out_size, self.num_heads)
                    attn_row = (self.a_l * h).sum(dim=1)
                    attn_col = (self.a_r * h).sum(dim=1)
                    h = h.view(-1, self.num_heads, self.out_size)
                    out = GATConvFuse_inference_hyper(
                        smem_consume,
                        attn_row,
                        attn_col,
                        indptr,
                        indices,
                        rows,
                        self.negative_slope,
                        h,
                    )
        else:
            for i in range(3):
                out = self.forward_nofuse(A, feat)

            with Timer() as t:
                for i in range(100):
                    out = self.forward_nofuse(A, feat)

        elapsed_time = t.elapsed_secs / 100
        return out.reshape(N, -1), elapsed_time * 1000
