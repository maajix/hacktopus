import json
import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List
import yaml
from process.CLIExecutionManager import CommandExecutionManager as CLIEx


class ParsedFlow:
    """
    Helper class
    """

    def __init__(self, data: dict):
        self.data = data

    def pretty(self) -> str:
        return json.dumps(self.data, indent=4)

    def __str__(self) -> str:
        return json.dumps(self.data)


class FlowMeta:
    """
    Dataclass to handle the flow metadata of YAML file
    """

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


class ToolEnums(Enum):
    """
    Enum to handle the different tool types
    """
    TOOLS_DIR_NAME = "tools"
    ALIAS_FILE = "aliases.yaml"


@dataclass(slots=True)
class FlowFileHandler:
    """
    Dataclass to handle the flow file paths
    """
    flow_filename: str
    alias_content: dict = None
    root_dir: str = Path(__file__).parent.parent.parent.absolute()
    flow_dir: str = Path(root_dir, "flows")
    tool_dir: str = Path(root_dir, ToolEnums.TOOLS_DIR_NAME.value)


@dataclass(slots=True)
class FlowHandler:
    """
    Dataclass to handle the flow data
    """
    metadata: FlowMeta = None
    is_valid: bool = None
    stage_info: list[list[Dict]] = None
    options: list[list[Dict]] = None
    parsed_yaml_data: dict = None
    alias_command: str = None


