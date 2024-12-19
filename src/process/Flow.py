from typing import List, Dict


class Flow:
    _stage_information = None
    _state_options = None
    _execution_dict = None
    _yaml = None

    def set_stage_information(self, stage_information: List[List[Dict]]):
        self._stage_information = stage_information

    def set_state_options(self, state_options: List[List[Dict]]):
        self._state_options = state_options

    def set_execution_dict(self, execution_array: Dict[str, list]):
        self._execution_dict = execution_array

    def set_yaml(self, yaml_file: str):
        self._yaml = yaml_file

    def get_stage_information(self):
        return self._stage_information

    def get_state_options(self):
        return self._state_options

    def get_execution_dict(self):
        return self._execution_dict

    def get_yaml(self):
        return self._yaml
