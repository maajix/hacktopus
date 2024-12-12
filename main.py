import os
import re
import subprocess
import asyncio
from urllib.parse import urlparse
from typing import Tuple, Dict, Any, List

import click
import yaml
from rich.console import Console
from rich.progress import Progress, TextColumn, TimeElapsedColumn, TaskID
from rich.table import Table
from rich.tree import Tree

console = Console()


def load_global_config() -> Dict[str, Any]:
    """Load the global configuration from global_config.yaml."""
    config_path = os.path.join(os.getcwd(), "global_config.yaml")
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            data = yaml.safe_load(f)
            return data if data is not None else {}
    return {}


global_config = load_global_config()


def strip_ansi_codes(text: str) -> str:
    """Remove ANSI color codes from text."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text) if text else text


def load_tool(tool_name: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Load tool configuration and aliases."""
    paths = global_config.get("paths", {})
    tools_dir = paths.get("tools_dir", "./tools")
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


def load_flow(flow_name: str) -> Dict[str, Any]:
    """Load flow configuration."""
    paths = global_config.get("paths", {})
    flows_dir = paths.get("flows_dir", "./flows")
    flow_file = os.path.join(flows_dir, f"{flow_name}.yaml")

    if os.path.exists(flow_file):
        with open(flow_file, 'r') as f:
            return yaml.safe_load(f) or {}
    return {}


@click.group()
def cli():
    """CLI tool for orchestrating pentest flows and aliases."""
    pass


@cli.command(name="tools")
@click.option('--tag', help="Filter tools by a tag substring")
def tools_command(tag: str):
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
def create_tool(name: str):
    """Create a new tool directory with config and aliases files."""
    tools_dir = global_config.get("paths", {}).get("tools_dir", "./tools")
    tool_dir = os.path.join(tools_dir, name)

    if os.path.exists(tool_dir):
        console.print(f"[red]Tool directory '{name}' already exists.[/red]")
        return

    try:
        os.makedirs(tool_dir, exist_ok=True)

        config_content = {
            "description": "",
            "tags": [],
            "run_command": "",
            "accepts_stdin": True,
            "header_flag": ""
        }
        with open(os.path.join(tool_dir, "config.yaml"), 'w') as f:
            yaml.dump(config_content, f, sort_keys=False)

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


def prompt_and_clear(prompt_text: str, default=None) -> str:
    """Prompt the user for input and clear the prompt line after input is received."""
    user_input = click.prompt(prompt_text, default=default)
    # ANSI escape codes:
    # \033[F moves the cursor up by one line
    # \033[K clears from the cursor to the end of the line
    console.print("\033[F\033[K", end="")
    return user_input


@cli.command(name="exec")
@click.argument('alias_name')
@click.argument('args', nargs=-1)
@click.option('--headers', multiple=True,
              help='Headers to include, in "Key:Value" format.')
