from typing import Any, List, Dict

import click
from rich import print as rprint

from flow.Flow import Flow
from flow.flow_utils import extract_vars, create_execution_dict


def prompt(prompt_text: str, default=None) -> str:
    """Prompt the user for input."""
    return click.prompt(prompt_text, default=default)


def parse_unknown_args(ctx) -> dict:
    unknown_args = ctx.args[:]  # copy the list
    user_vars = {}
    i = 0
    while i < len(unknown_args):
        arg = unknown_args[i]
        if arg.startswith('--'):
            var_name = arg.lstrip('-')
            if i + 1 < len(unknown_args):
                var_value = unknown_args[i + 1]
                user_vars[var_name] = var_value
                i += 2
            else:
                rprint(f"[red]No value provided for variable '{var_name}'[/red]")
                return {}
        else:
            rprint(f"[red]Unexpected argument: {arg}[/red]")
            return {}
    return user_vars


def validate_unknown_args(extracted_vars: List[str], unknown_args: dict) -> dict:
    # @TODO if user provides a valid arg and one without a value, he is prompted twice
    flow_args = {}
    for var_name in extracted_vars:
        if var_name in unknown_args:
            flow_args[var_name] = unknown_args[var_name]
        else:
            # Prompt user for the missing variable value
            flow_args[var_name] = prompt(
                f"Please provide a value for variable '{var_name}'"
            )
    return flow_args


def create_cli():
    @click.group()
    def cli():
        """Dynamically generated CLI"""
        pass

    @cli.group()
    def flow():
        """Flow management commands"""
        pass

    @flow.command(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
    @click.argument('flow_name')
    @click.pass_context
    def run(ctx: Any, flow_name: str) -> None:
        """
        Extract variables from the flow, and execute the flow with the provided variables.
        """
        flow: Flow = create_execution_dict(flow_name)

        # Extract template variables
        template_vars: List[str] = extract_vars(YAML=flow.yaml, execution_array=flow.execution_dict)

        # Manually parse unknown arguments to find provided variable values
        unknown_args: Dict = parse_unknown_args(ctx)

        # Prompt for variables that were not provided
        flow_args: Dict = validate_unknown_args(template_vars, unknown_args)

        # @TODO Execute the flow
        print("@TODO: Replace flow arguments with: ", flow_args)
        print("@TODO: Execute flow")
        rprint(flow.execution_dict)

    return cli
