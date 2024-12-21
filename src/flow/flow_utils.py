import re
from typing import Dict, Any, List

from flow.Flow import Flow
from rich import print as rprint

from flow.FlowTaskManager import FlowTaskManager


def extract_vars(YAML: Dict[str, Any], execution_array: Dict[str, List]) -> List[str]:
    """
    Extract unique template variables from execution array and flow config.
    execution_array should be a dictionary containing keys like "aliases" and "commands".
    """
    template_vars = set()
    mapped_vars = set()

    # Extract variables from flow config
    local_vars = {}
    for var_name, var_value in YAML.get('variables', {}).items():
        if isinstance(var_value, str) and var_value.startswith('{{'):
            template_vars.add(var_name.replace('{{', '').replace('}}', ''))
            local_vars[var_name] = var_value

    # Helper function to extract variables from a string
    def extract_vars_from_string(s: str):
        if isinstance(s, str):
            matches = re.findall(r'\{\{(\w+)}}', s)
            template_vars.update(matches)

    # Check stages and tasks for variable mappings
    for stage in YAML.get('stages', {}).values():
        for task in stage.get('tasks', []):
            map_var = task.get('map_var')
            if map_var:
                _, tool_var = map_var.split(':')
                mapped_vars.add(tool_var)

    # Check aliases and commands in execution_array
    for alias_group in execution_array.get('aliases', []):
        for alias in alias_group:
            extract_vars_from_string(alias[0])

    for command_group in execution_array.get('commands', []):
        for command in command_group:
            extract_vars_from_string(command[0])

    template_vars.difference_update(mapped_vars)
    return list(template_vars)


def create_execution_array(flow_name: str) -> Flow:
    """
    Create an execution array from a flow file.

    :param flow_name: The name of the flow file

    :Example:
    >>> create_execution_array('flow.yaml')
    """

    flow = Flow(flow_file=flow_name)
    flow_task_manager = FlowTaskManager()

    if not (flow.stage_information and flow.state_options):
        rprint("[ERR] Empty or invalid flow file provided")
        exit(1)

    # Convert tasks
    is_converted: bool = flow_task_manager.prepare_tasks(flow)
    if not is_converted:
        rprint("[ERR] While converting tasks")
        exit(1)

    if not flow.execution_dict:
        rprint("[ERR] No execution dict found. Cannot extract variables.")
        exit(1)

    # Extract template variables
    return flow