def exec_command(alias_name: str, args: tuple, headers: tuple):
    """
    Execute a given alias with optional arguments.
    Example: exec nmap:default-enum 192.168.1.1 --headers "User-Agent:Mozilla" --headers "Auth:Bearer xyz"
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

    var_map = {var_def['name']: args[i] for i, var_def in enumerate(variables)}

    for var_name, var_val in var_map.items():
        cmd_template = cmd_template.replace(f"{{{{{var_name}}}}}", var_val)

    run_command = tool_config.get("run_command")
    if not run_command:
        console.print(f"[red]Tool '{tool_name}' has no run_command defined.[/red]")
        return

    header_flag = tool_config.get("header_flag", "")
    if header_flag and headers:
        for header in headers:
            if ':' not in header:
                console.print(f"[red]Invalid header format: '{header}'. Use 'Key:Value'[/red]")
                return
            key, value = header.split(':', 1)
            cmd_template += f' {header_flag} "{key.strip()}: {value.strip()}"'

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
def flow_list(tag: str):
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

            if not flow_def:
                continue

            desc = flow_def.get("description", "")
            flow_tags = flow_def.get("tags", [])

            if tag:
                tag_lower = tag.lower()
                if not any(tag_lower in t.lower() for t in flow_tags):
                    continue

            tags_str = ", ".join(flow_tags) if flow_tags else ""
            table.add_row(flow_name, tags_str, desc)

    console.print(table)


@flow.command(name="info")
@click.argument('flow_name')
def flow_info_command(flow_name: str):
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
    console.print(flow_tree)


def validate_task(task: Dict[str, Any], var_values: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Validate a single task configuration.

    Args:
        task (dict): Task configuration to validate
        var_values (dict): Variables available for the flow

    Returns:
        tuple: (is_valid, error_message)
    """
    if 'alias' in task:
        alias_str = task['alias']
        if ':' not in alias_str:
            return False, f"Alias '{alias_str}' not in 'tool:alias' format"

        tool_name, alias_name = alias_str.split(":", 1)

        tools_dir = global_config.get("paths", {}).get("tools_dir", "./tools")
        tool_path = os.path.join(tools_dir, tool_name)
        if not os.path.isdir(tool_path):
            return False, f"Tool '{tool_name}' directory not found"

        tool_config, tool_aliases = load_tool(tool_name)

        if alias_name not in tool_aliases:
            return False, f"Alias '{alias_name}' not found in tool '{tool_name}'."

        if 'settings' in task:
            settings = task['settings']
            header_flag = tool_config.get("header_flag", "")
            accepts_stdin = tool_config.get("accepts_stdin", True) if header_flag else True

            if settings.get('pipe_input', False) and not accepts_stdin:
                return False, f"Tool '{tool_name}' does not accept stdin, but pipe_input is true"

            for setting, value in settings.items():
                if setting in ['pipe_input', 'pipe_output', 'print_output'] and not isinstance(
                        value, bool):
                    return False, f"Setting '{setting}' must be a boolean"

        if 'variables' in task:
            alias_def = tool_aliases[alias_name]
            required_vars = {var_def['name'] for var_def in alias_def.get("variables", [])}

            task_vars = task['variables']
            for var_name in task_vars:
                if var_name not in required_vars:
                    return False, f"Variable '{var_name}' provided but not required by alias '{alias_name}'"

            for var_name in required_vars:
                if var_name not in task_vars and var_name not in var_values:
                    return False, f"Required variable '{var_name}' missing for alias '{alias_name}'"

    elif 'flow' in task:
        flow_name = task['flow']
        flow_def = load_flow(flow_name)
        if not flow_def:
            return False, f"Referenced flow '{flow_name}' does not exist."

    else:
        return False, "Task must have either 'alias' or 'flow' key."

    if 'settings' in task:
        settings = task['settings']
        if settings.get('pipe_input', False):
            if 'alias' in task:
                tool_name = task['alias'].split(':', 1)[0]
                tool_config, _ = load_tool(tool_name)
                accepts_stdin = tool_config.get("accepts_stdin", True)
                if not accepts_stdin:
                    return False, f"Tool '{tool_name}' does not accept stdin, but pipe_input is true"

        for setting, value in settings.items():
            if setting in ['pipe_input', 'pipe_output', 'print_output'] and not isinstance(value,
                                                                                           bool):
                return False, f"Setting '{setting}' must be a boolean"

    return True, None


