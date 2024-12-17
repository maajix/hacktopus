from typing import List, Dict


class Flow:
    _stage_information = None
    _state_options = None

    def set_stage_information(self, stage_information: List[List[Dict]]):
        self._stage_information = stage_information

    def set_state_options(self, state_options: List[List[Dict]]):
        self._state_options = state_options

    def get_stage_information(self):
        return self._stage_information

    def get_state_options(self):
        return self._state_options
