from typing import Dict, List

from rich import print as rprint
from rich.console import Console

from cli.click_manager import create_cli
from flow.FlowParser import FlowParser
from flow.Flow import Flow
from flow.FlowTaskManager import FlowTaskManager

console = Console()
flow = Flow()

if __name__ == '__main__':
    flow_parser = FlowParser(flow_file="concept.yaml")
    flow_yaml_content: Dict = flow_parser.yaml
    flow_task_manager: FlowTaskManager = FlowTaskManager()

    # Returns a List[List[Dict[str, str]]] where str is either alias, command,
    # or flow with the corresponding execution information <tool>:<alias>
    execution_information: List[List[Dict]] = flow_parser.execution_information

    # Returns a List[List[Dict[str, str]]] contain all the options for each
    # stage like description or parallel
    execution_options: List[List[Dict]] = flow_parser.execution_options

    if execution_information and execution_options:
        # Update the empty flow object to contain those lists above
        flow.set_stage_information(execution_information)
        flow.set_state_options(execution_options)

        # Convert the lists into one execution dictionary containing
        # the converted commands, aliases, and flows with their respective variables if existing
        # Dict["<type>": List[List[Dict[str, str]]]] with types (options, aliases, commands, flows)
        is_converted: bool = flow_task_manager.prepare_tasks(flow)
        if not is_converted:
            rprint(f"[ERR] While converting tasks")
    else:
        rprint("[ERR] Empty flow file provided")
        exit(1)

    # Dynamically create a Click CLI based on variables in the flow configuration
    cli = create_cli(flow_yaml=flow_yaml_content, execution_array=flow.get_execution_dict)
    cli()
