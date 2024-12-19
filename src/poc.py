from typing import Dict, Any, List
import re

import click


def extract_template_variables(execution_array: Dict[str, List], flow_config: Dict[str, Any]) -> List[str]:
    """
    Extract unique template variables from execution array and flow config.

    :param execution_array: Complete execution configuration dictionary
    :param flow_config: Flow configuration dictionary
    :return: List of unique template variables
    """
    template_vars = set()

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
            # Check for map_var
            map_var = task.get('map_var')
            if map_var:
                # Split mapping (e.g., "url:domain")
                local_var, tool_var = map_var.split(':')
                # Remove the mapped tool variable from template vars
                template_vars.discard(tool_var)

    # Check aliases and commands
    for alias_group in execution_array.get('aliases', []):
        for alias in alias_group:
            extract_vars_from_string(alias[0])

    for command_group in execution_array.get('commands', []):
        for command in command_group:
            extract_vars_from_string(command[0])

    return list(template_vars)


def create_dynamic_cli_for_array(execution_array: Dict[str, List], flow_config: Dict[str, Any]):
    """
    Dynamically create a Click CLI based on template variables.

    :param execution_array: Complete execution configuration dictionary
    :param flow_config: Flow configuration dictionary
    :return: Click command function
    """
    # Extract unique template variables
    template_vars = extract_template_variables(execution_array, flow_config)

    # Create a base CLI group
    @click.group()
    def cli():
        """Dynamically generated CLI"""
        pass

    # Create run command with dynamic options
    @cli.command()
    def run(**kwargs):
        """Run the flow with dynamic variables"""
        # Process and print the received arguments
        print("Received arguments:")
        for key, value in kwargs.items():
            print(f"{key}: {value}")

        # Optional: Add placeholder for actual execution logic
        print("\nExecution array:", execution_array)
        print("\nFlow configuration:", flow_config)

    # Dynamically add options for each template variable
    for var_name in template_vars:
        run.params.append(
            click.Option(
                param_decls=[f'--{var_name}'],
                help=f'{var_name.capitalize()} to use in the flow'
            )
        )

    return cli


def create_dynamic_cli(flow_config: Dict[str, Any]):
    """
    Dynamically create a Click CLI based on variables in the flow configuration.

    :param flow_config: Dictionary containing flow configuration
    :return: Click command function
    """

    # Create a base CLI group
    @click.group()
    def cli():
        """Dynamically generated CLI"""
        pass

    # Create run command with dynamic options
    @cli.command()
    def run(**kwargs):
        """Run the flow with dynamic variables"""
        # Process and print the received arguments
        print("Received arguments:")
        for key, value in kwargs.items():
            print(f"{key}: {value}")

    # Dynamically add options based on variables in the flow configuration
    variables = flow_config.get('variables', {})
    for var_name, var_template in variables.items():
        # Check if it's a template variable
        if isinstance(var_template, str) and var_template.startswith('{{'):
            run.params.append(
                click.Option(
                    param_decls=[f'--{var_name}'],
                    help=f'{var_name.capitalize()} to use in the flow'
                )
            )

    return cli


def main():
    """Main entry point for the CLI"""
    # Example flow configuration directly in code
    flow_config = {
        'version': '1.0',
        'name': 'example_flow',
        'description': 'Demonstrate dynamic CLI parameter generation',
        'variables': {
            'url': '{{url}}',
            'domain': '{{domain}}',
            'port': '{{port}}'
        }
    }

    # Create and run the dynamic CLI
    cli = create_dynamic_cli(flow_config)
    cli()


if __name__ == '__main__':
    main()
