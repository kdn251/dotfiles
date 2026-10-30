#!/usr/bin/env python3
"""Reuse only our managed Twitch player, preserving its window and renderer."""
import json
import os
from pathlib import Path
import select
import socket
import struct
import sys

SOCKET='/tmp/mpv-twitch-ipc'


def connect():
    client=socket.socket(socket.AF_UNIX)
    client.settimeout(1)
    client.connect(SOCKET)
    pid,uid,_=struct.unpack('3i',client.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
    if uid!=os.getuid():
        client.close()
        raise ValueError('Not our player')
    return client,pid


def command(stream, *args):
    stream.write((json.dumps({'command':args,'request_id':1})+'\n').encode())
    while True:
        line=stream.readline()
        if not line:raise ValueError('Player closed')
        reply=json.loads(line)
        if reply.get('request_id')==1:
            if reply.get('error')!='success':raise ValueError('Player rejected command')
            return reply.get('data')


def channel(expected_pid):
    client,pid=connect()
    with client,client.makefile('rwb',buffering=0) as stream:
        if pid!=expected_pid:return None
        return command(stream,'get_property','user-data/twitch-channel')


def reuse(name,title,url,marker,fallback="",service="Twitch"):
    client,pid=connect()
    with client,client.makefile('rwb',buffering=0) as stream:
        if command(stream,'get_property','user-data/twitch-managed')!=2:
            raise ValueError('Player does not support stream switching')
        command(stream,'script-message','twitch-load',name,title,url,marker,fallback,service)
    return pid


if __name__=='__main__':
    try:
        if sys.argv[1]=='wait':
            # pidfd watches the process without polling or PID-reuse races.
            fd=os.pidfd_open(int(sys.argv[2]))
            try:
                while True:
                    if len(sys.argv)>3:
                        try:current=Path('/tmp/twitch-session.id').read_text().strip()
                        except OSError:current=''
                        if current!=sys.argv[3]:break
                    if select.select([fd],[],[],.5 if len(sys.argv)>3 else None)[0]:break
            finally:os.close(fd)
        else:print(reuse(*sys.argv[1:]))
    except (OSError,ValueError,KeyError):
        raise SystemExit(1)
