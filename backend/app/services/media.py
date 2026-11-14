import http.client
import ipaddress
import socket
import ssl
from contextlib import contextmanager
from urllib.parse import urljoin, urlsplit


def validate_https_url(url: str) -> None:
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or any(character.isspace() for character in url)
        ):
            raise ValueError
        host = parsed.hostname
        _ = parsed.port
        if host.lower() == "localhost" or host.lower().endswith((".localhost", ".local")):
            raise ValueError
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return
        if not address.is_global:
            raise ValueError
    except ValueError as exc:
        raise ValueError("素材地址必须是公开可访问的 HTTPS URL") from exc


@contextmanager
def open_media(url: str, timeout: int):
    connection = None
    try:
        for _ in range(10):
            validate_https_url(url)
            parsed = urlsplit(url)
            host = parsed.hostname
            port = parsed.port or 443
            addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            if not addresses or any(
                not ipaddress.ip_address(item[4][0]).is_global for item in addresses
            ):
                raise ValueError("结果地址不能访问内网")
            connection = http.client.HTTPSConnection(host, port, timeout=timeout)
            # Pin the validated address while retaining hostname verification in TLS.
            raw_socket = socket.create_connection((addresses[0][4][0], port), timeout)
            try:
                connection.sock = ssl.create_default_context().wrap_socket(
                    raw_socket, server_hostname=host
                )
            except BaseException:
                raw_socket.close()
                raise
            connection.request(
                "GET",
                (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else ""),
                headers={"User-Agent": "NodePass/0.1", "Accept": "video/*"},
            )
            response = connection.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                location = response.getheader("Location")
                connection.close()
                if not location:
                    raise ValueError("结果跳转缺少地址")
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise OSError(f"视频下载返回 HTTP {response.status}")
            try:
                yield response
            finally:
                response.close()
            return
        raise ValueError("结果地址跳转过多")
    finally:
        if connection:
            connection.close()
