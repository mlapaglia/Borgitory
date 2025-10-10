from typing import Dict, Literal, Optional, TypedDict, Union


class ProgressData(TypedDict, total=False):
    """Type definition for progress data from rclone operations"""

    type: str
    transferred: Optional[str]
    total: Optional[str]
    percentage: Optional[float]
    speed: Optional[str]
    eta: Optional[str]
    command: Optional[str]
    pid: Optional[int]
    return_code: Optional[int]
    status: Optional[str]
    message: Optional[str]
    stream: Optional[str]


class ConnectionTestResult(TypedDict, total=False):
    """Type definition for connection test results"""

    status: Literal["success", "failed", "warning", "error"]
    message: str
    output: Optional[str]
    details: Optional[Dict[str, Union[str, int, bool, None]]]
    can_write: Optional[bool]
