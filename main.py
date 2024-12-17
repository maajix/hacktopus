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
    """Load global configuration from global_config.yaml."""
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


async def run_flow_internal(
        flow_def: Dict[str, Any],
        var_values: Dict[str, str],
        progress: Progress = None,
        input_data: str = None,
        print_step_output: bool = False,
        headers: List[Tuple[str, str]] = None,
        strip_colors: bool = False,
        debug: bool = False,
        flow_depth: int = 0
) -> Dict[str, Any]:
    """
    Core flow execution logic that can be called recursively.
    Ensures only one Progress instance is active at once.
    """
    if flow_depth > 5:
        return {"output": "", "success": False, "error": "Maximum flow nesting depth exceeded"}

    # If no progress object is passed in, create one here
    new_progress_created = False
    if progress is None:
        progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=console,
            expand=True,
            transient=True
        )
        new_progress_created = True
        progress.start()

    def debug_print(msg: str, data: Any = None):
        if debug:
            console.print(f"\n[cyan]DEBUG:[/cyan] {msg}")
            if data:
                console.print("[cyan]---START---[/cyan]")
                console.print(data.strip() if isinstance(data, str) else data)
                console.print("[cyan]---END---[/cyan]")

    stages = flow_def.get('stages', {})
    flow_order = flow_def.get('flow', [])
    previous_stage_output = input_data
    stage_results = []

    # Create a 'main_task' to represent all stages in this flow
    main_task = progress.add_task(
        f"{flow_def.get('name', 'Flow')}",
        total=len(flow_order)
    )

    for stage_index, stage_entry in enumerate(flow_order, 1):
        stage_name = stage_entry['stage']
        stage_def = stages.get(stage_name, {})
        tasks = stage_def.get('tasks', [])
        is_parallel = stage_def.get('parallel', False)
        distribution = stage_def.get('distribution', 'broadcast')

        stage_tools_results = []
        current_stage_output = None

        debug_print(f"Starting stage: {stage_name}")
        debug_print("Previous stage output:", previous_stage_output)

        stage_label = "Parallel" if is_parallel else "Sequential"
        stage_desc = stage_def.get("description", "")

        # Update the main progress bar's task description
        progress.update(
            main_task,
            description=(
                f"[bold cyan]{flow_def.get('name', 'Flow')}[/bold cyan]\n"
                f"  Stage {stage_index}/{len(flow_order)}: [yellow]{stage_name}[/yellow] "
                f"({stage_label}, distribution={distribution})\n"
                f"  {stage_desc}"
            )
        )

        if is_parallel and distribution == "broadcast":
            # Parallel "broadcast" means every task runs concurrently
            coros = []
            task_ids = []
            for task in tasks:
                task_desc = task.get('alias', task.get('command', task.get('flow', 'Unknown')))
                task_id = progress.add_task(
                    f"[bold blue]⇉[/bold blue] {task_desc} - {task.get('description', '')}",
                    total=None
                )
                task_ids.append((task_id, task))

                # Decide input
                broadcast_input = previous_stage_output if task.get('settings', {}).get(
                    'pipe_input', True) else None

                if 'flow' in task:
                    child_flow = load_flow(task['flow'])
                    if child_flow:
                        child_vars = {
                            k: var_values.get(v[2:-2], v) if v.startswith('{{') else v
                            for k, v in task.get('variables', {}).items()
                        }
                        coros.append(run_flow_internal(
                            child_flow, child_vars, progress,
                            broadcast_input, print_step_output,
                            headers, strip_colors, debug, flow_depth + 1
                        ))
                    else:
                        coros.append(asyncio.sleep(0))

                elif 'alias' in task:
                    tool_name, alias_name = task['alias'].split(':', 1)
                    coros.append(run_alias_async(
                        tool_name, alias_name, progress, task_id,
                        broadcast_input, print_step_output, headers,
                        strip_colors, debug, var_values
                    ))

                elif 'command' in task:
                    coros.append(run_command_async(
                        task['command'], var_values, progress, task_id,
                        broadcast_input, print_step_output, strip_colors, debug
                    ))

            results = await asyncio.gather(*coros, return_exceptions=True)
            combined_outputs = []
            for ((task_id, task), result) in zip(task_ids, results):
                if isinstance(result, Exception):
                    debug_print(f"Error in task: {task}", str(result))
                    stage_tools_results.append({
                        "output": "", "success": False, "tool": str(task)
                    })
                else:
                    stage_tools_results.append(result)
                    if result['success'] and result['output']:
                        combined_outputs.append(result['output'].strip())

            current_stage_output = "\n".join(combined_outputs) if combined_outputs else None

        elif distribution == "chained" and not is_parallel:
            # Sequential "chained" means each task feeds the next
            current_input = previous_stage_output
            for task in tasks:
                task_desc = task.get('alias', task.get('command', task.get('flow', 'Unknown')))
                task_id = progress.add_task(
                    f"[bold blue]→[/bold blue] {task_desc} - {task.get('description', '')}",
                    total=None
                )

                chain_input = current_input if task.get('settings', {}).get('pipe_input',
                                                                            True) else None

                if 'flow' in task:
                    child_flow = load_flow(task['flow'])
                    if child_flow:
                        child_vars = {
                            k: var_values.get(v[2:-2], v) if v.startswith('{{') else v
                            for k, v in task.get('variables', {}).items()
                        }
                        result = await run_flow_internal(
                            child_flow, child_vars, progress,
                            chain_input, print_step_output,
                            headers, strip_colors, debug, flow_depth + 1
                        )
                    else:
                        result = {
                            "output": "", "success": False,
                            "tool": f"flow:{task['flow']} (not found)"
                        }

                elif 'alias' in task:
                    tool_name, alias_name = task['alias'].split(':', 1)
                    result = await run_alias_async(
                        tool_name, alias_name, progress, task_id,
                        chain_input, print_step_output, headers,
                        strip_colors, debug, var_values
                    )

                elif 'command' in task:
                    result = await run_command_async(
                        task['command'], var_values, progress, task_id,
                        chain_input, print_step_output, strip_colors, debug
                    )

                stage_tools_results.append(result)

                # The output of one task becomes the next task's input if pipe_output is true
                if result['success'] and result['output'] and task.get('settings', {}).get(
                        'pipe_output', True):
                    current_input = result['output'].strip()
                else:
                    current_input = None

            current_stage_output = current_input

        debug_print(f"Stage {stage_name} completed", stage_tools_results)
        debug_print("Final stage output:", current_stage_output)

        previous_stage_output = current_stage_output
        stage_results.append((stage_name, stage_tools_results))
        progress.update(main_task, advance=1)

    # If we created the progress instance, we stop it
    if new_progress_created:
        progress.stop()

    return {"output": previous_stage_output, "success": True, "stage_results": stage_results}


