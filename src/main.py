from rich.console import Console

from cli.click_manager import create_cli

console = Console()

if __name__ == '__main__':
    # Dynamically create a Click CLI based on variables in the flow configuration
    cli = create_cli()
    cli()
