import re
import time
from urllib.parse import urlparse

import click
import yaml
import os
import subprocess
import asyncio
from rich.console import Console
from rich.progress import Progress, TextColumn, TimeElapsedColumn
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
            "accepts_stdin": True,
            "header_flag": ""  # Determines header support based on presence and value
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
@click.option('--headers', multiple=True, help='Headers to include. Fully customizable strings.')
def exec_command(alias_name, args, headers):
    """
    Execute a given alias with optional arguments.
    Example: exec nmap:default-enum 192.168.1.1 --headers "User-Agent=Mozilla" --headers "Auth=Bearer xyz"
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

    # Handle headers if applicable
    header_flag = tool_config.get("header_flag", "")
    if header_flag and headers:
        for header in headers:
            # Append the header as-is without enforcing any format
            cmd_template += f' {header_flag} "{header}"'

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
@click.option('--tag', help="Filter flows by tag")
def flow_list(tag):
    """List all available flows. Optionally filter by tag."""
    flows_dir = global_config.get("paths", {}).get("flows_dir", "./flows")
    if not os.path.exists(flows_dir):
        console.print("[red]Flows directory not found.[/red]")
        return

    table = Table(title="Available Flows")
    table.add_column("Flow Name", style="cyan")
    table.add_column("Tags", style="magenta")
    table.add_column("Description", style="white")

    for file_name in os.listdir(flows_dir):
        if file_name.endswith(".yaml"):
            flow_name = file_name[:-5]
            flow_def = load_flow(flow_name)

            # Skip if flow definition couldn't be loaded
            if not flow_def:
                continue

            desc = flow_def.get("description", "")
            flow_tags = flow_def.get("tags", [])

            # If tag filter is specified, check if flow has matching tag
            if tag:
                tag_lower = tag.lower()
                if not any(tag_lower in t.lower() for t in flow_tags):
                    continue

            # Format tags for display
            tags_str = ", ".join(flow_tags) if flow_tags else ""

            table.add_row(flow_name, tags_str, desc)

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
    stages = flow_def.get("stages", {})
    flow_order = flow_def.get("flow", [])

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

    for stage_entry in flow_order:
        stage_name = stage_entry['stage']
        stage_def = stages.get(stage_name, {})

        if 'parallel' in stage_def:
            parallel_def = stage_def['parallel']
            parallel_node = flow_tree.add(f"● PARALLEL EXECUTION: {stage_name}")

            # Add parallel configuration
            if parallel_def.get('fan_out'):
                parallel_node.add(f"├── fan_out: {parallel_def.get('fan_out')}")
            if parallel_def.get('combine_output'):
                parallel_node.add(f"├── combine_output: {parallel_def.get('combine_output')}")

            tasks = parallel_def.get('tasks', [])
            for task in tasks:
                t_alias = task['alias']
                task_node = parallel_node.add(f"● [green]{t_alias}[/green]")

                configs = []
                if task.get('pipe_input'):
                    configs.append(("pipe_input", "true"))
                if task.get('print_output'):
                    configs.append(("print_output", "true"))

                for config_name, config_value in configs:
                    task_node.add(f"└── {config_name}: {config_value}")

        else:  # Sequential stage
            stage_node = flow_tree.add(f"● SEQUENTIAL EXECUTION: {stage_name}")

            stage_tasks = stage_def if isinstance(stage_def, list) else []
            for task in stage_tasks:
                t_alias = task['alias']
                task_node = stage_node.add(f"● [green]{t_alias}[/green]")

                configs = []
                if task.get('pipe_input'):
                    configs.append(("pipe_input", "true"))
                if task.get('pipe_output'):
                    configs.append(("pipe_output", "true"))
                if task.get('print_output'):
                    configs.append(("print_output", "true"))

                for config_name, config_value in configs:
                    task_node.add(f"└── {config_name}: {config_value}")

    console.print()


def validate_task(task, var_values):
    """
    Validate a single task configuration.

    Args:
        task (dict): Task configuration to validate
        var_values (dict): Variables available for the flow

    Returns:
        tuple: (is_valid, error_message)
    """
    # Check if task has required alias
    if 'alias' not in task:
        return False, "Task missing 'alias' field"

    alias_str = task['alias']
    if ':' not in alias_str:
        return False, f"Alias '{alias_str}' not in 'tool:alias' format"

    tool_name, alias_name = alias_str.split(':', 1)

    # Validate tool exists and load its configuration
    tools_dir = global_config.get("paths", {}).get("tools_dir", "./tools")
    tool_path = os.path.join(tools_dir, tool_name)
    if not os.path.isdir(tool_path):
        return False, f"Tool '{tool_name}' directory not found"

    # Load tool configuration and aliases
    tool_config, tool_aliases = load_tool(tool_name)

    # Check if alias exists for tool
    if alias_name not in tool_aliases:
        return False, f"Alias '{alias_name}' not found in tool '{tool_name}'"

    # Validate settings if present
    if 'settings' in task:
        settings = task['settings']

        # Check pipe_input compatibility based on header_flag
        header_flag = tool_config.get("header_flag", "")
        if settings.get('pipe_input', False):
            accepts_stdin = True  # Default assumption
            # Determine if the tool accepts stdin based on header_flag presence
            # If header_flag is present, assume it accepts stdin unless specified otherwise
            if header_flag:
                accepts_stdin = True
            # Add more logic if needed based on tool's specific behavior

            if not accepts_stdin:
                return False, f"Tool '{tool_name}' does not accept stdin, but pipe_input is true"

        # Validate setting types
        for setting, value in settings.items():
            if setting in ['pipe_input', 'pipe_output', 'print_output'] and not isinstance(value,
                                                                                           bool):
                return False, f"Setting '{setting}' must be a boolean"

    # Validate variables if present
    if 'variables' in task:
        alias_def = tool_aliases[alias_name]
        required_vars = {var_def['name'] for var_def in alias_def.get("variables", [])}

        # Check all required variables are provided
        task_vars = task['variables']
        for var_name, var_value in task_vars.items():
            if var_name not in required_vars:
                return False, f"Variable '{var_name}' provided but not required by alias '{alias_name}'"

        # Check all variables have values
        for var_name in required_vars:
            if var_name not in task_vars and var_name not in var_values:
                return False, f"Required variable '{var_name}' missing for alias '{alias_name}'"

    return True, None


def validate_flow(flow_def, var_values):
    stages = flow_def.get('stages', {})
    flow_order = flow_def.get('flow', [])

    if not stages:
        return False, "No stages defined in flow"

    if not flow_order:
        return False, "No flow order defined"

    for stage_entry in flow_order:
        if 'stage' not in stage_entry:
            return False, "Stage entry missing 'stage' field"

        stage_name = stage_entry['stage']
        if stage_name not in stages:
            return False, f"Stage '{stage_name}' referenced in flow but not defined in stages"

        stage_def = stages[stage_name]

        if isinstance(stage_def, list):  # Sequential tasks
            for task in stage_def:
                valid, msg = validate_task(task, var_values)
                if not valid:
                    return False, f"In stage '{stage_name}': {msg}"

        elif stage_def.get('parallel'):  # Parallel tasks
            for task in stage_def['tasks']:
                valid, msg = validate_task(task, var_values)
                if not valid:
                    return False, f"In parallel stage '{stage_name}': {msg}"
        else:
            return False, f"Invalid stage definition for '{stage_name}'"

    return True, None


@flow.command(name="run",
              context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
@click.argument('flow_name')
@click.option('--print-step-output', is_flag=True, help="Print each step's output after execution")
@click.option('--strip-colors', is_flag=True, help="Strip ANSI color codes from output")
@click.option('--debug', is_flag=True, help="Show stderr output and additional debug information")
@click.option('--show-full-output', is_flag=True, help="Show full output without truncation")
@click.option('--save-output', is_flag=True, help="Save output to results directory")
@click.option('--headers', multiple=True, help='Headers to include. Fully customizable strings.')
@click.pass_context
def flow_run_command(ctx, flow_name, print_step_output, strip_colors, debug, show_full_output,
                     save_output, headers):
    """Run a defined flow with error checking and optional color stripping."""
    flow_def = load_flow(flow_name)
    if not flow_def:
        console.print(f"[red]Flow '{flow_name}' not found.[/red]")
        return

    # Create results directory if saving output
    if save_output:
        results_dir = "results"
        os.makedirs(results_dir, exist_ok=True)
        output_file = os.path.join(results_dir, f"{flow_name}_output.txt")

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

    # Parse and validate headers
    headers_list = headers
    parsed_headers = []
    for header in headers_list:
        # Accept any string format without enforcing key-value structure
        header_cleaned = header.strip()
        if not header_cleaned:
            console.print(f"[red]Invalid header: Empty string provided.[/red]")
            return
        parsed_headers.append(header_cleaned)

    valid, error_msg = validate_flow(flow_def, var_values)
    if not valid:
        console.print(f"[red]{error_msg}[/red]")
        return

    stages = flow_def.get('stages', {})
    flow_order = flow_def.get('flow', [])
    last_output = None

    def transform_value(value, transform_type):
        """Transform a value based on the specified transformation type."""
        if transform_type == "url_to_domain":
            domain = urlparse(value).netloc
            return domain.removeprefix('www.')
        # Add more transformations as needed
        return value

    async def run_alias_async(tool_name, alias_name, progress, task_id, input_data=None,
                              print_step_output=False, headers=None):
        """Execute a tool alias with real-time progress updates and improved error handling."""
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

        # Apply processed variables to command template
        for var_def in variables:
            vname = var_def['name']
            if vname in processed_vars:
                cmd_template = cmd_template.replace(f"{{{{{vname}}}}}", processed_vars[vname])

        run_command = tool_config.get("run_command")
        full_cmd = f"{run_command} {cmd_template}"

        # Append headers if header_flag is present and headers are provided
        header_flag = tool_config.get("header_flag", "")
        if header_flag and headers:
            for header in headers:
                # Append the header as-is
                full_cmd += f' {header_flag} "{header}"'

        # Update progress to show Running status
        progress.update(task_id,
                        description=f"    [bold blue]→[/bold blue] {tool_name}:{alias_name}\n      \t[bold green]Running[/bold green] {full_cmd}")

        def run_proc():
            try:
                # Add error handling environment variables for common tools
                env = os.environ.copy()
                env['PYTHONWARNINGS'] = 'ignore:Unverified HTTPS request'  # Suppress SSL warnings
                env['REQUESTS_CA_BUNDLE'] = ''  # Disable SSL verification for requests

                proc = subprocess.run(
                    full_cmd,
                    shell=True,
                    input=input_data,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env
                )

                # Strip colors if requested
                output = proc.stdout
                error_output = proc.stderr
                if strip_colors:
                    output = strip_ansi_codes(output)
                    error_output = strip_ansi_codes(error_output)

                return output, proc.returncode, error_output
            except Exception as e:
                return None, -1, str(e)

        try:
            stdout, rc, stderr = await loop.run_in_executor(None, run_proc)

            # Clean up error output - remove common noise
            if stderr:
                error_lines = stderr.split('\n')
                cleaned_error_lines = []
                for line in error_lines:
                    # Skip common warning messages and tracebacks
                    if any(skip in line.lower() for skip in [
                        'warning:', 'traceback', 'file "',
                        'line ', 'module', 'import',
                        'certificate', 'insecurerequest',
                        'urllib3'
                    ]):
                        continue
                    # Keep actual error messages
                    if line.strip() and not line.startswith(' '):
                        cleaned_error_lines.append(line.strip())
                cleaned_stderr = '\n'.join(cleaned_error_lines)
            else:
                cleaned_stderr = ""

            # Update progress to show Done/Failed status
            status = "[green]Done[/green]" if rc == 0 else "[red]Failed[/red]"
            progress.update(task_id,
                            description=f"    [bold blue]→[/bold blue] {tool_name}:{alias_name}\n      \t{status} {full_cmd}")

            if rc != 0:
                # Show simplified error message
                error_msg = "Command failed to execute properly" if not cleaned_stderr else cleaned_stderr
                console.print(f"\n[red]Error running {tool_name}:{alias_name}[/red]")
                console.print(f"[yellow]Details: {error_msg}[/yellow]")

                if debug:
                    console.print("\n[dim]Full error output:[/dim]")
                    console.print(stderr)

                # Continue with next task instead of halting
                return {"output": "", "success": False, "tool": f"{tool_name}:{alias_name}"}

            return {"output": stdout, "success": True, "tool": f"{tool_name}:{alias_name}"}

        except Exception as e:
            # Update progress to show error status
            progress.update(task_id,
                            description=f"    [bold blue]→[/bold blue] {tool_name}:{alias_name}\n      \t[red]Failed[/red] {full_cmd}")

            # Continue with next task instead of halting
            return {"output": "", "success": False, "tool": f"{tool_name}:{alias_name}"}

    def summarize_output(output, tool_name, show_full=False):
        """Create a summary of tool output based on the tool type."""
        if not output:
            return "No output"

        lines = output.strip().split('\n')

        # If show_full_output is True, return complete output
        if show_full:
            return output.strip()

        if tool_name.startswith('paramspider:'):
            params = [line for line in lines if '=' in line]
            return f"Discovered {len(params)} parameters"
        elif tool_name.startswith('arjun:'):
            params = [line for line in lines if line.startswith('[+]')]
            return '\n'.join(params) if params else "No parameters discovered"
        elif tool_name.startswith('katana:'):
            urls = [line for line in lines if line.startswith('http')]
            return f"Discovered {len(urls)} unique URLs"
        elif tool_name.startswith('gf:'):
            matches = [line for line in lines if line.startswith('http')]
            return f"Found {len(matches)} matches\n" + '\n'.join(matches)
        return f"{len(lines)} lines of output"

    async def run_flow():
        flow_def = load_flow(flow_name)
        stages = flow_def.get('stages', {})
        flow_order = flow_def.get('flow', [])
        total_stages = len(flow_order)
        last_output = None
        stage_results = []
        full_output = [] if save_output else None

        if save_output:
            full_output.append("Flow Execution Summary")
            full_output.append("=====================")

        with Progress(
                TextColumn("[progress.description]{task.description}"),
                TimeElapsedColumn(),
                console=console,
                expand=True,
                transient=True
        ) as progress:
            main_task = progress.add_task(
                description="",
                total=total_stages
            )

            for stage_index, stage_entry in enumerate(flow_order, 1):
                stage_name = stage_entry['stage']
                stage_def = stages.get(stage_name, {})
                stage_tools_results = []

                # Determine stage type
                stage_type = 'Parallel' if isinstance(stage_def, dict) and stage_def.get(
                    'parallel') else 'Sequential'
                if stage_type == 'Parallel':
                    stage_desc = stage_def.get('description', '')
                else:
                    stage_desc = ''

                # Update main progress with stage information
                progress.update(
                    main_task,
                    description=(
                        f"[bold cyan]{flow_def.get('name', 'Flow')}[/bold cyan]\n"
                        f"  Stage {stage_index}/{total_stages}: [yellow]{stage_name}[/yellow] ({stage_type})\n"
                        f"  {stage_desc if stage_desc else ''}"
                    )
                )

                # Track if any task in the stage succeeded
                stage_had_success = False

                if isinstance(stage_def, list):  # Sequential tasks
                    task_ids = []
                    for task in stage_def:
                        alias_str = task['alias']
                        desc = task.get('description', '')
                        task_id = progress.add_task(
                            f"    [bold blue]→[/bold blue] {alias_str}\n      {desc}",
                            total=None
                        )
                        task_ids.append((task_id, task))

                    for task_id, task in task_ids:
                        alias_str = task['alias']
                        tool_name, alias_name = alias_str.split(":", 1)
                        input_data = last_output if task.get('settings', {}).get(
                            'pipe_input') else None

                        # Pass headers to run_alias_async
                        result = await run_alias_async(tool_name, alias_name, progress, task_id,
                                                       input_data, print_step_output,
                                                       headers=parsed_headers)

                        if result['success']:
                            stage_had_success = True
                            if task.get('settings', {}).get('pipe_output'):
                                last_output = result['output']
                        stage_tools_results.append(result)

                elif stage_def.get('parallel'):  # Parallel tasks
                    tasks = stage_def['tasks']
                    task_ids = []

                    for task in tasks:
                        alias_str = task['alias']
                        desc = task.get('description', '')
                        task_id = progress.add_task(
                            f"    [bold blue]⇉[/bold blue] {alias_str}\n      {desc}",
                            total=None
                        )
                        task_ids.append((task_id, task))

                    coros = []
                    for task_id, task in task_ids:
                        alias_str = task['alias']
                        tool_name, alias_name = alias_str.split(":", 1)
                        pipe_input = task.get('pipe_input', False)
                        task_input = last_output if pipe_input else None
                        coros.append(
                            run_alias_async(tool_name, alias_name, progress, task_id, task_input,
                                            print_step_output, headers=parsed_headers)
                        )

                    try:
                        results = await asyncio.gather(*coros, return_exceptions=True)
                        for result in results:
                            if isinstance(result, Exception):
                                stage_tools_results.append(
                                    {"output": "", "success": False, "tool": "Unknown"})
                            else:
                                if result['success']:
                                    stage_had_success = True
                                stage_tools_results.append(result)

                        if stage_def.get('combine_output') and stage_had_success:
                            outputs = [r['output'] for r in results if
                                       isinstance(r, dict) and r['success']]
                            last_output = "\n".join(filter(None, outputs))
                    except Exception as e:
                        console.print(f"[red]Error in parallel execution: {str(e)}[/red]")
                        continue

                stage_results.append((stage_name, stage_tools_results))
                progress.update(main_task, advance=1)

            # After all stages complete, show the summary
            console.print("\n[bold cyan]Flow Execution Summary:[/bold cyan]")

            for stage_name, tools_results in stage_results:
                console.print(f"\n[bold blue]Stage: {stage_name}[/bold blue]")

                if save_output:
                    full_output.append(f"\nStage: {stage_name}")
                    full_output.append("=" * (len(stage_name) + 7))

                for result in tools_results:
                    if result['success']:
                        summary = summarize_output(result['output'], result['tool'],
                                                   show_full_output)
                        console.print(f"[green]✓[/green] {result['tool']}:")
                        console.print(f"  {summary}")
                        if save_output:
                            full_output.append(f"\n✓ {result['tool']}:")
                            full_output.append(result['output'].strip())
                    else:
                        console.print(f"[red]✗[/red] {result['tool']}: Failed")
                        if save_output:
                            full_output.append(f"\n✗ {result['tool']}: Failed")

            # Save output if requested
            if save_output:
                try:
                    with open(output_file, 'w') as f:
                        f.write('\n'.join(full_output))
                    console.print(f"\n[green]Output saved to: {output_file}[/green]")
                except Exception as e:
                    console.print(f"\n[red]Error saving output: {str(e)}[/red]")

    asyncio.run(run_flow())


if __name__ == "__main__":
    cli()
