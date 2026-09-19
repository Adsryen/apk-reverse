#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""向 app 的 DataStore(video_preferences) 注入 ad_free_expires_at 大值，验证它能否抑制广告 UI。

Preferences 的 protobuf 结构：
  PreferenceMap { map<string, Value> preferences = 1; }
  entry: 0x0A <len(key)> <key>  0x12 <len(value)> <value>
  Value : boolean=1(float wire), float=2, integer=3(varint), long=4(varint), string=5, ...

所以要写一个 longKey："ad_free_expires_at" -> Value{ long = 大值 }
  Value 载荷 = 0x20 <varint(long)>   (field 4, wire type 0 -> tag 0x20)
"""
import struct
import sys


def varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def map_entry(key, value_payload):
    """编码 PreferenceMap 里的一个 map entry。

    ★关键（踩过坑）：map<string,Value> preferences = 1 是一个 map 字段，
    编码时必须**两层** 0x0A：
        外层: 0x0A <len(entry)>          <- 字段1的 tag + 长度
        内层: 0x0A <len(key)> <key>  0x12 <len(value)> <value>
    只写内层（丢掉外层 tag+长度）会让 DataStore 反序列化失败，
    app 直接 uncaughtException 崩溃，而且没有堆栈（被 UCrash 吞掉），极难定位。
    """
    kb = key.encode('utf-8')
    inner = (b'\x0a' + varint(len(kb)) + kb
             + b'\x12' + varint(len(value_payload)) + value_payload)
    return b'\x0a' + varint(len(inner)) + inner


def entry(key, value_payload):
    """兼容旧调用：返回 map_entry。"""
    return map_entry(key, value_payload)


def main():
    # 保留已有键：player_page_open_count = 1  (int32, field 3 -> tag 0x18)
    existing = entry('player_page_open_count', b'\x18\x01')
    # 注入一个远超任何现实时间的时间戳（毫秒/秒都覆盖）
    BIG = 9999999999999
    injected = entry('ad_free_expires_at', b'\x20' + varint(BIG))
    data = existing + injected
    out = sys.argv[1] if len(sys.argv) > 1 else 'video_preferences.preferences_pb'
    with open(out, 'wb') as f:
        f.write(data)
    print('[ok] wrote %s (%d bytes)' % (out, len(data)))
    print('[hex] %s' % data.hex(' '))
    print('[note] ad_free_expires_at = %d, varint=%s' % (BIG, varint(BIG).hex(' ')))


if __name__ == '__main__':
    main()
