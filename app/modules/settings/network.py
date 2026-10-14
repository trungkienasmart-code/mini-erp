# app/modules/settings/network.py
import socket
import subprocess
import platform
import uuid
from typing import Optional, List, Tuple


def get_local_ip() -> str:
    """
    Lấy IP LAN của máy (không phải 127.0.0.1).
    Dùng trick: kết nối đến 8.8.8.8 (không thực sự gửi gói tin).
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_all_local_ips() -> List[str]:
    """Lấy tất cả IP của các card mạng (bỏ 127.0.0.1)."""
    ips = []
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if not ip.startswith("127."):
                ips.append(ip)
    except Exception:
        pass

    # Fallback
    main_ip = get_local_ip()
    if main_ip not in ips and main_ip != "127.0.0.1":
        ips.insert(0, main_ip)

    return ips or ["127.0.0.1"]


def get_machine_id() -> str:
    """
    Lấy mã định danh máy (dùng cho license).
    - Windows: dùng uuid.getnode() (MAC address hash).
    """
    try:
        mac = uuid.getnode()
        return f"{mac:012x}".upper()
    except Exception:
        return "UNKNOWN"


def check_port_open(port: int = 8000) -> bool:
    """
    Kiểm tra port đang LISTEN không (chỉ chạy trên Windows).
    """
    if platform.system() != "Windows":
        return True
    try:
        result = subprocess.run(
            ["netstat", "-an"],
            capture_output=True, text=True, timeout=5,
        )
        return f":{port}" in result.stdout and "LISTENING" in result.stdout
    except Exception:
        return False


def firewall_rule_exists(rule_name: str = "Mini ERP 8000") -> bool:
    """Kiểm tra rule firewall đã tồn tại chưa."""
    if platform.system() != "Windows":
        return True
    try:
        result = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule",
             f"name={rule_name}"],
            capture_output=True, text=True, timeout=5,
        )
        return "No rules match" not in result.stdout
    except Exception:
        return False


def open_firewall_port(port: int = 8000, rule_name: str = None) -> Tuple[bool, str]:
    """
    Mở port trên Windows Firewall (cần quyền admin).
    Trả về (success, message).
    """
    if platform.system() != "Windows":
        return False, "Chỉ hỗ trợ Windows"

    if rule_name is None:
        rule_name = f"Mini ERP {port}"

    if firewall_rule_exists(rule_name):
        return True, f"Port {port} đã được mở trước đó"

    try:
        cmd = [
            "powershell", "-Command",
            f"Start-Process powershell -Verb RunAs -Wait -ArgumentList "
            f"'-Command New-NetFirewallRule -DisplayName \"{rule_name}\" "
            f"-Direction Inbound -Protocol TCP -LocalPort {port} -Action Allow'"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            return True, f"Đã mở port {port} thành công"
        else:
            return False, f"Lỗi mở port: {result.stderr[:200]}"
    except subprocess.TimeoutExpired:
        return False, "Timeout — có thể user chưa bấm UAC"
    except Exception as e:
        return False, f"Lỗi: {e}"


def get_network_info(port: int = 8000) -> dict:
    """
    Tổng hợp thông tin mạng để hiển thị.
    """
    main_ip = get_local_ip()
    all_ips = get_all_local_ips()

    return {
        "host_ip": main_ip,
        "all_ips": all_ips,
        "port": port,
        "url": f"http://{main_ip}:{port}",
        "machine_id": get_machine_id(),
        "port_open": check_port_open(port),
        "firewall_open": firewall_rule_exists(f"Mini ERP {port}"),
        "os": platform.system(),
        "hostname": socket.gethostname(),
    }