def load_flow(flow_name: str) -> Dict[str, Any]:
    """Load flow configuration from flows_dir."""
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
    """Prompt the user for input."""
    return click.prompt(prompt_text, default=default)


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

        is_parallel = stage_def.get('parallel', False)
        distribution = stage_def.get('distribution', 'broadcast')
        tasks = stage_def.get('tasks', [])

        if is_parallel:
            node_label = f"● PARALLEL: {stage_name} (distribution={distribution})"
        else:
            node_label = f"● SEQUENTIAL: {stage_name} (distribution={distribution})"

        stage_node = flow_tree.add(node_label)

        stage_desc = stage_def.get("description", "")
        if stage_desc:
            stage_node.add(f"└── Description: {stage_desc}")

        for task in tasks:
            if 'alias' in task:
                t_alias = task['alias']
                task_label = f"[green]{t_alias}[/green]"
            elif 'command' in task:
                t_cmd = task['command']
                task_label = f"[green]Command: {t_cmd}[/green]"
            else:
                task_label = "[red]Unknown task type[/red]"

            task_node = stage_node.add(f"● {task_label} - {task.get('description', '')}")
            configs = task.get('settings', {})
            for key_ in ['pipe_input', 'pipe_output', 'print_output']:
                if key_ in configs and configs[key_] is True:
                    task_node.add(f"└── {key_}: true")

    console.print()
    console.print(flow_tree)


