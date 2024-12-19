import re
from typing import Dict, Any, List

import click


def extract_vars(flow_config: Dict[str, Any], execution_array: Dict[str, List]) -> List[str]:
    """
    Extract unique template variables from execution array and flow config.

    :param execution_array: Complete execution configuration dictionary
    :param flow_config: Flow configuration dictionary
    :return: List of unique template variables
    """
    template_vars = set()
    mapped_vars = set()

    # Extract variables from flow config
    local_vars = {}
    for var_name, var_value in flow_config.get('variables', {}).items():
        if isinstance(var_value, str) and var_value.startswith('{{'):
            template_vars.add(var_name.replace('{{', '').replace('}}', ''))
            local_vars[var_name] = var_value

    # Helper function to extract variables from a string
    def extract_vars_from_string(s: str):
        if isinstance(s, str):
            matches = re.findall(r'\{\{(\w+)}}', s)
            template_vars.update(matches)

    # Check stages and tasks for variable mappings
    for stage in flow_config.get('stages', {}).values():
        for task in stage.get('tasks', []):
            map_var = task.get('map_var')
            if map_var:
                _, tool_var = map_var.split(':')
                mapped_vars.add(tool_var)

    # Check aliases and commands
    for alias_group in execution_array.get('aliases', []):
        for alias in alias_group:
            extract_vars_from_string(alias[0])

    for command_group in execution_array.get('commands', []):
        for command in command_group:
            extract_vars_from_string(command[0])

    template_vars.difference_update(mapped_vars)
    return list(template_vars)


def create_cli(flow_yaml: Dict, execution_array: Dict):
    """
    Dynamically create a Click CLI based on variables in the flow configuration.

    :param flow_yaml: Dictionary containing flow configuration
    :param execution_array: Dictionary containing execution array
    :return: Click command function
    """

    # Create a base CLI group
    @click.group()
    def cli():
        """Dynamically generated CLI"""
        pass

    @cli.command()
    def run(**kwargs):
        """Run the flow with dynamic variables"""
        # Process and print the received arguments
        print("Received arguments:")
        for key, value in kwargs.items():
            print(f"{key}: {value}")

    template_vars = extract_vars(flow_yaml, execution_array)

    # Dynamically add options for each template variable
    for var_name in template_vars:
        run.params.append(
            click.Option(
                param_decls=[f'--{var_name}'],
                help=f'{var_name.capitalize()} to use in the flow'
            )
        )

    return cli
