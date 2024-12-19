from .Flow import Flow
from .CLIBuilder import CLIBuilder


class FlowTaskManager:
    _cli_builder = None

    def __init__(self, Flow: Flow):
        self._cli_builder = CLIBuilder(Flow)

    def prepare_tasks(self, flow: Flow) -> bool:
        _depth = 0
        _execution_information = flow.get_stage_information()
        _execution_options = flow.get_state_options()
        _execution_commands = {
            "options": [],
            "aliases": [],
            "commands": [],
            "flows": []
        }

        for stage_execution in _execution_information:
            # rprint("\n[b][cyan]==== New Stage ====")
            tmp_options, tmp_alias, tmp_cmd, tmp_flows = [], [], [], []

            # rprint("Options:", _execution_options[_depth])
            tmp_options.append(_execution_options[_depth])

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
            _execution_commands["options"].extend(tmp_options)
            _execution_commands["aliases"].append(tmp_alias)
            _execution_commands["commands"].append(tmp_cmd)
            _execution_commands["flows"].append(tmp_flows)

            # rprint(f"\nExecution Commands: {_execution_commands}")
            _depth += 1

        # Update the given flows execution dict
        flow.set_execution_dict(_execution_commands)
        if _execution_commands.__len__() > 0:
            return True
        else:
            print(f"[WRN] Execution dict is empty, nothing to do!")
            return False
