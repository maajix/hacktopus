import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

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

    @property
    def version(self):
        return self.data.get("version")

    @property
    def name(self):
        return self.data.get("name")

    @property
    def tags(self):
        return self.data.get("tags")

    @property
    def variables(self):
        return self.data.get("variables")

    @property
    def stages(self):
        return self.data.get("stages")


@dataclass
class FlowFileHandler:
    flow_filename: str
    root_dir: str = Path(__file__).parent.parent.parent.parent.absolute()
    flow_dir: str = Path(root_dir, "flows")


@dataclass
class FlowHandler:
    metadata: FlowMeta = None
    is_valid: bool = None
    stage_info: list[list[Dict]] = None
    options: list[list[Dict]] = None
    parsed_yaml_data: dict = None


class FlowParser:
    """
    Class to parse a YAML flow file into its components
    """
    flow_file_handler: FlowFileHandler
    flow_handler: FlowHandler

    def __init__(self, flow_file):
        self.flow_file_handler = FlowFileHandler(flow_filename=flow_file)
        self.flow_handler = FlowHandler()
        self.flow_handler.parsed_yaml_data = self.parse_flow_file().data
        self.validate_flow()
        self.extract_stage_information()

    def read_json(self) -> ParsedFlow:
        """
        Read the flow file and return the parsed JSON in a ParsedFlow object

        :Example:
        >>> FlowParser("concept.yaml").read_json().data
        {'version': '1.0', 'name': 'Gather available URLs from Target',...}
        """
        __flow_path: str = os.path.join(self.flow_file_handler.flow_dir, self.flow_file_handler.flow_filename)
        if os.path.exists(__flow_path):
            with open(__flow_path, 'r') as f:
                return ParsedFlow(yaml.safe_load(f))
        else:
            print(f"Flow file '{self.flow_file_handler.flow_filename}' does not exist.")
            return ParsedFlow({})

    def parse_flow_file(self) -> FlowMeta:
        """
        Parse the flow file and return the FlowMeta object

        :Example:
        >>> FlowParser("concept.yaml").parse_flow_file().version
        '1.0
        """
        try:
            self.flow_handler.metadata = FlowMeta(self.read_json().data)
        except Exception as e:
            print(f"Failed to parse flow file '{self.flow_file_handler.flow_filename}'. Error: {e}")
        return self.flow_handler.metadata

    def validate_flow(self) -> bool:
        """
        Validate the flow file and return True if the flow is valid

        :Example:
        >>> FlowParser("concept.yaml").validate_flow()
        True
        """
        try:
            if not self.flow_handler.metadata.version:
                print(f"[ERR] Wrong or no version specified '{self.flow_handler.metadata.version}'")
                exit(1)
            if not self.flow_handler.metadata.tags:
                print(f"[INF] No tags have been defined")
            if not self.flow_handler.metadata.variables:
                print(f"[INF] No variables have been defined")
            if not self.flow_handler.metadata.stages:
                print(f"[ERR] No stages have been defined")
                exit(1)
        except yaml.YAMLError as exc:
            raise f"[ERR] Invalid YAML syntax. {exc}"
        return True

    def extract_stage_information(self) -> None:
        """
        Extract the stage information from the flow file and store it in the FlowHandler object

        :Example:
        >>> FlowParser("concept.yaml").extract_stage_information()
        """
        tmp_order, tmp_options, stage_options, stage_info = [], [], [], []

        for stage in self.flow_handler.metadata.stages:
            try:
                try:
                    for task in self.flow_handler.metadata.stages[stage]["tasks"]:
                        tmp_order.append(task)
                except KeyError:
                    print(f"[ERR] No tasks defined for stage '{stage}'")
                    exit(1)

                for options in self.flow_handler.metadata.stages[stage]:
                    if "description" not in self.flow_handler.metadata.stages[stage]:
                        print(f"[ERR] No description defined for stage '{stage}'")
                        exit(1)
                    if options == "tasks":
                        continue
                    tmp_options.append({options: self.flow_handler.metadata.stages[stage][options]})

                if len(tmp_options) > 0:
                    stage_options.append(tmp_options)
                    tmp_options = []
                else:
                    continue

                stage_info.append(tmp_order)
                tmp_order = []
            except KeyError:
                print(f"[ERR] Stage '{stage}' is not defined")
                exit(1)

        self.flow_handler.stage_info = stage_info
        self.flow_handler.options = stage_options

    @property
    def execution_information(self) -> list[list[Dict]]:
        """
        Return the stage information from the flow file

        :Example:
        >>> FlowParser("concept.yaml").execution_information
        [{'alias': 'parmspider:get_params'}, {'command': 'echo "Hello World"'}, {...
        """
        return self.flow_handler.stage_info

    @property
    def execution_options(self) -> list[list[Dict]]:
        """
        Return the stage options from the flow file

        :Example:
        >>> FlowParser("concept.yaml").execution_options
        [{'description': 'Gather available URLs from Target', 'parallel': True}, {...
        """
        return self.flow_handler.options

    @property
    def yaml(self) -> dict:
        """
        Return the parsed YAML data from the flow file

        :Example:
        >>> FlowParser("concept.yaml").yaml
        {'version': '1.0', 'name': 'Gather available URLs from Target',...}
        """
        return self.flow_handler.parsed_yaml_data
