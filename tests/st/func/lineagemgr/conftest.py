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
# ============================================================================
"""The st config."""

import os
import shutil
import sys
import tempfile

import pytest

from ....utils import mindspore

sys.modules['mindspore'] = mindspore

BASE_SUMMARY_DIR = tempfile.mkdtemp(prefix='test_lineage_summary_dir_base_')
SUMMARY_DIR = os.path.join(BASE_SUMMARY_DIR, 'run1')
SUMMARY_DIR_2 = os.path.join(BASE_SUMMARY_DIR, 'run2')
SUMMARY_DIR_3 = os.path.join(BASE_SUMMARY_DIR, 'except_run')

COLLECTION_MODULE = 'TestModelLineage'
API_MODULE = 'TestModelApi'
DATASET_GRAPH = {
    'op_type': 'BatchDataset',
    'op_module': 'minddata.dataengine.datasets',
    'num_parallel_workers': None,
    'drop_remainder': True,
    'batch_size': 10,
    'children': [
        {
            'op_type': 'MapDataset',
            'op_module': 'minddata.dataengine.datasets',
            'num_parallel_workers': None,
            'input_columns': [
                'label'
            ],
            'output_columns': [
                None
            ],
            'operations': [
                {
                    'tensor_op_module': 'minddata.transforms.c_transforms',
                    'tensor_op_name': 'OneHot',
                    'num_classes': 10
                }
            ],
            'children': [
                {
                    'op_type': 'MnistDataset',
                    'shard_id': None,
                    'num_shards': None,
                    'op_module': 'minddata.dataengine.datasets',
                    'dataset_dir': '/home/anthony/MindData/tests/dataset/data/testMnistData',
                    'num_parallel_workers': None,
                    'shuffle': None,
                    'num_samples': 100,
                    'sampler': {
                        'sampler_module': 'minddata.dataengine.samplers',
                        'sampler_name': 'RandomSampler',
                        'replacement': True,
                        'num_samples': 100
                    },
                    'children': []
                }
            ]
        }
    ]
}

def get_module_name(nodeid):
    """Get the module name from nodeid."""
    _, module_name, _ = nodeid.split("::")
    return module_name


def pytest_collection_modifyitems(items):
    """Modify the execution order."""
    split_items = {
        COLLECTION_MODULE: [],
        API_MODULE: []
    }
    for item in items:
        module_name = get_module_name(item.nodeid)
        module_item = split_items.get(module_name)
        if module_item is not None:
            module_item.append(item)
    ordered_items = split_items.get(COLLECTION_MODULE)
    ordered_items.extend(split_items.get(API_MODULE))
    items[:] = ordered_items


@pytest.fixture(scope="session")
def create_summary_dir():
    """Create summary directory."""
    try:
        if os.path.exists(BASE_SUMMARY_DIR):
            shutil.rmtree(BASE_SUMMARY_DIR)
        permissions = os.R_OK | os.W_OK | os.X_OK
        mode = permissions << 6
        if not os.path.exists(BASE_SUMMARY_DIR):
            os.mkdir(BASE_SUMMARY_DIR, mode=mode)
        yield
    finally:
        if os.path.exists(BASE_SUMMARY_DIR):
            shutil.rmtree(BASE_SUMMARY_DIR)