class Flow:
    """
    This class is used to store the parsed information from the FlowParser
    """

    def __init__(self, flow_file: str):
        self._execution_dict = None
        self.flow_file = flow_file
        self.flow_handler: FlowHandler = FlowHandler()
        self.flow_file_handler: FlowFileHandler = FlowFileHandler(flow_filename=self.flow_file)
        self.init()

    def init(self):
        self.flow_handler.parsed_yaml_data = self.parse_flow_file().data
        self.validate_flow()
        self.extract_stage_information()

    def run(self, args: dict):
        """
        Run the flow with the provided arguments

        :Example:
        >>> Flow("concept.yaml").run({"url": "https://example.com"})
        """

        print(f"[TODO] Running flow '{self.flow_file}'")
        # Replace the template variables with the provided arguments
        self.replace_execution_dict_templates(args)

        # Run the flow
        CLIEx().run_flow(flow=self)

    def set_execution_dict(self, execution_array: Dict[str, list]):
        """
        Set the execution dictionary for the flow

        :Example:
        >>> Flow.set_execution_dict(execution_array)
        """
        self._execution_dict = execution_array

    @property
    def stage_information(self):
        """
        Get the stage information for the flow

        :Example:
        >>> Flow.stage_information
        """
        return self.flow_handler.stage_info

    @property
    def state_options(self):
        """
        Get the state options for the flow

        :Example:
        >>> Flow.state_options
        """
        return self.flow_handler.options

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
        return self.flow_handler.parsed_yaml_data

    def read_json(self) -> ParsedFlow:
        """
        Read the flow file and return the parsed JSON in a ParsedFlow object

        :Example:
        >>> Flow("concept.yaml").read_json().data
        {'version': '1.0', 'name': 'Gather available URLs from Target',...}
        """
        __flow_path: str = os.path.join(self.flow_file_handler.flow_dir,
                                        self.flow_file_handler.flow_filename)
        if os.path.exists(__flow_path):
            with open(__flow_path, 'r') as f:
                data = yaml.safe_load(f)
                return ParsedFlow(data)
        else:
            print(f"Flow file '{self.flow_file_handler.flow_filename}' does not exist.")
            exit(1)

    def parse_flow_file(self) -> FlowMeta:
        """
        Parse the flow file and return the FlowMeta object

        :Example:
        >>> Flow("concept.yaml").parse_flow_file().version
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
        >>> Flow("concept.yaml").validate_flow()
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
        >>> Flow("concept.yaml").extract_stage_information()
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

    def alias_to_command(self, alias: str) -> str:
        """
        Convert a given alias to a CLI command
        :param alias: Alias to convert

        :Example:
        >>> Flow.alias_to_command("paramspider:default")
        paramspider -s -d {{url}}
        """

        try:
            """Split the given tool shortcut into tool and alias"""
            tool, alias = alias.split(":")
        except Exception as e:
            print(f"[ERR] Could not find ':' delimiter in alias: {alias}")
            return str(e)

        aliases_file = Path(self.flow_file_handler.tool_dir, tool, ToolEnums.ALIAS_FILE.value)

        if os.path.exists(aliases_file):
            with open(aliases_file, 'r') as f:
                try:
                    self.flow_file_handler.alias_content = yaml.safe_load(f)
                except Exception as e:
                    print(f"[ERR] Could not load aliases file: {aliases_file}")
                    return str(e)
        else:
            print(f"[ERR] Aliases file not found: {aliases_file}")

        for _alias in self.flow_file_handler.alias_content["aliases"]:
            if _alias == alias:
                try:
                    self.flow_handler.alias_command = (
                            tool + " " + self.flow_file_handler.alias_content
                            .get("aliases")
                            .get(_alias)
                            .get("command")
                    )
                    break
                except Exception as e:
                    print(f"[ERR] Could not parse command for alias: {alias}")
                    return str(e)
            else:
                print(f"[ERR] Alias '{alias}' not found for tool '{tool}'")

        return self.flow_handler.alias_command

    def build_execution_dict(self) -> bool:
        """
        Prepare the tasks for the given flow object by converting the stage information and options
        :return: True if the flow execution dict is not empty, False otherwise

        :Example:
        >>> Flow().build_execution_dict()
        """

        _depth = 0
        commands = {
            "options": [],
            "aliases": [],
            "commands": [],
            "flows": []
        }

        for stage_execution in self.stage_information:
            # rprint("\n[b][cyan]==== New Stage ====")
            tmp_options, tmp_alias, tmp_cmd, tmp_flows = [], [], [], []

            # rprint("Options:", _execution_options[_depth])
            tmp_options.append(self.state_options[_depth])

            for dicts in stage_execution:
                try:
                    current_alias = dicts["alias"]
                    if current_alias:
                        transform_var = dicts.get("transform_var")
                        transform_stdin = dicts.get("transform_stdin")
                        alias = self.alias_to_command(current_alias)
                        tmp_alias.append([
                            alias,
                            transform_var,
                            transform_stdin
                        ])
                        # rprint(f"RUN ALIAS [yellow]{alias}")
                except KeyError:
                    pass

                try:
                    current_flow = dicts.get("flow")
                    if current_flow:
                        options = dicts.get("variables")
                        tmp_flows.append([current_flow, options])
                        # rprint(f"RUN FLOW '{current_flow}' | SET VARS \"{options if options else ''}\"")
                except KeyError:
                    pass

                try:
                    current_command = dicts.get("command")
                    if current_command:
                        transform_var = dicts.get("transform_var")
                        transform_stdin = dicts.get("transform_stdin")
                        tmp_cmd.append([
                            current_command,
                            transform_var,
                            transform_stdin
                        ])
                        # rprint(f"RUN CMD [yellow]{current_command}")
                except KeyError:
                    pass

            # Append the commands of each state in one containing array
            commands["options"].extend(tmp_options)
            commands["aliases"].append(tmp_alias)
            commands["commands"].append(tmp_cmd)
            commands["flows"].append(tmp_flows)

            # rprint(f"\nExecution Commands: {_execution_commands}")
            _depth += 1

        # Update the given flows execution dict
        if commands.__len__() > 0:
            self.set_execution_dict(commands)
            return True
        else:
            print(f"[WRN] Execution dict is empty, nothing to do!")
            return False

    def extract_vars(self) -> List[str]:
        """
        Extract unique template variables from execution array and flow config.
        execution_array should be a dictionary containing keys like "aliases" and "commands".

        :Example:
        >>> Flow.extract_vars()
        """
        template_vars = set()
        mapped_vars = set()

        # Extract variables from flow config
        local_vars = {}
        for var_name, var_value in self.yaml.get('variables', {}).items():
            if isinstance(var_value, str) and var_value.startswith('{{'):
                template_vars.add(var_name.replace('{{', '').replace('}}', ''))
                local_vars[var_name] = var_value

        # Helper function to extract variables from a string
        def extract_vars_from_string(s: str):
            if isinstance(s, str):
                matches = re.findall(r'\{\{(\w+)}}', s)
                template_vars.update(matches)

        # Check stages and tasks for variable mappings
        for stage in self.yaml.get('stages', {}).values():
            for task in stage.get('tasks', []):
                map_var = task.get('map_var')
                if map_var:
                    _, tool_var = map_var.split(':')
                    mapped_vars.add(tool_var)

        # Check aliases and commands in execution_array
        for alias_group in self.execution_dict.get('aliases', []):
            for alias in alias_group:
                extract_vars_from_string(alias[0])

        for command_group in self.execution_dict.get('commands', []):
            for command in command_group:
                extract_vars_from_string(command[0])

        template_vars.difference_update(mapped_vars)
        return list(template_vars)

    def replace_execution_dict_templates(self, args: dict) -> dict:
        """
        Replace the execution arguments with the provided arguments @TODO
        """
        print(f"[TODO] Replace execution dict templates with provided arguments: {args}")
        pass
