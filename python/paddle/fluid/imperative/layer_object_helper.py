#   Copyright (c) 2019 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import print_function

import copy
import six
from ..framework import Parameter, _in_imperative_mode
from ..param_attr import ParamAttr
from .. import core
from six.moves import zip
from ..layer_helper_base import LayerHelperBase


class LayerObjectHelper(LayerHelperBase):
    def __init__(self, name):
        super(LayerObjectHelper, self).__init__(name, layer_type=name)

    def append_op(self,
                  type=None,
                  inputs=None,
                  outputs=None,
                  attrs=None,
                  stop_gradient=None):
        """append an operator for this layer object.

           Args:
               type: operator type
               inputs: input variable of the operator
               dtype: data type of this parameter
               is_bias: if this is a bias parameter
               default_initializer: set the default initializer for this parameter

        Returns created parameter Variable.
        """
        return self.main_program.current_block().append_op(
            type=type,
            inputs=inputs,
            outputs=outputs,
            attrs=attrs,
            stop_gradient=stop_gradient)

    def _multiple_input(self, inputs_in):
        inputs = inputs_in
        ret = []
        if isinstance(inputs, (list, tuple)):
            for inp in inputs:
                ret.append(self.to_variable(inp))
        else:
            ret.append(self.to_variable(inputs))
        return ret

    # TODO: make it public when we need it
    def _input(self, inputs_in):
        inputs = self._multiple_input(inputs_in)
        if len(inputs) != 1:
            raise "{0} layer only takes one input".format(self.layer_type)
        return inputs[0]

    def _multiple_param_attr(self, length, param_attr_in=None):
        param_attr = param_attr_in
        if isinstance(param_attr, ParamAttr):
            param_attr = [param_attr]

        if len(param_attr) != 1 and len(param_attr) != length:
            raise ValueError("parameter number mismatch")
        elif len(param_attr) == 1 and length != 1:
            tmp = [None] * length
            for i in six.moves.range(length):
                tmp[i] = copy.deepcopy(param_attr[0])
            param_attr = tmp
        return param_attr

    def iter_inputs_and_params(self, inputs_in, param_attr_in=None):
        """Access all inputs and params one by one

           Args:
               inputs_in: inputs to be iter
               param_attr_in: param_attr to be iter

        Returns input, param_attr
        """
        inputs = inputs_in if (inputs_in is not None) else []
        inputs = self._multiple_input(inputs)
        param_attrs = self._multiple_param_attr(len(inputs), param_attr_in)
        for ipt, param_attr in zip(inputs, param_attrs):
            yield ipt, param_attr

    def input_dtype(self, inputs_in):
        """Get input data type

           Args:
               inputs_in: inputs wanted know the data type

        Returns dtype of the input
        """
        inputs = self._multiple_input(inputs_in)
        dtype = None
        for each in inputs:
            if dtype is None:
                dtype = each.dtype
            elif dtype != each.dtype:
                raise ValueError("Data Type mismatch: %d to %d" %
                                 (dtype, each.dtype))
        return dtype

    def get_parameter(self, name):
        """Get parameter specifically

           Args:
               name: parameter's name

        Returns target parameter
        """
        param = self.main_program.global_block().var(name)
        if not isinstance(param, Parameter):
            raise ValueError("no Parameter name %s found" % name)
        return param

    def append_bias_op(self,
                       input_var,
                       dim_start=1,
                       dim_end=None,
                       bias_attr=None):
        """Append bias operator and return its output. If the user does not set bias_attr, append_bias_op will return input_var

            Args:
                input_var: the input variable. The len(input_var.shape) is
                larger or equal than 2.
                dim_start:
                dim_end: the shape of the bias will be
                bias_attr: the bias_attr of it

        Return the Variable of after append bias op
        """
        size = list(input_var.shape[dim_start:dim_end])
        bias_attr = bias_attr
        if not bias_attr:
            return input_var

        b = self.create_parameter(
            attr=bias_attr, shape=size, dtype=input_var.dtype, is_bias=True)
        tmp = self.create_variable_for_type_inference(dtype=input_var.dtype)
        self.append_op(
            type='elementwise_add',
            inputs={'X': [input_var],
                    'Y': [b]},
            outputs={'Out': [tmp]},
            attrs={'axis': dim_start})
        return tmp

    # TODO: this should not be called anymore after all activation func move to Layers
    def append_activation(self,
                          input_var,
                          act=None,
                          use_cudnn=None,
                          use_mkl_dnn=None):
        """Append activation

            Args:
                input_var: the input variable. The len(input_var.shape) is
                larger or equal than 2.
                act: activation type
                use_mkl_dnn: if use mkldnn
                use_cudnn: if use cudnn

        Return the Variable of after append activation
        """
        act = act
        if act is None:
            return input_var
        if isinstance(act, six.string_types):
            act = {'type': act}
        else:
            raise TypeError(str(act) + " should be unicode or str")

        if (use_cudnn is not None) and use_cudnn:
            act['use_cudnn'] = use_cudnn
        if (use_mkl_dnn is not None) and use_mkl_dnn:
            act['use_mkldnn'] = use_mkl_dnn
        act_type = act.pop('type')

        tmp = input_var
        # NOTE(dzhwinter): some activation support inplace compution.
        # NOTE(minqiyang): currently, we don't support inplace in imperative mode
        if not _in_imperative_mode() and core.IsInplace(act_type):
            tmp = input_var
        else:
            tmp = self.create_variable_for_type_inference(dtype=input_var.dtype)
        self.append_op(
            type=act_type,
            inputs={"X": [input_var]},
            outputs={"Out": [tmp]},
            attrs=act)
        return tmp

    def is_instance(self, param, cls):
        """Check if the input parameter is instance of input class

            Args:
                param: parameter to be check
                cls: class of the parameter

        Return result of the check (True or False)
        """
        param = param
        if not isinstance(param, cls):
            raise TypeError("The input {0} parameter of method {1} must be {2}",
                            param, self.layer_type, cls.__name__)
