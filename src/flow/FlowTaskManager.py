from dataclasses import dataclass
from typing import Dict

from flow.Flow import Flow
from process.CLIBuilder import CLIBuilder
# from rich import print as rprint


@dataclass
class FlowExecutionHandler:
    options: list[list[Dict]] = None
    aliases: list[list[Dict]] = None
    commands: list[list[Dict]] = None
    flows: list[list[Dict]] = None
    info: list[list[Dict]] = None


class FlowTaskManager:
    def __init__(self):
        self._cli_builder = CLIBuilder()
        self.flow_execution_handler = FlowExecutionHandler()

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
                        alias = self._cli_builder.alias_to_command(current_alias)
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
