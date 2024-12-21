import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict

import yaml

from flow.Flow import Flow


# from rich import print as rprint


class ToolEnums(Enum):
    """
    Enum to handle the different tool types
    """
    TOOLS_DIR_NAME = "tools"
    ALIAS_FILE = "aliases.yaml"


@dataclass
class ToolFileHandler:
    """
    Dataclass to handle the tool file paths
    """
    tool_name: str = None
    alias_content: dict = None
    root_dir: str = Path(__file__).parent.parent.parent.absolute()
    tool_dir: str = Path(root_dir, ToolEnums.TOOLS_DIR_NAME.value)


@dataclass
class FlowHandler:
    """
    Dataclass to handle the flow file paths
    """
    stage_info: dict = None
    stage_options: dict = None
    alias_command: str = None


@dataclass
class FlowExecutionHandler:
    options: list[list[Dict]] = None
    aliases: list[list[Dict]] = None
    commands: list[list[Dict]] = None
    flows: list[list[Dict]] = None
    info: list[list[Dict]] = None


class FlowTaskManager:
    def __init__(self):
        self.flow_execution_handler = FlowExecutionHandler()
        self.tool_file_handler = ToolFileHandler()
        self.flowHandler = FlowHandler()

    def alias_to_command(self, alias: str) -> str:
        """
        Convert a given alias to a CLI command
        :param alias: Alias to convert

        :Example:
        >>> FlowTaskManager.alias_to_command("paramspider:default")
        paramspider -s -d {{url}}
        """

        try:
            """Split the given tool shortcut into tool and alias"""
            tool, alias = alias.split(":")
        except Exception as e:
            print(f"[ERR] Could not find ':' delimiter in alias: {alias}")
            return str(e)

        aliases_file = Path(self.tool_file_handler.tool_dir, tool, ToolEnums.ALIAS_FILE.value)

        if os.path.exists(aliases_file):
            with open(aliases_file, 'r') as f:
                try:
                    self.tool_file_handler.alias_content = yaml.safe_load(f)
                except Exception as e:
                    print(f"[ERR] Could not load aliases file: {aliases_file}")
                    return str(e)
        else:
            print(f"[ERR] Aliases file not found: {aliases_file}")

        for _alias in self.tool_file_handler.alias_content["aliases"]:
            if _alias == alias:
                try:
                    self.flowHandler.alias_command = (
                            tool + " " + self.tool_file_handler.alias_content
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

        return self.flowHandler.alias_command

    def prepare_tasks(self, flow: Flow) -> bool:
        """
        Prepare the tasks for the given flow object by converting the stage information and options

        :param flow: Flow object
        :return: True if the flow execution dict is not empty, False otherwise

        :Example:
        >>> FlowTaskManager().prepare_tasks(flow)
        """

        _depth = 0
        self.flow_execution_handler.info = flow.stage_information
        self.flow_execution_handler.options = flow.state_options
        self.flow_execution_handler.commands = {
            "options": [],
            "aliases": [],
            "commands": [],
            "flows": []
        }

        for stage_execution in self.flow_execution_handler.info:
            # rprint("\n[b][cyan]==== New Stage ====")
            tmp_options, tmp_alias, tmp_cmd, tmp_flows = [], [], [], []

            # rprint("Options:", _execution_options[_depth])
            tmp_options.append(self.flow_execution_handler.options[_depth])

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
            self.flow_execution_handler.commands["options"].extend(tmp_options)
            self.flow_execution_handler.commands["aliases"].append(tmp_alias)
            self.flow_execution_handler.commands["commands"].append(tmp_cmd)
            self.flow_execution_handler.commands["flows"].append(tmp_flows)

            # rprint(f"\nExecution Commands: {_execution_commands}")
            _depth += 1

        # Update the given flows execution dict
        flow.set_execution_dict(self.flow_execution_handler.commands)

        if self.flow_execution_handler.commands.__len__() > 0:
            return True
        else:
            print(f"[WRN] Execution dict is empty, nothing to do!")
            return False
