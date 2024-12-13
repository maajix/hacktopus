# 🐙 Hacktopus CLI

![Hacktopus CLI Banner](banner.png) <!-- Replace with your banner image URL -->

**Hacktopus CLI** is a powerful command-line interface crafted to streamline and orchestrate penetration testing workflows. Tailored for security professionals, it facilitates the management, execution, and automation of complex pentest flows using customizable tools and aliases.

## 🛠️ Features

- **Tool Management:** Easily list, filter, and manage penetration testing or bug bounty hunting tools
- **Alias Management:** Create and manage aliases for tool commands to simplify usage
- **Flow Orchestration:** Define and execute complex pentest flows comprising multiple tools and stages
- **Customizable Outputs:** View detailed or summarized execution outputs with options to save results
- **Header Configuration:** Include custom headers in tool executions for enhanced testing scenarios
- **Debugging Support:** Enable detailed debug information to troubleshoot and optimize flows

## 📦 Installation

### Prerequisites

- **Python 3.7+**: Ensure you have Python installed. You can download it from [python.org](https://www.python.org/downloads/)
- `pip install -r requirements.txt`

## 🚀 Usage

### Basic Commands

```bash
# List all available tools
python main.py tools

# List all tools with a specific tag
python main.py tools --tag web

# List all available aliases
python main.py aliases

# Add a new tool
python main.py add toolname

# Get detailed information about a flow
python main.py flow info flowname

# List all available flows
python main.py flow list
```

### Running Flows

```bash
# Basic flow execution
python main.py flow run flowname

# Run with headers
python main.py flow run flowname --headers "User-Agent: Mozilla/5.0"

# Run with debug information
python main.py flow run flowname --debug

# Save output to file
python main.py flow run flowname --save-output
```

### Flow Execution Options

- `--print-step-output`: Print each step's output after execution
- `--strip-colors`: Strip ANSI color codes from output
- `--debug`: Show stderr output and additional debug information
- `--show-full-output`: Show full output of each step without truncation
- `--save-output`: Save output to results directory
- `--headers`: Include custom headers in "Key:Value" format

## 📁 Directory Structure

```
hacktopus-cli/
├── tools/                  
│   ├── toolname/
│   │   ├── config.yaml     # Tool configuration
│   │   └── aliases.yaml    # Tool aliases
├── flows/                  
│   └── flowname.yaml       # Flow configuration
└── results/                # Output directory
```

## 🔧 Tool Configuration

### config.yaml
```yaml
description: "Tool description"
tags:
  - tag1
  - tag2
run_command: "binary-name"
accepts_stdin: true
header_flag: "--header"
```

### aliases.yaml
```yaml
aliases:
  default:
    description: "Default tool usage"
    command: "-u {{url}}"
    variables:
      - name: url
        description: "Target URL"
```

## 🌊 Flow Configuration

Example flow structure:
```yaml
version: "1.0"
name: "Flow Name"
description: "Flow description"
tags:
  - tag1
  - tag2

variables:
  url: "{{url}}"

stages:
  stage_name:
    parallel: true
    description: "Stage description"
    combine_output: true
    tasks:
      - alias: "tool:alias"
        description: "Task description"
```