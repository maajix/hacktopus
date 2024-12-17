from parser.FlowParser import FlowParser
from process.CLIExecutionManager import CommandExecutionManager
from process.CLIBuilder import CLIBuilder, Flow
from rich.console import Console
from rich import print as rprint

console = Console()


# @TODO Gather tasks / commands, execute in parallel (create threads) if set else sequentially
def prepare_tasks():
    depth = 0
    for stage_execution in execution_information:
        rprint("\n[b][cyan]==== New Stage ====")
        rprint("Options:", execution_options[depth])
        depth += 1

        for dicts in stage_execution:
            try:
                current_alias = dicts["alias"]
                if current_alias:
                    rprint(f"RUN ALIAS [yellow]{cli_builder.alias_to_command(current_alias)}")
            except KeyError:
                pass

            try:
                current_flow = dicts.get("flow")
                if current_flow:
                    options = dicts.get("variables")
                    rprint(f"RUN FLOW '{current_flow}' | SET VARS \"{options if options else ''}\"")
            except KeyError:
                pass

            try:
                current_command = dicts.get("command")
                if current_command:
                    rprint(f"RUN CMD [yellow]{current_command}")
            except KeyError:
                pass


if __name__ == '__main__':
    flow_parser = FlowParser("concept.yaml")
    flow = Flow()
    cli_builder = CLIBuilder(flow)

    execution_information = flow_parser.get_execution_information()
    execution_options = flow_parser.get_execution_options()

    flow.set_stage_information(execution_information)
    flow.set_state_options(execution_options)

    prepare_tasks()