def validate_flow(flow_def: Dict[str, Any], var_values: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate the entire flow configuration."""
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
@click.option('--headers', multiple=True,
              help='Headers to include, in "Key:Value" format.')
@click.pass_context
def flow_run_command(ctx, flow_name: str, print_step_output: bool, strip_colors: bool, debug: bool,
                     show_full_output: bool, save_output: bool, headers: tuple):
    """Run a defined flow with error checking and optional color stripping."""
    flow_def = load_flow(flow_name)
    if not flow_def:
        console.print(f"[red]Flow '{flow_name}' not found.[/red]")
        return

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
            var_values[var_name] = prompt_and_clear(
                f"Please provide a value for variable '{var_name}'")

    # Parse and validate headers
    parsed_headers = []
    for header in headers:
        if ':' not in header:
            console.print(f"[red]Invalid header format: '{header}'. Use 'Key:Value'[/red]")
            return
        key, value = header.split(':', 1)
        parsed_headers.append((key.strip(), value.strip()))

    valid, error_msg = validate_flow(flow_def, var_values)
    if not valid:
        console.print(f"[red]{error_msg}[/red]")
        return

    stages = flow_def.get('stages', {})
    flow_order = flow_def.get('flow', [])
    stage_results = []
    full_output = [] if save_output else None
    previous_stage_output = None  # This will hold the final output

    def transform_value(value: str, transform_type: str) -> str:
        """Transform a value based on the specified transformation type."""
        if transform_type == "url_to_domain":
            domain = urlparse(value).netloc
            return domain.removeprefix('www.')
        return value

    async def run_alias_async(tool_name: str, alias_name: str, progress: Progress, task_id: TaskID,
                              input_data: str = None, print_step_output: bool = False,
                              headers: List[Tuple[str, str]] = None) -> Dict[str, Any]:
        """Execute a tool alias with real-time progress updates and improved error handling."""
        loop = asyncio.get_event_loop()
        tool_config, tool_aliases = load_tool(tool_name)
        alias_def = tool_aliases[alias_name]
        cmd_template = alias_def.get("command", "")
        variables = alias_def.get("variables", [])

        processed_vars = var_values.copy()
        for var_def in variables:
            vname = var_def['name']
            if vname in processed_vars and 'transform' in var_def:
                transform_type = var_def['transform']
                original = processed_vars[vname]
                processed_vars[vname] = transform_value(original, transform_type)

        for var_def in variables:
            vname = var_def['name']
            if vname in processed_vars:
                cmd_template = cmd_template.replace(f"{{{{{vname}}}}}", processed_vars[vname])

        run_command = tool_config.get("run_command")
        full_cmd = f"{run_command} {cmd_template}"

        header_flag = tool_config.get("header_flag", "")
        if header_flag and headers:
            for key, value in headers:
                full_cmd += f' {header_flag} "{key}: {value}"'

        progress.update(task_id,
                        description=f"    [bold blue]→[/bold blue] {tool_name}:{alias_name}\n      \t[bold green]Running[/bold green] {full_cmd}")

        def run_proc():
            try:
                env = os.environ.copy()
                env['PYTHONWARNINGS'] = 'ignore:Unverified HTTPS request'
                env['REQUESTS_CA_BUNDLE'] = ''

                proc = subprocess.run(
                    full_cmd,
                    shell=True,
                    input=input_data,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env
                )

                output = strip_ansi_codes(proc.stdout) if strip_colors else proc.stdout
                error_output = strip_ansi_codes(proc.stderr) if strip_colors else proc.stderr

                return output, proc.returncode, error_output
            except Exception as e:
                return None, -1, str(e)

        try:
            stdout, rc, stderr = await loop.run_in_executor(None, run_proc)

            if stderr:
                error_lines = stderr.split('\n')
                cleaned_error_lines = [
                    line.strip() for line in error_lines
                    if not any(skip in line.lower() for skip in [
                        'warning:', 'traceback', 'file "',
                        'line ', 'module', 'import',
                        'certificate', 'insecurerequest',
                        'urllib3'
                    ]) and line.strip() and not line.startswith(' ')
                ]
                cleaned_stderr = '\n'.join(cleaned_error_lines)
            else:
                cleaned_stderr = ""

            status = "[green]Done[/green]" if rc == 0 else "[red]Failed[/red]"
            progress.update(task_id,
                            description=f"    [bold blue]→[/bold blue] {tool_name}:{alias_name}\n      \t{status} {full_cmd}")

            if rc != 0:
                error_msg = "Command failed to execute properly" if not cleaned_stderr else cleaned_stderr
                console.print(f"\n[red]Error running {tool_name}:{alias_name}[/red]")
                console.print(f"[yellow]Details: {error_msg}[/yellow]")

                if debug:
                    console.print("\n[dim]Full error output:[/dim]")
                    console.print(stderr)

                return {"output": "", "success": False, "tool": f"{tool_name}:{alias_name}"}

            return {"output": stdout, "success": True, "tool": f"{tool_name}:{alias_name}"}

        except Exception as e:
            progress.update(task_id,
                            description=f"    [bold blue]→[/bold blue] {tool_name}:{alias_name}\n      \t[red]Failed[/red] {full_cmd}")
            return {"output": "", "success": False, "tool": f"{tool_name}:{alias_name}"}

    def summarize_output(output: str, tool_name: str, show_full: bool) -> str:
        """Create a summary of tool output based on the tool type."""
        if not output:
            return "No output"

        lines = output.strip().split('\n')

        if show_full:
            return output.strip()

        if tool_name.startswith('paramspider:'):
            params = [line for line in lines if '=' in line]
            return f"  - Discovered {len(params)} parameters"
        elif tool_name.startswith('arjun:'):
            params = [line for line in lines if line.startswith('[+]')]
            return '\n'.join(params) if params else "  - No parameters discovered"
        elif tool_name.startswith('katana:'):
            urls = [line for line in lines if line.startswith('http')]
            return f"  - Discovered {len(urls)} unique URLs"
        elif tool_name.startswith('gf:'):
            matches = [line for line in lines if line.startswith('http')]
            return f"  - Found {len(matches)} matches"
        return f"  - {len(lines)} lines of output"

    async def run_flow():
        nonlocal previous_stage_output  # Declare that we will modify the outer variable
        stages_local = flow_def.get('stages', {})
        flow_order_local = flow_def.get('flow', [])
        total_stages = len(flow_order_local)
        stage_results_local = []
        full_output_local = [] if save_output else None

        def debug_print(msg: str, data: Any = None):
            if debug:
                console.print(f"\n[cyan]DEBUG:[/cyan] {msg}")
                if data:
                    console.print("[cyan]---START---[/cyan]")
                    console.print(data.strip() if isinstance(data, str) else data)
                    console.print("[cyan]---END---[/cyan]")

        if save_output:
            full_output_local.extend(["Flow Execution Summary", "====================="])

        with Progress(
                TextColumn("[progress.description]{task.description}"),
                TimeElapsedColumn(),
                console=console,
                expand=True,
                transient=True
        ) as progress:
            main_task = progress.add_task(description="", total=total_stages)

            for stage_index, stage_entry in enumerate(flow_order_local, 1):
                stage_name = stage_entry['stage']
                stage_def = stages_local.get(stage_name, {})
                stage_tools_results = []
                current_stage_output = None

                debug_print(f"Starting stage: {stage_name}")
                debug_print("Previous stage output:", previous_stage_output)

                stage_type = 'Parallel' if isinstance(stage_def, dict) and stage_def.get(
                    'parallel') else 'Sequential'
                stage_desc = stage_def.get('description', '') if isinstance(stage_def, dict) else ''

                progress.update(
                    main_task,
                    description=(
                        f"[bold cyan]{flow_def.get('name', 'Flow')}[/bold cyan]\n"
                        f"  Stage {stage_index}/{total_stages}: [yellow]{stage_name}[/yellow] ({stage_type})\n"
                        f"  {stage_desc}"
                    )
                )

                if isinstance(stage_def, list):  # Sequential tasks
                    for task in stage_def:
                        alias_str = task['alias']
                        task_id = progress.add_task(
                            f"    [bold blue]→[/bold blue] {alias_str}\n      {task.get('description', '')}",
                            total=None
                        )

                        tool_name_task, alias_name = alias_str.split(":", 1)
                        should_pipe_input = task.get('settings', {}).get('pipe_input', True)
                        input_data = previous_stage_output if should_pipe_input else None

                        debug_print(f"Running task: {alias_str}")
                        debug_print("Task input data:", input_data)

                        result = await run_alias_async(
                            tool_name_task,
                            alias_name,
                            progress,
                            task_id,
                            input_data,
                            print_step_output,
                            headers=parsed_headers
                        )

                        if result['success']:
                            should_pipe_output = task.get('settings', {}).get('pipe_output', True)
                            if should_pipe_output:
                                current_stage_output = result['output'].strip() if result[
                                    'output'] else None
                                debug_print(f"Task output (pipe_output={should_pipe_output}):",
                                            current_stage_output)
                            else:
                                debug_print(
                                    f"Task output not piped (pipe_output={should_pipe_output})")

                        stage_tools_results.append(result)

                elif stage_def.get('parallel'):  # Parallel tasks
                    parallel_tasks = stage_def['tasks']
                    task_ids = []
                    coros = []

                    for task in parallel_tasks:
                        alias_str = task['alias']
                        task_id = progress.add_task(
                            f"    [bold blue]⇉[/bold blue] {alias_str}\n      {task.get('description', '')}",
                            total=None
                        )
                        task_ids.append((task_id, task))

                    debug_print(f"Starting parallel execution with {len(parallel_tasks)} tasks")

                    for task_id, task in task_ids:
                        alias_str = task['alias']
                        tool_name_task, alias_name = alias_str.split(":", 1)
                        should_pipe_input = task.get('settings', {}).get('pipe_input', True)
                        input_data = previous_stage_output if should_pipe_input else None

                        debug_print(f"Preparing parallel task: {alias_str}")
                        debug_print("Task input data:", input_data)

                        coros.append(
                            run_alias_async(
                                tool_name_task,
                                alias_name,
                                progress,
                                task_id,
                                input_data,
                                print_step_output,
                                headers=parsed_headers
                            )
                        )

                    try:
                        results = await asyncio.gather(*coros, return_exceptions=True)
                        parallel_outputs = []

                        for (task_id, task), result in zip(task_ids, results):
                            if isinstance(result, Exception):
                                debug_print(
                                    f"Error in parallel task {task['alias']}: {str(result)}")
                                stage_tools_results.append(
                                    {"output": "", "success": False, "tool": task['alias']})
                            else:
                                stage_tools_results.append(result)
                                if result['success']:
                                    should_pipe_output = task.get('settings', {}).get('pipe_output',
                                                                                      True)
                                    if should_pipe_output and result['output']:
                                        parallel_outputs.append(result['output'].strip())
                                        debug_print(f"Parallel task output ({task['alias']}):",
                                                    result['output'].strip())

                        if stage_def.get('combine_output') and parallel_outputs:
                            current_stage_output = "\n".join(filter(None, parallel_outputs))
                            debug_print("Combined parallel outputs:", current_stage_output)

                    except Exception as e:
                        debug_print(f"Error in parallel execution: {str(e)}")

                debug_print(f"Stage {stage_name} completed")
                debug_print("Final stage output:", current_stage_output)

                previous_stage_output = current_stage_output  # Update the outer variable
                debug_print("Updated pipeline state for next stage:", previous_stage_output)

                stage_results_local.append((stage_name, stage_tools_results))

                if save_output:
                    full_output_local.append(f"\nStage: {stage_name}")
                    full_output_local.append("=" * (len(stage_name) + 7))

                    for result in stage_tools_results:
                        if result['success']:
                            full_output_local.append(f"\n✓ {result['tool']}:")
                            full_output_local.append(
                                result['output'].strip() if result['output'] else "No output")
                        else:
                            full_output_local.append(f"\n✗ {result['tool']}: Failed")

                progress.update(main_task, advance=1)

        # After all stages are complete, handle output display and saving
        # Display outputs based on --show-full-output
        if show_full_output:
            console.print("\n[bold cyan]Flow Execution Details:[/bold cyan]")
            for stage_name, tools_results in stage_results_local:
                console.print(f"\n[bold blue]Stage: {stage_name}[/bold blue]")

                for result in tools_results:
                    if result['success']:
                        console.print(f"[green]✓[/green] {result['tool']}:")
                        console.print(
                            f"{result['output'].strip() if result['output'] else 'No output'}")
                    else:
                        console.print(f"[red]✗[/red] {result['tool']}: Failed")
        else:
            console.print("\n[bold cyan]Flow Execution Summary:[/bold cyan]")
            for stage_name, tools_results in stage_results_local:
                console.print(f"\n[bold blue]Stage: {stage_name}[/bold blue]")

                for result in tools_results:
                    if result['success']:
                        summary = summarize_output(result['output'], result['tool'],
                                                   show_full_output)
                        console.print(f"[green]✓[/green] {result['tool']}:")
                        console.print(f"  {summary}")
                    else:
                        console.print(f"[red]✗[/red] {result['tool']}: Failed")

        # **Print Final Output**
        if previous_stage_output:
            console.print("\n[bold cyan]Final Output:[/bold cyan]")
            console.print("=============")
            console.print(previous_stage_output if previous_stage_output else "No final output")

        # Save outputs to file if --save-output is used
        if save_output:
            if show_full_output:
                # Save full outputs
                with open(output_file, 'w') as f:
                    f.write("Flow Execution Details\n")
                    f.write("======================\n")
                    for stage_name, tools_results in stage_results_local:
                        f.write(f"\nStage: {stage_name}\n")
                        f.write("=" * (len(stage_name) + 7) + "\n")
                        for result in tools_results:
                            if result['success']:
                                f.write(f"\n✓ {result['tool']}:\n")
                                f.write(
                                    f"{result['output'].strip() if result['output'] else 'No output'}\n")
                            else:
                                f.write(f"\n✗ {result['tool']}: Failed\n")
            else:
                # Save summaries
                with open(output_file, 'w') as f:
                    f.write("Flow Execution Summary\n")
                    f.write("=======================\n")
                    for stage_name, tools_results in stage_results_local:
                        f.write(f"\nStage: {stage_name}\n")
                        f.write("=" * (len(stage_name) + 7) + "\n")
                        for result in tools_results:
                            if result['success']:
                                summary = summarize_output(result['output'], result['tool'],
                                                           show_full_output)
                                f.write(f"\n✓ {result['tool']}:\n")
                                f.write(f"  {summary}\n")
                            else:
                                f.write(f"\n✗ {result['tool']}: Failed\n")

            # Inside run_flow()
            if save_output:
                with open(output_file, 'w') as f:
                    # Write initial headers
                    f.write("Flow Execution Details\n")
                    f.write("======================\n")

                    # Write stage results
                    for stage_name, tools_results in stage_results_local:
                        f.write(f"\nStage: {stage_name}\n")
                        f.write("=" * (len(stage_name) + 7) + "\n")
                        for result in tools_results:
                            if result['success']:
                                if show_full_output:
                                    f.write(f"\n✓ {result['tool']}:\n")
                                    f.write(
                                        f"{result['output'].strip() if result['output'] else 'No output'}\n")
                                else:
                                    summary = summarize_output(result['output'], result['tool'],
                                                               show_full_output)
                                    f.write(f"\n✓ {result['tool']}:\n")
                                    f.write(f"  {summary}\n")
                            else:
                                f.write(f"\n✗ {result['tool']}: Failed\n")

                    # Write final output in the same file handle
                    if previous_stage_output:
                        f.write("\nFinal Output:\n")
                        f.write("=============\n")
                        f.write(f"{previous_stage_output}\n")

                console.print(f"\n[green]Output saved to: {output_file}[/green]")
    asyncio.run(run_flow())


if __name__ == "__main__":
    cli()
