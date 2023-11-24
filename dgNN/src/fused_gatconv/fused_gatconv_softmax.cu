#include "../util/computeUtil.h"
#include <cuda.h>
#include <torch/types.h>

template <typename DType>
__global__ void gat_sddmmCooKernel(const int lhs_len, const int rhs_len,
                                   const int out_len, const int nnz,
                                   const float negative_slope, const int *row,
                                   const int *col, const DType *lhs,
                                   const DType *rhs, DType *out) {
  int ty = blockIdx.x * blockDim.y + threadIdx.y;
  // process each nnz by one warp 32 threads
  if (ty < nnz) {
    const int src = __ldg(row + ty);
    const int dst = __ldg(col + ty);
    const int eid = ty;

    const DType *lhsoff = lhs + src * lhs_len;
    const DType *rhsoff = rhs + dst * rhs_len;
    DType *outoff = out + eid * out_len;

    // the output feature
    int tx = threadIdx.x; // tx < 32
    if (tx == 0) {
      DType val = lhsoff[0] + rhsoff[0];
      val = LeakyRelu(val, negative_slope);
      outoff[0] = val;
    }
  }
}

__global__ void softMax_SPMM(const int h, const int f, const int *indptr,
                             const int *indices, const float *in_feat,
                             const float *attn_edge, float *out_feat) {
  const int rid = blockIdx.x;                     // loop over row of adj matrix
  const int hid = blockIdx.y;                     // loop over heads
  const int fid = threadIdx.y * 32 + threadIdx.x; // loop over feature dim

  const int lb = indptr[rid]; // row rid elements
  const int hb = indptr[rid + 1];

  const int num_neighbor = hb - lb;
  extern __shared__ float smem[];
  float *neigh_nodes_weight = smem;
  float weightMax = -1e38;
  const int hf = h * f;
  const int hfid = hid * f + fid;

  // init smem
  int loop = (num_neighbor + f - 1) / f;
  for (int j = 0; j < loop; j++) {
    int pid = fid + j * f;
    if (pid < num_neighbor) {
      // TODO add nnz
      neigh_nodes_weight[pid] = attn_edge[lb + pid];
    }
  }
  __syncthreads();

  loop = (num_neighbor + WARP_SIZE - 1) / WARP_SIZE;
  for (int j = 0; j < loop; j++) {
    float weight = -1e38;
    int pid = threadIdx.x + (j << 5);
    if (pid < num_neighbor) {
      weight = neigh_nodes_weight[pid];
    }
    __syncwarp();
    for (int stride = 16; stride > 0; stride >>= 1) {
      weight = max(__shfl_xor_sync(0xffffffff, weight, stride, 32), weight);
    }
    // warpMax = warpReduceMax(weight);
    __syncwarp();
    weightMax = MAX(weight, weightMax);
  }
  // compute the sum of exp
  float expAll = 0;
  for (int j = 0; j < loop; j++) {
    int pid = threadIdx.x + (j << 5); // node need to process in loop j
    float exptmp = 0;
    if (pid < num_neighbor) {
      float weight = neigh_nodes_weight[pid];
      exptmp = exp(weight - weightMax);
    }
    __syncwarp();
    for (int stride = 16; stride > 0; stride >>= 1) {
      exptmp += __shfl_xor_sync(0xffffffff, exptmp, stride, 32);
    }
    __syncwarp();
    expAll += exptmp;
  }

  // compute the output
  float acc = 0;
  float attn_val;
  for (int j = 0; j < num_neighbor; j++) {
    int cid = indices[lb + j];
    float weight = neigh_nodes_weight[j];
    attn_val = exp(weight - weightMax);
    if (fid < f) {
      acc += attn_val * in_feat[cid * hf + hfid];
    }
  }
  if (fid < f)
    // handle the node with no neighbor
    out_feat[rid * hf + hfid] = (expAll != 0) ? acc / expAll : 0;
}

void gat_softmax_inference_launch(int m, int nnz, int h, int f,
                                  int smem_consume, const float *attn_row,
                                  const float *attn_col, const int *indptr,
                                  const int *indices, const int *rows,
                                  float negative_slope, float *attn_edge,
                                  const float *in_feat, float *out_feat) {
  const int ntx = 32;
  const int nty = 8;

  const int nbx = (nnz + nty - 1) / nty;
  const int nby = h;
  const dim3 nblks(nbx, nby);
  const dim3 nthrs(ntx, nty);
  const int smem_size = smem_consume * sizeof(float);

  CUDA_KERNEL_CALL((gat_sddmmCooKernel<float>), nblks, nthrs, 0, h, h, h, nnz,
                   negative_slope, rows, indices, attn_row, attn_col,
                   attn_edge);

  const dim3 nblks2(m, h, 1);
  const dim3 nthrs2(32, (f + 31) / 32, 1);
  CUDA_KERNEL_CALL((softMax_SPMM), nblks2, nthrs2,
                   (smem_consume) * sizeof(float), h, f, indptr, indices,
                   in_feat, attn_edge, out_feat);
}

torch::Tensor
gat_softmax_inference_cuda(int smem_consume, torch::Tensor attn_row,
                           torch::Tensor attn_col, torch::Tensor indptr,
                           torch::Tensor indices, torch::Tensor rows,
                           float negative_slope, torch::Tensor in_feat) {
  const auto m = indptr.size(0) - 1;
  const auto nnz = indices.size(0);
  const auto h = attn_row.size(1);
  const auto f = in_feat.size(2);
  auto devid = attn_row.device().index();
  auto options =
      torch::TensorOptions().dtype(torch::kFloat32).device(torch::kCUDA, devid);
  auto out_feat = torch::empty({m, h, f}, options);
  auto attn_edge = torch::zeros({nnz * h}, options);

  gat_softmax_inference_launch(
      m, nnz, h, f, smem_consume, attn_row.data_ptr<float>(),
      attn_col.data_ptr<float>(), indptr.data_ptr<int>(),
      indices.data_ptr<int>(), rows.data_ptr<int>(), negative_slope,
      attn_edge.data_ptr<float>(), in_feat.data_ptr<float>(),
      out_feat.data_ptr<float>());

  return out_feat;
}
