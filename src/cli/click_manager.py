from typing import Any, List, Dict

import click
from rich import print as rprint

from flow.Flow import Flow


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
            if i + 1 < len(unknown_args) and not unknown_args[i + 1].startswith('--'):
                var_value = unknown_args[i + 1]
                user_vars[var_name] = var_value
                i += 2
            else:
                # Instead of returning empty dict, just mark this variable as None
                rprint(f"[red]No value provided for variable '{var_name}'[/red]")
                user_vars[var_name] = None
                i += 1
        else:
            rprint(f"[red]Unexpected argument: {arg}[/red]")
            i += 1
    return user_vars


def validate_unknown_args(extracted_vars: List[str], unknown_args: dict) -> dict:
    flow_args = {}
    # Use the original order from extracted_vars
    for var_name in extracted_vars:  # removed sorted()
        # Check if argument exists AND has a value
        if var_name in unknown_args and unknown_args[var_name] not in (None, ''):
            flow_args[var_name] = unknown_args[var_name]
        else:
            # Prompt only for missing or empty values
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
        flow: Flow = Flow(flow_file=flow_name)

        # Prompt for variables that were not provided
        flow_args: Dict = validate_unknown_args(flow.extract_vars(), parse_unknown_args(ctx))

        # Execute the flow
        flow.run(flow_args)

    return cli