def validate_task(task: Dict[str, Any], var_values: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate a single task configuration (alias or command)."""
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
        return True, None

    elif 'command' in task:
        cmd = task['command']
        pattern = re.compile(r"{{(.*?)}}")
        vars_in_cmd = pattern.findall(cmd)
        for var_name in vars_in_cmd:
            if var_name.strip() not in var_values:
                return False, f"Variable '{var_name}' not provided for command task"

        if 'settings' in task:
            settings = task['settings']
            for setting, value in settings.items():
                if setting in ['pipe_input', 'pipe_output', 'print_output'] and not isinstance(
                        value, bool):
                    return False, f"Setting '{setting}' must be a boolean in command task"
        return True, None

    elif 'flow' in task:
        flow_name = task['flow']
        flow_def = load_flow(flow_name)
        if not flow_def:
            return False, f"Referenced flow '{flow_name}' not found"

        # Validate variable mapping
        child_vars = task.get('variables', {})
        for var_name, var_value in child_vars.items():
            if var_value.startswith('{{') and var_value[2:-2] not in var_values:
                return False, f"Parent variable '{var_value}' not found"

        return True, None

    else:
        return False, "Task must have either 'alias' or 'command' key."


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
            return False, f"Stage '{stage_name}' not defined in stages"

        stage_def = stages[stage_name]
        tasks = stage_def.get('tasks', [])
        if not tasks:
            return False, f"Stage '{stage_name}' has no 'tasks' defined."

        distribution = stage_def.get('distribution', 'broadcast')
        is_parallel = stage_def.get('parallel', False)

        # Not allowed: parallel + chained
        if is_parallel and distribution == "chained":
            return False, f"Stage '{stage_name}' is parallel with distribution='chained' which is not allowed."

        for task in tasks:
            valid, msg = validate_task(task, var_values)
            if not valid:
                return False, f"In stage '{stage_name}': {msg}"

    return True, None


async def run_alias_async(tool_name: str, alias_name: str, progress: Progress, task_id: TaskID,
                          input_data: str = None, print_step_output: bool = False,
                          headers: List[Tuple[str, str]] = None, strip_colors: bool = False,
                          debug: bool = False, var_values: Dict[str, str] = None) -> Dict[str, Any]:
    """Execute a tool alias with real-time progress."""
    loop = asyncio.get_event_loop()
    tool_config, tool_aliases = load_tool(tool_name)
    alias_def = tool_aliases[alias_name]
    cmd_template = alias_def.get("command", "")
    variables = alias_def.get("variables", [])

    processed_vars = var_values.copy() if var_values else {}

    def transform_value(value: str, transform_type: str) -> str:
        if transform_type == "url_to_domain":
            domain = urlparse(value).netloc
            return domain.removeprefix('www.')
        return value

    for var_def in variables:
        vname = var_def['name']
        if vname in processed_vars and 'transform' in var_def:
            processed_vars[vname] = transform_value(processed_vars[vname], var_def['transform'])

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
                if line.strip() and not any(skip in line.lower() for skip in [
                    'warning:', 'traceback', 'file "',
                    'line ', 'module', 'import',
                    'certificate', 'insecurerequest',
                    'urllib3'
                ])
            ]
            cleaned_stderr = '\n'.join(cleaned_error_lines)
        else:
            cleaned_stderr = ""

        status = "[green]Done[/green]" if rc == 0 else "[red]Failed[/red]"
        progress.update(task_id,
                        description=f"    [bold blue]→[/bold blue] {tool_name}:{alias_name}\n      \t{status} {full_cmd}")

        if rc != 0:
            error_msg = cleaned_stderr if cleaned_stderr else "Command failed to execute properly"
            console.print(f"\n[red]Error running {tool_name}:{alias_name}[/red]")
            console.print(f"[yellow]Details: {error_msg}[/yellow]")

            if debug:
                console.print("\n[dim]Full error output:[/dim]")
                console.print(stderr)
            return {"output": "", "success": False, "tool": f"{tool_name}:{alias_name}"}

        if print_step_output and stdout:
            console.print("\n[bold white]Step Output:[/bold white]")
            console.print(stdout.strip())

        return {"output": stdout, "success": True, "tool": f"{tool_name}:{alias_name}"}

    except Exception as e:
        progress.update(task_id,
                        description=f"    [bold blue]→[/bold blue] {tool_name}:{alias_name}\n      \t[red]Failed[/red] {full_cmd}")
        return {"output": "", "success": False, "tool": f"{tool_name}:{alias_name}"}


async def run_command_async(command: str,
                            var_values: Dict[str, str],
                            progress: Progress,
                            task_id: TaskID,
                            input_data: str = None,
                            print_step_output: bool = False,
                            strip_colors: bool = False,
                            debug: bool = False) -> Dict[str, Any]:
    """Execute a direct command with variable substitution and I/O handling."""
    loop = asyncio.get_event_loop()
    for var_name, var_val in var_values.items():
        command = command.replace(f"{{{{{var_name}}}}}", var_val)

    def run_proc():
        env = os.environ.copy()
        proc = subprocess.run(
            command,
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

    progress.update(task_id,
                    description=f"    [bold blue]→[/bold blue] Running Command\n      \t[bold green]Executing[/bold green] {command}")

    try:
        stdout, rc, stderr = await loop.run_in_executor(None, run_proc)

        if stderr:
            error_lines = stderr.split('\n')
            cleaned_error_lines = [
                line.strip() for line in error_lines
                if line.strip() and not any(skip in line.lower() for skip in [
                    'warning:', 'traceback', 'file "',
                    'line ', 'module', 'import',
                    'certificate', 'insecurerequest',
                    'urllib3'
                ])
            ]
            cleaned_stderr = '\n'.join(cleaned_error_lines)
        else:
            cleaned_stderr = ""

        status = "[green]Done[/green]" if rc == 0 else "[red]Failed[/red]"
        progress.update(task_id,
                        description=f"    [bold blue]→[/bold blue] Running Command\n      \t{status} {command}")

        if rc != 0:
            error_msg = cleaned_stderr if cleaned_stderr else "Command failed to execute properly"
            console.print(f"\n[red]Error running command[/red]")
            console.print(f"[yellow]Details: {error_msg}[/yellow]")

            if debug:
                console.print("\n[dim]Full error output:[/dim]")
                console.print(stderr)

            return {"output": "", "success": False, "tool": f"command:{command}"}

        if print_step_output and stdout:
            console.print("\n[bold white]Command Output:[/bold white]")
            console.print(stdout.strip())

        return {"output": stdout, "success": True, "tool": f"command:{command}"}

    except Exception as e:
        progress.update(task_id,
                        description=f"    [bold blue]→[/bold blue] Running Command\n      \t[red]Failed[/red] {command}")
        return {"output": "", "success": False, "tool": f"command:{command}"}


def summarize_output(output: str, tool_name: str, show_full: bool) -> str:
    """Create a summary of tool/command output."""
    if not output:
        return "No output"
    lines = output.strip().split('\n')
    if show_full:
        return output.strip()

    # Basic heuristics
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
    elif tool_name.startswith('command:'):
        return f"  - {len(lines)} lines of output"
    return f"  - {len(lines)} lines of output"


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
    """Run a defined flow with simplified broadcast/chained logic."""

    flow_def = load_flow(flow_name)
    if not flow_def:
        console.print(f"[red]Flow '{flow_name}' not found.[/red]")
        return

    if save_output:
        results_dir = "results"
        os.makedirs(results_dir, exist_ok=True)
        output_file = os.path.join(results_dir, f"{flow_name}_output.txt")

    # parse variables from command line
    flow_vars = flow_def.get('variables', {})
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

    async def run_flow():
        # Create and start the top-level Progress once
        top_level_progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=console,
            expand=True,
            transient=True
        )
        top_level_progress.start()

        # Pass top_level_progress to run_flow_internal
        result = await run_flow_internal(
            flow_def,
            var_values,
            progress=top_level_progress,
            input_data=None,
            print_step_output=print_step_output,
            headers=parsed_headers,
            strip_colors=strip_colors,
            debug=debug
        )

        # Stop the single progress display
        top_level_progress.stop()

        # Summaries and final output
        if not show_full_output:
            console.print("\n[bold cyan]Flow Execution Summary:[/bold cyan]")
        else:
            console.print("\n[bold cyan]Flow Execution Details:[/bold cyan]")

        for stage_name, tools_results in result['stage_results']:
            console.print(f"\n[bold blue]Stage: {stage_name}[/bold blue]")
            for tool_result in tools_results:
                if tool_result['success']:
                    if show_full_output:
                        console.print(f"[green]✓[/green] {tool_result['tool']}:")
                        console.print(
                            tool_result['output'].strip() if tool_result['output'] else "No output")
                    else:
                        summary = summarize_output(tool_result['output'], tool_result['tool'],
                                                   show_full_output)
                        console.print(f"[green]✓[/green] {tool_result['tool']}:")
                        console.print(f"  {summary}")
                else:
                    console.print(f"[red]✗[/red] {tool_result['tool']}: Failed")

        if result['output']:
            console.print("\n[bold cyan]Final Output:[/bold cyan]")
            console.print("=============")
            console.print(result['output'])

        if save_output:
            with open(output_file, 'w') as f:
                f.write(f"Flow Execution {'Details' if show_full_output else 'Summary'}\n")
                f.write("=" * 30 + "\n\n")
                for stage_name, tools_results in result['stage_results']:
                    f.write(f"Stage: {stage_name}\n")
                    f.write("=" * (len(stage_name) + 7) + "\n")
                    for tool_result in tools_results:
                        if tool_result['success']:
                            if show_full_output:
                                f.write(f"\n✓ {tool_result['tool']}:\n")
                                f.write(tool_result['output'].strip() if tool_result[
                                    'output'] else "No output")
                                f.write("\n")
                            else:
                                summary = summarize_output(tool_result['output'],
                                                           tool_result['tool'], show_full_output)
                                f.write(f"\n✓ {tool_result['tool']}:\n  {summary}\n")
                        else:
                            f.write(f"\n✗ {tool_result['tool']}: Failed\n")

                if result['output']:
                    f.write("\nFinal Output:\n=============\n")
                    f.write(result['output'] + "\n")

            console.print(f"\n[green]Output saved to: {output_file}[/green]")

    asyncio.run(run_flow())


if __name__ == "__main__":
    cli()
