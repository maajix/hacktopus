import re

import click
import yaml
import os
import subprocess
import asyncio
from rich.console import Console
from rich.table import Table
from rich.tree import Tree
import sys

console = Console()


def load_global_config():
    config_path = os.path.join(os.getcwd(), "global_config.yaml")
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            data = yaml.safe_load(f)
            return data if data is not None else {}
    else:
        return {}


global_config = load_global_config()


def strip_ansi_codes(text):
    """Remove ANSI color codes from text."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text) if text else text


def load_tool(tool_name):
    tools_dir = global_config.get("paths", {}).get("tools_dir", "./tools")
    tool_dir = os.path.join(tools_dir, tool_name)
    config_file = os.path.join(tool_dir, "config.yaml")
    aliases_file = os.path.join(tool_dir, "aliases.yaml")

    tool_config = {}
    tool_aliases = {}

    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            tool_config = yaml.safe_load(f) or {}

    if os.path.exists(aliases_file):
        with open(aliases_file, 'r') as f:
            data = yaml.safe_load(f) or {}
            tool_aliases = data.get("aliases", {})

    return tool_config, tool_aliases


def load_flow(flow_name):
    flows_dir = global_config.get("paths", {}).get("flows_dir", "./flows")
    flow_file = os.path.join(flows_dir, f"{flow_name}.yaml")

    if os.path.exists(flow_file):
        with open(flow_file, 'r') as f:
            return yaml.safe_load(f) or {}
    else:
        return None


@click.group()
def cli():
    """CLI tool for orchestrating pentest flows and aliases."""
    pass


@cli.command(name="tools")
@click.option('--tag', help="Filter tools by a tag substring")
def tools_command(tag):
    """List all available tools. Optionally filter by tag substring."""
    tools_dir = global_config.get("paths", {}).get("tools_dir", "./tools")
    if not os.path.exists(tools_dir):
        console.print("[red]Tools directory not found.[/red]")
        return

    table = Table(title="Available Tools")
    table.add_column("Tool Name", style="cyan")
    table.add_column("Tags", style="magenta")
    table.add_column("Description", style="white")

    for tool_name in os.listdir(tools_dir):
        tool_path = os.path.join(tools_dir, tool_name)
        if os.path.isdir(tool_path):
            tool_config, _ = load_tool(tool_name)
            desc = tool_config.get("description", "")
            tool_tags = tool_config.get("tags", [])

            if tag:
                tag_lower = tag.lower()
                if not any(tag_lower in t.lower() for t in tool_tags):
                    continue

            tags_str = ", ".join(tool_tags)
            table.add_row(tool_name, tags_str, desc)

    console.print(table)


@cli.command(name="aliases")
def aliases_command():
    """List all aliases from all tools."""
    tools_dir = global_config.get("paths", {}).get("tools_dir", "./tools")
    if not os.path.exists(tools_dir):
        console.print("[red]Tools directory not found.[/red]")
        return

    table = Table(title="Available Aliases")
    table.add_column("Tool:Alias", style="cyan")
    table.add_column("Description", style="white")

    for tool_name in os.listdir(tools_dir):
        tool_path = os.path.join(tools_dir, tool_name)
        if os.path.isdir(tool_path):
            _, aliases = load_tool(tool_name)
            for alias_name, alias_data in aliases.items():
                desc = alias_data.get("description", "")
                table.add_row(f"{tool_name}:{alias_name}", desc)

    console.print(table)


@cli.command(name="add")
@click.argument('name')
def create_tool(name):
    """Create a new tool directory with config and aliases files."""
    tools_dir = global_config.get("paths", {}).get("tools_dir", "./tools")

    # Create tool directory
    tool_dir = os.path.join(tools_dir, name)
    if os.path.exists(tool_dir):
        console.print(f"[red]Tool directory '{name}' already exists.[/red]")
        return

    try:
        # Create directories
        os.makedirs(tool_dir, exist_ok=True)

        # Create config.yaml
        config_content = {
            "description": "",
            "tags": [],
            "run_command": "",
            "accepts_stdin": True
        }

        with open(os.path.join(tool_dir, "config.yaml"), 'w') as f:
            yaml.dump(config_content, f, sort_keys=False)

        # Create aliases.yaml
        aliases_content = {
            "aliases": {
                "default": {
                    "description": "",
                    "command": "",
                    "variables": []
                }
            }
        }

        with open(os.path.join(tool_dir, "aliases.yaml"), 'w') as f:
            yaml.dump(aliases_content, f, sort_keys=False)

        console.print(
            f"[green]Successfully created tool directory '{name}' with config and aliases files.[/green]")

    except Exception as e:
        console.print(f"[red]Error creating tool directory: {str(e)}[/red]")


@cli.command(name="exec")
@click.argument('alias_name')
@click.argument('args', nargs=-1)
def exec_command(alias_name, args):
    """
    Execute a given alias with optional arguments.
    Example: exec nmap:default-enum 192.168.1.1
    """
    if ":" not in alias_name:
        console.print("[red]Please specify alias as tool:alias_name[/red]")
        return

    tool_name, alias_key = alias_name.split(":", 1)
    tool_config, tool_aliases = load_tool(tool_name)

    if alias_key not in tool_aliases:
        console.print(f"[red]Alias '{alias_key}' not found in tool '{tool_name}'.[/red]")
        return

    alias_def = tool_aliases[alias_key]
    cmd_template = alias_def.get("command", "")
    variables = alias_def.get("variables", [])

    if len(args) < len(variables):
        console.print("[red]Not all variables provided.[/red]")
        return

    var_map = {}
    for i, var_def in enumerate(variables):
        var_map[var_def['name']] = args[i]

    for var_name, var_val in var_map.items():
        cmd_template = cmd_template.replace(f"{{{{{var_name}}}}}", var_val)

    run_command = tool_config.get("run_command")
    if not run_command:
        console.print(f"[red]Tool '{tool_name}' has no run_command defined.[/red]")
        return

    full_cmd = f"{run_command} {cmd_template}"
    console.print(f"[green]Executing:[/green] {full_cmd}")

    proc = subprocess.run(full_cmd, shell=True)
    if proc.returncode != 0:
        console.print("[red]Command failed![/red]")


@cli.group()
def flow():
    """Manage and run flows."""
    pass


@flow.command(name="list")
def flow_list():
    """List all available flows."""
    flows_dir = global_config.get("paths", {}).get("flows_dir", "./flows")
    if not os.path.exists(flows_dir):
        console.print("[red]Flows directory not found.[/red]")
        return

    table = Table(title="Available Flows")
    table.add_column("Flow Name", style="cyan")
    table.add_column("Description", style="white")

    for file_name in os.listdir(flows_dir):
        if file_name.endswith(".yaml"):
            flow_name = file_name[:-5]
            flow_def = load_flow(flow_name)
            desc = flow_def.get("description", "")
            table.add_row(flow_name, desc)

    console.print(table)


@flow.command(name="info")
@click.argument('flow_name')
def flow_info_command(flow_name):
    """Show detailed information about a specific flow in a tree-like structure."""
    flow_def = load_flow(flow_name)
    if not flow_def:
        console.print(f"[red]Flow '{flow_name}' not found.[/red]")
        return

    desc = flow_def.get("description", "")
    variables = flow_def.get("variables", {})
    steps = flow_def.get("steps", [])

    console.print(f"[bold cyan]Flow Name:[/bold cyan] {flow_name}")
    console.print(f"[bold cyan]Description:[/bold cyan] {desc}")

    if variables:
        console.print("\n[bold cyan]Variables:[/bold cyan]")
        var_table = Table(show_header=True, header_style="bold magenta")
        var_table.add_column("Variable", style="cyan")
        var_table.add_column("Placeholder", style="white")
        for var_name, var_placeholder in variables.items():
            var_table.add_row(var_name, var_placeholder)
        console.print(var_table)

    flow_tree = Tree("[bold cyan]Flow Structure:[/bold cyan]", guide_style="bold cyan")

    for i, step in enumerate(steps, start=1):
        if 'alias' in step:
            alias_str = step['alias']
            alias_node = flow_tree.add(f"● [green]{alias_str}[/green]")

            configs = []
            if step.get('pipe_input'):
                configs.append(("pipe_input", "true"))
            if step.get('pipe_output'):
                configs.append(("pipe_output", "true"))
            if step.get('print_output'):
                configs.append(("print_output", "true"))

            for config_name, config_value in configs:
                alias_node.add(f"└── {config_name}: {config_value}")

        elif 'parallel' in step:
            parallel_def = step['parallel']
            parallel_node = flow_tree.add("● PARALLEL EXECUTION")

            # Add parallel configuration
            if parallel_def.get('fan_out'):
                parallel_node.add(f"├── fan_out: {parallel_def.get('fan_out')}")
            if parallel_def.get('combine_output'):
                parallel_node.add(f"├── combine_output: {parallel_def.get('combine_output')}")

            tasks = parallel_def.get('tasks', [])
            for t in tasks:
                t_alias = t['alias']
                task_node = parallel_node.add(f"● [green]{t_alias}[/green]")

                configs = []
                if t.get('pipe_input'):
                    configs.append(("pipe_input", "true"))
                if t.get('print_output'):
                    configs.append(("print_output", "true"))

                for config_name, config_value in configs:
                    task_node.add(f"└── {config_name}: {config_value}")

    console.print()
    console.print(flow_tree)


def validate_flow(flow_def, var_values):
    steps = flow_def.get('steps', [])
    tools_dir = global_config.get("paths", {}).get("tools_dir", "./tools")

    for i, step in enumerate(steps, start=1):
        if 'alias' in step:
            alias_str = step['alias']
            if ":" not in alias_str:
                return False, f"Step {i}: Alias '{alias_str}' not in 'tool:alias' format."

            tool_name, alias_name = alias_str.split(":", 1)
            tool_path = os.path.join(tools_dir, tool_name)
            if not os.path.isdir(tool_path):
                return False, f"Step {i}: Tool '{tool_name}' directory not found."

            tool_config, tool_aliases = load_tool(tool_name)
            if alias_name not in tool_aliases:
                return False, f"Step {i}: Alias '{alias_name}' not found in tool '{tool_name}'."

            if step.get('pipe_input', False):
                accepts_stdin = tool_config.get("accepts_stdin", True)
                if not accepts_stdin:
                    return False, f"Step {i}: Tool '{tool_name}' does not accept stdin, but pipe_input is true."

            # Check alias variables
            alias_def = tool_aliases[alias_name]
            for var_def in alias_def.get("variables", []):
                vname = var_def['name']
                if vname not in var_values:
                    return False, f"Step {i}: Missing variable '{vname}' required by alias '{alias_str}'."

        elif 'parallel' in step:
            parallel_def = step['parallel']
            tasks = parallel_def.get('tasks', [])
            for t in tasks:
                alias_str = t['alias']
                if ":" not in alias_str:
                    return False, f"Parallel Step {i}: Alias '{alias_str}' not in 'tool:alias' format."

                tool_name, alias_name = alias_str.split(":", 1)
                tool_path = os.path.join(tools_dir, tool_name)
                if not os.path.isdir(tool_path):
                    return False, f"Parallel Step {i}: Tool '{tool_name}' directory not found."

                tool_config, tool_aliases = load_tool(tool_name)
                if alias_name not in tool_aliases:
                    return False, f"Parallel Step {i}: Alias '{alias_name}' not found in tool '{tool_name}'."

                if t.get('pipe_input', False):
                    accepts_stdin = tool_config.get("accepts_stdin", True)
                    if not accepts_stdin:
                        return False, f"Parallel Step {i}: Tool '{tool_name}' does not accept stdin, but pipe_input is true."

                # Check alias variables
                alias_def = tool_aliases[alias_name]
                for var_def in alias_def.get("variables", []):
                    vname = var_def['name']
                    if vname not in var_values:
                        return False, f"Parallel Step {i}: Missing variable '{vname}' required by alias '{alias_str}'."

    return True, None


@flow.command(name="run",
              context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
@click.argument('flow_name')
@click.option('--print-step-output', is_flag=True, help="Print each step's output after execution")
@click.option('--strip-colors', is_flag=True, help="Strip ANSI color codes from output")
@click.option('--debug', is_flag=True, help="Show stderr output and additional debug information")
@click.pass_context
def flow_run_command(ctx, flow_name, print_step_output, strip_colors, debug):
    """Run a defined flow with error checking and optional color stripping."""
    flow_def = load_flow(flow_name)
    if not flow_def:
        console.print(f"[red]Flow '{flow_name}' not found.[/red]")
        return

    flow_vars = flow_def.get('variables', {})

    # Parse unknown args for variables
    user_vars = {}
    unknown_args = ctx.args[:]
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
                console.print(f"[red]No value provided for variable '{var_name}'[/red]")
                return
        else:
            console.print(f"[red]Unexpected argument: {arg}[/red]")
            return

    var_values = {}
    for var_name in flow_vars:
        if var_name in user_vars:
            var_values[var_name] = user_vars[var_name]
        else:
            var_values[var_name] = click.prompt(f"Please provide a value for variable '{var_name}'")

    valid, error_msg = validate_flow(flow_def, var_values)
    if not valid:
        console.print(f"[red]{error_msg}[/red]")
        return

    steps = flow_def.get('steps', [])
    last_output = None

    def transform_value(value, transform_type):
        """Transform a value based on the specified transformation type."""
        if transform_type == "url_to_domain":
            from urllib.parse import urlparse
            domain = urlparse(value).netloc
            return domain.removeprefix('www.')
        # Add more transformations as needed
        return value

    async def run_alias_async(tool_name, alias_name, input_data=None):
        loop = asyncio.get_event_loop()
        tool_config, tool_aliases = load_tool(tool_name)
        alias_def = tool_aliases[alias_name]
        cmd_template = alias_def.get("command", "")
        variables = alias_def.get("variables", [])

        # Process variables with their transforms
        processed_vars = var_values.copy()
        for var_def in variables:
            vname = var_def['name']
            if vname in processed_vars and 'transform' in var_def:
                transform_type = var_def['transform']
                original = processed_vars[vname]
                processed_vars[vname] = transform_value(original, transform_type)
                if debug:
                    console.print(
                        f"[yellow]Debug - Transforming {vname} using {transform_type}: {original} -> {processed_vars[vname]}[/yellow]")

        # Apply processed variables to command template
        for var_def in variables:
            vname = var_def['name']
            if vname in processed_vars:
                cmd_template = cmd_template.replace(f"{{{{{vname}}}}}", processed_vars[vname])

        run_command = tool_config.get("run_command")
        full_cmd = f"{run_command} {cmd_template}"
        console.print(f"[green]Running:[/green] {full_cmd}")

        def run_proc():
            try:
                proc = subprocess.run(full_cmd, shell=True, input=input_data, text=True,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                # Show stderr in debug mode
                if debug and proc.stderr and proc.stderr.strip():
                    console.print(f"[yellow]Debug - stderr from '{alias_name}':[/yellow]")
                    console.print(proc.stderr)

                # Strip colors if requested
                output = proc.stdout
                if strip_colors:
                    output = strip_ansi_codes(output)

                return output, proc.returncode, proc.stderr
            except Exception as e:
                return None, -1, str(e)

        stdout, rc, stderr = await loop.run_in_executor(None, run_proc)

        if rc != 0:
            error_msg = stderr if stderr else "Unknown error"
            console.print(f"[red]Command '{alias_name}' failed with exit code {rc}[/red]")
            console.print(f"[red]Error: {error_msg}[/red]")
            if click.confirm("Do you want to continue with the flow?", default=False):
                return stdout, 0
            else:
                sys.exit(1)

        return stdout, 0

    async def run_parallel_tasks(tasks, input_data, fan_out, combine_output, print_step_output):
        coros = []
        task_info = []
        for t in tasks:
            alias_str = t['alias']
            pipe_input = t.get('pipe_input', False)
            t_print_output = t.get('print_output', False)
            tool_name, alias_name = alias_str.split(":", 1)
            task_input = input_data if (pipe_input and fan_out) else (
                input_data if pipe_input else None)
            coros.append(run_alias_async(tool_name, alias_name, task_input))
            task_info.append((alias_str, t_print_output))

        results = await asyncio.gather(*coros, return_exceptions=True)
        outputs = []
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                console.print(f"[red]Parallel task '{task_info[i][0]}' failed: {str(res)}[/red]")
                if click.confirm("Do you want to continue with the flow?", default=False):
                    continue
                else:
                    return None
            stdout, rc = res
            if rc != 0:
                return None
            outputs.append(stdout)

            # Only print output if print_output is true for this task or global print_step_output is set
            if stdout and stdout.strip():
                should_print = task_info[i][1] or print_step_output
                if should_print:
                    console.print(
                        f"[bold blue]Output from parallel task '{task_info[i][0]}':[/bold blue]")
                    console.print(stdout)

        if combine_output:
            combined = "\n".join(o.strip() for o in outputs if o)
            return combined
        return None

    async def run_flow():
        nonlocal last_output
        for i, step in enumerate(steps, start=1):
            if 'alias' in step:
                alias_str = step['alias']
                tool_name, alias_name = alias_str.split(":", 1)
                input_data = last_output if step.get('pipe_input') else None
                output, rc = await run_alias_async(tool_name, alias_name, input_data)
                if rc != 0:
                    return

                # Only print output if print_output is true for this step or global print_step_output is set
                should_print = step.get('print_output', False) or print_step_output
                if should_print and output and output.strip():
                    console.print(f"[bold blue]Output from step {i} ({alias_str}):[/bold blue]")
                    console.print(output)

                if step.get('pipe_output'):
                    last_output = output
                else:
                    last_output = None

            elif 'parallel' in step:
                parallel_def = step['parallel']
                combine_output = parallel_def.get('combine_output', False)
                fan_out = parallel_def.get('fan_out', False)
                tasks = parallel_def.get('tasks', [])
                input_data = last_output if fan_out else None
                result = await run_parallel_tasks(tasks, input_data, fan_out, combine_output,
                                                  print_step_output)

                if combine_output and result and result.strip():
                    console.print("[bold blue]Combined output from parallel step:[/bold blue]")
                    console.print(result)

                last_output = result if combine_output else None

        console.print("[green]Flow execution completed successfully.[/green]")

    asyncio.run(run_flow())


if __name__ == "__main__":
    cli()
