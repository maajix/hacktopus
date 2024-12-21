from typing import List, Dict, Any


class Flow:
    """
    This class is used to store the parsed information from the FlowParser
    """

    def __init__(self):
        self._stage_information: List[List[Dict]] = []
        self._state_options: List[List[Dict]] = []
        self._execution_dict: Dict[str, list] = {}
        self._yaml: Dict[str, Any] = {}

    def set_stage_information(self, stage_information: List[List[Dict]]):
        """
        Set the stage information for the flow

        :Example:
        >>> Flow.set_stage_information(stage_information)
        """
        self._stage_information = stage_information

    def set_state_options(self, state_options: List[List[Dict]]):
        """
        Set the state options for the flow

        :Example:
        >>> Flow.set_state_options(state_options)
        """
        self._state_options = state_options

    def set_execution_dict(self, execution_array: Dict[str, list]):
        """
        Set the execution dictionary for the flow

        :Example:
        >>> Flow.set_execution_dict(execution_array)
        """
        self._execution_dict = execution_array

    def set_yaml(self, YAML: Dict):
        """
        Set the yaml file path for the flow

        :Example:
        >>> Flow.set_yaml(YAML)
        """
        self._yaml = YAML

    @property
    def stage_information(self):
        """
        Get the stage information for the flow

        :Example:
        >>> Flow.stage_information
        """
        return self._stage_information

    @property
    def state_options(self):
        """
        Get the state options for the flow

        :Example:
        >>> Flow.state_options
        """
        return self._state_options

    @property
    def execution_dict(self):
        """
        Get the execution dictionary for the flow

        :Example:
        >>> Flow.execution_dict
        """
        return self._execution_dict

    @property
    def yaml(self):
        """
        Get the yaml file path for the flow

        :Example:
        >>> Flow.yaml
        """
        return self._yaml
