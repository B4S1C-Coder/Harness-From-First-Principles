from pathlib import Path
from ..sandboxes import VirtualFileSystemSandbox
from ..tools import ToolExecutor, ToolExecutionLimits
from ..builtin_tools.virtual_fs import (
    ListDirectoryTool,
    ReadFileTool,
    ReadLinesTool,
    EditFileTool,
    WriteFileTool,
)
from ..logger import ApplicationLogger

def virtual_fs_toolkit(
    root: Path,
    logger: ApplicationLogger,
    limits: ToolExecutionLimits | None = None,
) -> ToolExecutor:
    """ Constructs a preconfigured tool executor with virtual file system tools. """

    workspace = VirtualFileSystemSandbox(
        root=root,
        can_read=True,
        can_write=True,
        can_execute=False,
    )

    executor = ToolExecutor(
        tools=[
            ListDirectoryTool(workspace),
            ReadFileTool(workspace),
            ReadLinesTool(workspace),
            EditFileTool(workspace),
            WriteFileTool(workspace),
        ],
        limits=limits or ToolExecutionLimits(
            max_argument_bytes=64 * 1024,
            max_result_bytes=128 * 1024,
        ),
        logger=logger,
    )

    return executor

def virtual_readonly_fs_toolkit(
    root: Path,
    logger: ApplicationLogger,
    limits: ToolExecutionLimits | None = None,
) -> ToolExecutor:
    """ Constructs a preconfigured tool executor with read only virtual file system tools. """

    workspace = VirtualFileSystemSandbox(
        root=root,
        can_read=True,
        can_write=False,
        can_execute=False,
    )

    executor = ToolExecutor(
        tools=[
            ListDirectoryTool(workspace),
            ReadFileTool(workspace),
            ReadLinesTool(workspace),
        ],
        limits=limits or ToolExecutionLimits(
            max_argument_bytes=64 * 1024,
            max_result_bytes=128 * 1024,
        ),
        logger=logger,
    )
    
    return executor