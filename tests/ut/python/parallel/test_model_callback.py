# Copyright 2019 Huawei Technologies Co., Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from mindspore.train import Model, ParallelMode
from mindspore.nn.loss import SoftmaxCrossEntropyWithLogits
from mindspore.nn.optim.momentum import Momentum
from mindspore import Tensor
import mindspore as ms
import numpy as np
from mindspore.ops import operations as P
import mindspore.nn as nn
from mindspore.common.parameter import Parameter
from tests.dataset_mock import MindData
from mindspore import context
from mindspore.parallel._utils import _reset_op_id
from mindspore.train.callback import Callback


context.set_context(mode=context.GRAPH_MODE)


class Dataset(MindData):
    def __init__(self, predict, label, length=3):
        super(Dataset, self).__init__(size=length)
        self.predict = predict
        self.label = label
        self.index = 0
        self.length = length

    def __iter__(self):
        return self

    def __next__(self):
        if self.index >= self.length:
            raise StopIteration
        self.index += 1
        return self.predict, self.label

    def reset(self):
        self.index = 0


class AllToAllNet(nn.Cell):
    def __init__(self, strategy1):
        super(AllToAllNet, self).__init__()
        self.matmul = P.MatMul().set_strategy(((1, 1), (1, 8)))
        self.matmul_weight = Parameter(Tensor(np.ones([128, 256]), dtype=ms.float32), name="weight")
        self.transpose1 = P.Transpose().set_strategy(strategy1)

    def construct(self, x):
        x = self.matmul(x, self.matmul_weight)
        x = self.transpose1(x, (1, 0))
        return x


def all_to_all_net(strategy1):
    return AllToAllNet(strategy1=strategy1)


class ContextCallback(Callback):
    def begin(self, run_context):
        parallel_mode = context.get_auto_parallel_context("parallel_mode")
        assert parallel_mode == ParallelMode.STAND_ALONE

    def epoch_begin(self, run_context):
        parallel_mode = context.get_auto_parallel_context("parallel_mode")
        assert parallel_mode == ParallelMode.STAND_ALONE

    def epoch_end(self, run_context):
        parallel_mode = context.get_auto_parallel_context("parallel_mode")
        assert parallel_mode == ParallelMode.STAND_ALONE

    def step_begin(self, run_context):
        parallel_mode = context.get_auto_parallel_context("parallel_mode")
        assert parallel_mode == ParallelMode.STAND_ALONE

    def step_end(self, run_context):
        parallel_mode = context.get_auto_parallel_context("parallel_mode")
        assert parallel_mode == ParallelMode.STAND_ALONE

    def end(self, run_context):
        parallel_mode = context.get_auto_parallel_context("parallel_mode")
        assert parallel_mode == ParallelMode.STAND_ALONE


def all_to_all_common(strategy1):
    learning_rate = 0.1
    momentum = 0.9
    epoch_size = 2

    context.reset_auto_parallel_context()
    context.set_auto_parallel_context(parallel_mode=ParallelMode.SEMI_AUTO_PARALLEL, device_num=8)
    predict = Tensor(np.ones([32, 128]), dtype=ms.float32)
    label = Tensor(np.ones([32]), dtype=ms.int32)
    dataset = Dataset(predict, label, 2)
    net = all_to_all_net(strategy1)

    loss = SoftmaxCrossEntropyWithLogits(is_grad=False, sparse=True)
    loss.softmax_cross_entropy.set_strategy(((8, 1), (8, 1)))
    opt = Momentum(net.trainable_params(), learning_rate, momentum)
    model = Model(net, loss, opt)

    context_callback = ContextCallback()

    model.train(epoch_size, dataset, dataset_sink_mode=False, callbacks=[context_callback])

    parallel_mode = context.get_auto_parallel_context("parallel_mode")
    assert parallel_mode == ParallelMode.SEMI_AUTO_PARALLEL

    context.set_auto_parallel_context(parallel_mode=ParallelMode.AUTO_PARALLEL, device_num=8)
    model.train(epoch_size, dataset, dataset_sink_mode=False, callbacks=[context_callback])
    parallel_mode = context.get_auto_parallel_context("parallel_mode")
    assert parallel_mode == ParallelMode.AUTO_PARALLEL

    context.reset_auto_parallel_context()


def test_model_callback():
    strategy1 = ((8, 1), )
    _reset_op_id()
    all_to_all_common(strategy1)



