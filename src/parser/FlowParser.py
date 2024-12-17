import json
import os
from pathlib import Path
from typing import Any, Dict

import yaml


class ParsedFlow:
    def __init__(self, data: dict):
        self.data = data

    def pretty(self) -> str:
        return json.dumps(self.data, indent=4)

    def __str__(self) -> str:
        return json.dumps(self.data)


class FlowMeta:
    def __init__(self, data: dict):
        self.data = data

    def version(self):
        return self.data['version']

    def name(self):
        return self.data['name']

    def tags(self):
        return self.data['tags']

    def variables(self):
        return self.data['variables']

    def stages(self):
        return self.data['stages']


class FlowParser:
    """
    Class to parse a YAML flow file into its components
    """
    _ROOT_DIR = Path(__file__).parent.parent.parent.absolute()
    _FLOWS_DIR = Path(_ROOT_DIR, "flows")
    _META = None
    _FLOW_FILE = None
    _IS_VALID_FLOW = None
    _STAGE_INFO = None
    _OPTIONS = None

    def __init__(self, flow_file):
        self._FLOW_FILE = flow_file
        self._parse_flow_file()
        self._validate_flow()
        self._extract_stage_information()

    def _read_json(self) -> ParsedFlow:
        _flow_path = os.path.join(self._FLOWS_DIR, self._FLOW_FILE)
        if os.path.exists(_flow_path):
            with open(_flow_path, 'r') as f:
                data = yaml.safe_load(f)
                parsed_data = data if data is not None else {}
                return ParsedFlow(parsed_data)
        else:
            print(f"Flow file '{self._FLOW_FILE}' does not exist.")
            return ParsedFlow({})

    def _parse_flow_file(self) -> FlowMeta:
        try:
            self._META = FlowMeta(self._read_json().data)
        except Exception as e:
            print(f"Failed to parse flow file '{self._FLOW_FILE}'. Error: {e}")
        return self._META

    def _validate_flow(self) -> bool:
        try:
            if not self._META.version():
                raise ValueError(f"[ERR] Could not validate version '{self._META.version()}'")
            if not self._META.tags():
                print(f"[INF] No tags have been defined")
            if not self._META.variables():
                print(f"[INF] No variables have been defined")
            if not self._META.stages():
                raise ValueError(f"[ERR] No stages have been defined")
        except yaml.YAMLError as exc:
            raise f"[ERR] Invalid YAML syntax. {exc}"
        return True

    def _extract_stage_information(self):
        tmp_order, tmp_options, stage_options, stage_info = [], [], [], []

        for stage in self._META.stages():
            for options in self._META.stages()[stage]:
                if options == "tasks":
                    continue
                tmp_options.append({options: self._META.stages()[stage][options]})

            if len(tmp_options) > 0:
                stage_options.append(tmp_options)
                tmp_options = []
            else:
                continue

            for task in self._META.stages()[stage]["tasks"]:
                tmp_order.append(task)

            stage_info.append(tmp_order)
            tmp_order = []

        self._STAGE_INFO = stage_info
        self._OPTIONS = stage_options
        return True

    def get_execution_information(self) -> list[list[Dict]]:
        return self._STAGE_INFO

    def get_execution_options(self) -> list[list[Dict]]:
        return self._OPTIONS



