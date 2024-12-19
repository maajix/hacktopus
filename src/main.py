from rich import print as rprint
from rich.console import Console

from parser.FlowParser import FlowParser
from process.CLIBuilder import CLIBuilder, Flow
from process.FlowTaskManager import FlowTaskManager
from cli.click_manager import create_cli

console = Console()
flow = Flow()

if __name__ == '__main__':
    flow_parser = FlowParser(flow_file="concept.yaml")
    flow_content = flow_parser.get_file_contents()

    cli_builder = CLIBuilder(Flow=flow)
    flow_task_manager = FlowTaskManager(Flow=flow)

    # Returns a List[List[Dict[str, str]]] where str is either alias, command,
    # or flow with the corresponding execution information <tool>:<alias>
    execution_information = flow_parser.get_execution_information()

    # Returns a List[List[Dict[str, str]]] contain all the options for each
    # stage like description or parallel
    execution_options = flow_parser.get_execution_options()

    if execution_information and execution_options:
        # Update the empty flow object to contain those lists above
        flow.set_stage_information(execution_information)
        flow.set_state_options(execution_options)

        # Convert the lists into one execution dictionary containing
        # the converted commands, aliases, and flows with their respective variables if existing
        # Dict["<type>": List[List[Dict[str, str]]]] with types (options, aliases, commands, flows)
        is_converted = flow_task_manager.prepare_tasks(flow)
        if not is_converted:
            rprint(f"[ERR] While converting tasks")
    else:
        rprint("[ERR] Empty flow file provided")
        exit(1)

    # Dynamically create a Click CLI based on variables in the flow configuration
    cli = create_cli(flow_yaml=flow_content, execution_array=flow.get_execution_dict())
    cli()
