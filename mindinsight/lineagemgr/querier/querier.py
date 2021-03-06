# Copyright 2020 Huawei Technologies Co., Ltd
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
"""This file is used to define lineage info querier."""
import enum
import functools
import operator
import os

from mindinsight.lineagemgr.common.exceptions.exceptions import \
    LineageParamTypeError, LineageSummaryAnalyzeException, \
    LineageEventNotExistException, LineageQuerierParamException, \
    LineageSummaryParseException, LineageEventFieldNotExistException
from mindinsight.lineagemgr.common.log import logger
from mindinsight.lineagemgr.querier.query_model import LineageObj, FIELD_MAPPING
from mindinsight.lineagemgr.summary.lineage_summary_analyzer import \
    LineageSummaryAnalyzer


@enum.unique
class ConditionParam(enum.Enum):
    """
    Filtering and sorting field names.

    `LIMIT` represents the number of lineage info per page. `OFFSET` represents
    page number. `SORTED_NAME` means to sort by this field. `SORTED_TYPE` means
    ascending or descending.
    """
    LIMIT = 'limit'
    OFFSET = 'offset'
    SORTED_NAME = 'sorted_name'
    SORTED_TYPE = 'sorted_type'
    LINEAGE_TYPE = 'lineage_type'

    @classmethod
    def is_condition_type(cls, value):
        """
        Judge that the input param is one of field names in the class.

        Args:
            value (str): The input field name.

        Returns:
            bool, `True` if the input field name in the class, else `False`.
        """
        return value in cls._value2member_map_


@enum.unique
class ExpressionType(enum.Enum):
    """
    Filter condition name definition.

    `EQ` means `==`. `LT` means `<`. `GT` means `>`. `LE` means `<=`. `GE` means
    `>=`. `IN` means filter value in the specified list.
    """
    EQ = 'eq'
    LT = 'lt'
    GT = 'gt'
    LE = 'le'
    GE = 'ge'
    IN = 'in'

    @classmethod
    def is_valid_exp(cls, key):
        """
        Judge that the input param is one of filter condition names in the class.

        Args:
            key (str): The input filter condition name.

        Returns:
            bool, `True` if the input filter condition name in the class,
            else `False`.
        """
        return key in cls._value2member_map_

    @classmethod
    def is_match(cls, except_key, except_value, actual_value):
        """
        Determine whether the value meets the expected requirement.

        Args:
            except_key (str): The expression key.
            except_value (Union[str, int, float, list, tuple]): The expected
                value.
            actual_value (Union[str, int, float]): The actual value.

        Returns:
            bool, `True` if the actual value meets the expected requirement,
            else `False`.
        """
        if actual_value is None and except_key in [cls.LT.value, cls.GT.value,
                                                   cls.LE.value, cls.GE.value]:
            return False

        if except_key == cls.IN.value:
            state = operator.contains(except_value, actual_value)
        else:
            state = getattr(operator, except_key)(actual_value, except_value)
        return state


@enum.unique
class LineageFilterKey(enum.Enum):
    """Summary lineage information filter key."""
    METRIC = 'metric'
    HYPER_PARAM = 'hyper_parameters'
    ALGORITHM = 'algorithm'
    TRAIN_DATASET = 'train_dataset'
    VALID_DATASET = 'valid_dataset'
    MODEL = 'model'
    DATASET_GRAPH = 'dataset_graph'

    @classmethod
    def is_valid_filter_key(cls, key):
        """
        Judge that the input param is one of field names in the class.

        Args:
            key (str): The input field name.

        Returns:
            bool, `True` if the input field name in the class, else `False`.
        """
        return key in cls._value2member_map_

    @classmethod
    def get_key_list(cls):
        """
        Get the filter key name list.

        Returns:
            list[str], the filter key name list.
        """
        return [member.value for member in cls]


@enum.unique
class LineageType(enum.Enum):
    """Lineage search type."""
    DATASET = 'dataset'
    MODEL = 'model'


