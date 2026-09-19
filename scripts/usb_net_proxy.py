#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用于给「无网络」Android 设备供网的极简 HTTP/HTTPS 代理。

场景：手机 WiFi DHCP 失败 -> 无默认网络 -> app 所有请求失败。
解法：手机没有可用网络接口也没关系 —— adb reverse 会在**设备本机的 loopback**
上开监听，不需要任何网络接口。于是：
    1) 电脑跑本代理 (0.0.0.0:8080)
    2) adb -s <serial> reverse tcp:8080 tcp:8080
    3) 设备端 su -c "settings put global http_proxy 127.0.0.1:8080"
    4) app 的 HTTP/HTTPS 流量经 USB 到电脑，由电脑代发

支持：
  - CONNECT 隧道（HTTPS 主用）
  - 明文 HTTP 绝对 URI 转发
仅做转发，不做 MITM（不解密 TLS，也不改流量），因此不干扰证书校验。

用法：python usb_net_proxy.py [listen_port] [logfile]
"""
import socket
import sys
import threading
import time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
LOGF = sys.argv[2] if len(sys.argv) > 2 else None
_lock = threading.Lock()
_logf = open(LOGF, 'a', encoding='utf-8') if LOGF else None


def log(msg):
    line = '[%s] %s' % (time.strftime('%H:%M:%S'), msg)
    print(line, flush=True)
    if _logf:
        with _lock:
            _logf.write(line + '\n')
            _logf.flush()


def pump(a, b):
    """a -> b 单向搬运，直到任一端关闭。"""
    try:
        while True:
            r, _, _ = select_select([a], [], [], 30)
            if not r:
                break
            data = a.recv(65536)
            if not data:
                break
            b.sendall(data)
    except Exception:
        pass
    finally:
        for s in (a, b):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                s.close()
            except Exception:
                pass


def select_select(rlist, wlist, xlist, timeout):
    import select
    return select.select(rlist, wlist, xlist, timeout)


def read_head(sock, limit=65536):
    data = b''
    while b'\r\n\r\n' not in data and len(data) < limit:
        chunk = sock.recv(4096)
        if not chunk:
            return data
        data += chunk
    return data


def handle(client, addr):
    client.settimeout(30)
    try:
        head = read_head(client)
        if not head:
            client.close()
            return
        first = head.split(b'\r\n', 1)[0].decode('latin-1')
        parts = first.split(' ')
        if len(parts) < 3:
            client.close()
            return
        method, target = parts[0].upper(), parts[1]
        rest = head.split(b'\r\n\r\n', 1)[1] if b'\r\n\r\n' in head else b''

        if method == 'CONNECT':
            host, _, port = target.rpartition(':')
            port = int(port or 443)
            log('CONNECT %s:%d' % (host, port))
            remote = socket.create_connection((host, port), timeout=20)
            client.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
            client.settimeout(None)
            remote.settimeout(None)
            t = threading.Thread(target=pump, args=(client, remote), daemon=True)
            t.start()
            pump(remote, client)
        else:
            # 明文 HTTP：target 一般是绝对 URI
            if target.startswith('http://'):
                without = target[len('http://'):]
                hostport = without.split('/', 1)[0]
                path = '/' + without.split('/', 1)[1] if '/' in without else '/'
            else:
                hostport = None
                for ln in head.split(b'\r\n'):
                    if ln.lower().startswith(b'host:'):
                        hostport = ln.split(b':', 1)[1].strip().decode()
                path = target
            if not hostport:
                client.close()
                return
            host, _, port = hostport.rpartition(':')
            port = int(port or 80)
            log('HTTP %s%s' % (hostport, path))
            remote = socket.create_connection((host, port), timeout=20)
            req = ('%s %s HTTP/1.1\r\n' % (method, path)).encode()
            hdrs = head.split(b'\r\n')[1:]
            for h in hdrs:
                if h.lower().startswith(b'proxy-connection'):
                    continue
                req += h + b'\r\n'
            req += b'\r\n' + rest
            remote.sendall(req)
            client.settimeout(None)
            remote.settimeout(None)
            t = threading.Thread(target=pump, args=(client, remote), daemon=True)
            t.start()
            pump(remote, client)
    except Exception as e:
        log('ERR %s %s' % (addr, e))
        try:
            client.close()
        except Exception:
            pass


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('0.0.0.0', PORT))
    srv.listen(128)
    log('proxy listening on 0.0.0.0:%d' % PORT)
    while True:
        c, a = srv.accept()
        threading.Thread(target=handle, args=(c, a), daemon=True).start()


if __name__ == '__main__':
    main()