class Querier:
    """
    The querier of model lineage information.

    The class provides model lineage information query function. The information
    includes hyper parameters, train dataset, algorithm, model information,
    metric, valid dataset, etc.

    The class also provides search and sorting capabilities about model lineage
    information. You can search and sort by the specified condition.
    The condition explain in `ConditionParam` and `ExpressionType` class.
    See the method `filter_summary_lineage` for supported fields.

    Args:
        summary_path (Union[str, list[str]]): The single summary log path or
            a list of summary log path.

    Raises:
        LineageParamTypeError: If the input parameter type is invalid.
        LineageQuerierParamException: If the input parameter value is invalid.
        LineageSummaryParseException: If all summary logs parsing failed.
    """
    def __init__(self, summary_path):
        self._lineage_objects = []
        self._index_map = {}
        self._parse_failed_paths = []
        self._parse_summary_logs(summary_path)
        self._size = len(self._lineage_objects)

    def get_summary_lineage(self, summary_dir=None, filter_keys=None):
        """
        Get summary lineage information.

        If a summary dir is specified, the special summary lineage information
        will be found. If the summary dir is `None`, all summary lineage
        information will be found.

        Returns the content corresponding to the specified field in the filter
        key. The contents of the filter key include `metric`, `hyper_parameters`,
        `algorithm`, `train_dataset`, `valid_dataset` and `model`. You can
        specify multiple filter keys in the `filter_keys`. If the parameter is
        `None`, complete information will be returned.

        Args:
            summary_dir (Union[str, None]): Summary log dir. Default: None.
            filter_keys (Union[list[str], None]): Filter keys. Default: None.

        Returns:
            list[dict], summary lineage information.
        """
        self._parse_fail_summary_logs()

        if filter_keys is None:
            filter_keys = LineageFilterKey.get_key_list()
        else:
            for key in filter_keys:
                if not LineageFilterKey.is_valid_filter_key(key):
                    raise LineageQuerierParamException(
                        filter_keys, 'The filter key {} is invalid.'.format(key)
                    )

        if summary_dir is None:
            result = [
                item.get_summary_info(filter_keys) for item in self._lineage_objects
            ]
        else:
            index = self._index_map.get(summary_dir)
            if index is None:
                raise LineageQuerierParamException(
                    'summary_dir',
                    'Summary dir {} does not exist.'.format(summary_dir)
                )
            lineage_obj = self._lineage_objects[index]
            result = [lineage_obj.get_summary_info(filter_keys)]
        return result

    def filter_summary_lineage(self, condition=None):
        """
        Filter and sort lineage information based on the specified condition.

        See `ConditionType` and `ExpressionType` class for the rule of filtering
        and sorting. The filtering and sorting fields are defined in
        `FIELD_MAPPING` or prefixed with `metric_`.

        If the condition is `None`, all model lineage information will be
        returned.

        Args:
            condition (Union[dict, None]): Filter and sort condition.
                Default: None.

        Returns:
            dict, filtered and sorted model lineage information.
        """
        def _filter(lineage_obj: LineageObj):
            for condition_key, condition_value in condition.items():
                if ConditionParam.is_condition_type(condition_key):
                    continue
                if self._is_valid_field(condition_key):
                    raise LineageQuerierParamException(
                        'condition',
                        'The field {} not supported'.format(condition_key)
                    )

                value = lineage_obj.get_value_by_key(condition_key)
                for exp_key, exp_value in condition_value.items():
                    if not ExpressionType.is_valid_exp(exp_key):
                        raise LineageQuerierParamException(
                            'condition',
                            'The expression {} not supported.'.format(exp_key)
                        )
                    if not ExpressionType.is_match(exp_key, exp_value, value):
                        return False
            return True

        def _cmp(obj1: LineageObj, obj2: LineageObj):
            value1 = obj1.get_value_by_key(sorted_name)
            value2 = obj2.get_value_by_key(sorted_name)

            if value1 is None and value2 is None:
                cmp_result = 0
            elif value1 is None:
                cmp_result = -1
            elif value2 is None:
                cmp_result = 1
            else:
                cmp_result = (value1 > value2) - (value1 < value2)

            return cmp_result

        self._parse_fail_summary_logs()

        if condition is None:
            condition = {}
        result = list(filter(_filter, self._lineage_objects))

        if ConditionParam.SORTED_NAME.value in condition:
            sorted_name = condition.get(ConditionParam.SORTED_NAME.value)
            if self._is_valid_field(sorted_name):
                raise LineageQuerierParamException(
                    'condition',
                    'The sorted name {} not supported.'.format(sorted_name)
                )
            sorted_type = condition.get(ConditionParam.SORTED_TYPE.value)
            reverse = sorted_type == 'descending'
            result = sorted(
                result, key=functools.cmp_to_key(_cmp), reverse=reverse
            )

        offset_result = self._handle_limit_and_offset(condition, result)

        search_type = condition.get(ConditionParam.LINEAGE_TYPE.value)
        lineage_info = {
            'object': [
                item.to_dataset_lineage_dict() if search_type == LineageType.DATASET.value
                else item.to_filtration_dict() for item in offset_result
            ],
            'count': len(result)
        }

        return lineage_info

    def _is_valid_field(self, field_name):
        """
        Check if field name is valid.

        Args:
            field_name (str): Field name.

        Returns:
            bool, `True` if the field name is valid, else `False`.
        """
        return field_name not in FIELD_MAPPING and not field_name.startswith('metric_')

    def _handle_limit_and_offset(self, condition, result):
        """
        Handling the condition of `limit` and `offset`.

        Args:
            condition (dict): Filter and sort condition.
            result (list[LineageObj]): Filtered and sorted result.

        Returns:
            list[LineageObj], paginated result.
        """
        offset = 0
        limit = 10
        if ConditionParam.OFFSET.value in condition:
            offset = condition.get(ConditionParam.OFFSET.value)
        if ConditionParam.LIMIT.value in condition:
            limit = condition.get(ConditionParam.LIMIT.value)
        if ConditionParam.OFFSET.value not in condition \
                and ConditionParam.LIMIT.value not in condition:
            offset_result = result
        else:
            offset_result = result[offset * limit: limit * (offset + 1)]
        return offset_result

    def _parse_summary_logs(self, summary_path):
        """
        Parse summary logs.

        Args:
            summary_path (Union[str, list[str]]): The single summary log path or
                a list of summary log path.
        """
        if not summary_path:
            raise LineageQuerierParamException(
                'summary_path', 'The summary path is empty.'
            )
        if isinstance(summary_path, str):
            self._parse_summary_log(summary_path, 0)
        elif isinstance(summary_path, list):
            index = 0
            for path in summary_path:
                parse_result = self._parse_summary_log(path, index)
                if parse_result:
                    index += 1
        else:
            raise LineageParamTypeError('Summary path is not str or list.')

        if self._parse_failed_paths:
            logger.info('Parse failed paths: %s', str(self._parse_failed_paths))

        if not self._lineage_objects:
            raise LineageSummaryParseException()

    def _parse_summary_log(self, log_path, index: int, is_save_fail_path=True):
        """
        Parse the single summary log.

        Args:
            log_path (str): The single summary log path.
            index (int): TrainInfo instance index in the train info list.
            is_save_fail_path (bool): Set whether to save the failed summary
                path. Default: True.

        Returns:
            bool, `True` if parse summary log success, else `False`.
        """
        log_dir = os.path.dirname(log_path)
        try:
            lineage_info = LineageSummaryAnalyzer.get_summary_infos(log_path)
            lineage_obj = LineageObj(
                log_dir,
                train_lineage=lineage_info.train_lineage,
                evaluation_lineage=lineage_info.eval_lineage,
                dataset_graph=lineage_info.dataset_graph
            )
            self._lineage_objects.append(lineage_obj)
            self._add_dataset_mark()
            self._index_map[log_dir] = index
            return True
        except (LineageSummaryAnalyzeException,
                LineageEventNotExistException,
                LineageEventFieldNotExistException):
            if is_save_fail_path:
                self._parse_failed_paths.append(log_path)
            return False

    def _parse_fail_summary_logs(self):
        """Parse fail summary logs."""
        if self._parse_failed_paths:
            failed_paths = []
            for path in self._parse_failed_paths:
                parse_result = self._parse_summary_log(path, self._size, False)
                if parse_result:
                    self._size += 1
                else:
                    failed_paths.append(path)
            self._parse_failed_paths = failed_paths

    def _add_dataset_mark(self):
        """Add dataset mark into LineageObj."""
        # give a dataset mark for each dataset graph in lineage information
        marked_dataset_group = {'1': None}
        for lineage in self._lineage_objects:
            dataset_mark = '0'
            for dataset_graph_mark, marked_dataset_graph in marked_dataset_group.items():
                if marked_dataset_graph == lineage.dataset_graph:
                    dataset_mark = dataset_graph_mark
                    break
            # if no matched, add the new dataset graph into group
            if dataset_mark == '0':
                dataset_mark = str(int(max(marked_dataset_group.keys())) + 1)
                marked_dataset_group.update({
                    dataset_mark:
                        lineage.dataset_graph
                })
            lineage.dataset_mark = dataset_mark
