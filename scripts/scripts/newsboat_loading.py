"""Shared startup ship and refresh-toast renderer."""
import os
from pathlib import Path
import re
import subprocess


class GraphicsStream:
    """Keep terminal sequences, image transfers and synchronized frames atomic.

    Relays add their own graphics between returned blocks. A PTY read boundary
    can occur inside an escape, a UTF-8 character, or any Kitty base64 chunk;
    none of those boundaries is safe for inserting another drawing command.
    """
    def __init__(self, preserve_frames=False):
        self.pending = b''
        self.preserve_frames = preserve_frames

    def feed(self, data):
        data = self.pending + data
        self.pending = b''
        offset = 0
        transfer = frame = None

        def incomplete(start):
            boundary = min(n for n in (start, transfer, frame) if n is not None)
            self.pending = data[boundary:]
            return data[:boundary]

        while offset < len(data):
            start = offset
            byte = data[offset]
            if byte == 27:
                if offset + 1 == len(data):
                    return incomplete(start)
                kind = data[offset+1]
                if kind in (ord('_'), ord('P'), ord(']')):
                    end = data.find(b'\x1b\\', offset+2)
                    terminator = 2
                    if kind == ord(']'):
                        bell = data.find(b'\x07', offset+2)
                        if bell >= 0 and (end < 0 or bell < end):
                            end, terminator = bell, 1
                    if end < 0:
                        return incomplete(start)
                    if data.startswith(b'\x1b_G',start):
                        header = data[start+3:end].split(b';',1)[0].split(b',')
                        if b'm=1' in header and transfer is None:
                            transfer = start
                        elif b'm=0' in header:
                            transfer = None
                    offset = end + terminator
                elif kind == ord('['):
                    end = offset + 2
                    while end < len(data) and not 0x40 <= data[end] <= 0x7e:
                        end += 1
                    if end == len(data):
                        return incomplete(start)
                    sequence = data[start:end+1]
                    if self.preserve_frames and sequence == b'\x1b[?2026h' and frame is None:
                        frame = start
                    elif sequence == b'\x1b[?2026l':
                        frame = None
                    offset = end + 1
                else:
                    end = offset + 1
                    while end < len(data) and 0x20 <= data[end] <= 0x2f:
                        end += 1
                    if end == len(data):
                        return incomplete(start)
                    offset = end + 1
            elif 0xc2 <= byte <= 0xf4:
                length = 2 if byte < 0xe0 else 3 if byte < 0xf0 else 4
                if offset + length > len(data):
                    return incomplete(start)
                offset += length
            else:
                offset += 1
        if transfer is not None or frame is not None:
            return incomplete(len(data))
        return data


def ship_art(frame, inner):
    """Shared smoke, ship bobbing, and waves for refresh and thumbnail loading."""
    smoke = [list(' ' * 18) for _ in range(2)]
    for stack in (7, 11):
        for puff_offset in (0, 6):
            age = (frame // 2 + puff_offset + (2 if stack == 11 else 0)) % 12
            smoke[1-age//6][stack+age//4] = 'o' if 3 <= age < 9 else '.'
    art = [''.join(line) for line in smoke] + [
        '      |#| |#|     ',
        '   ___|[]_[]|___  ',
        '   \\_o_o_o_o__/   ',
    ]
    colors = [244,244,203,255,203]
    if 6 <= frame % 32 < 22:
        art = art[1:] + [' ' * 18]
        colors = colors[1:] + [244]
    wave = '~^~~-~~^~~-~~^~~-~~^~~-~~'
    shift = (frame//2) % 6
    art.append(wave[shift:shift+18])
    colors.append(38)
    art = [line.center(inner) for line in art[:-1]] + [(wave * 3)[shift:shift+inner]]
    return list(zip(colors, art))


class Renderer:
    def __init__(self):
        launcher = Path(__file__).with_name("newsboat-launch.sh")
        self.process = subprocess.Popen(
            ["bash", str(launcher), "--render"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        )

    def draw(self, frame, caption):
        cols, rows = os.get_terminal_size(1)
        # Small windows cannot fit the boat; keep the counter usable instead.
        if cols < 28 or rows < 20:
            return ("\x1b[?25l\x1b[H\x1b[2J" + caption[:cols - 1]).encode()
        self.process.stdin.write(f"{frame}\t{caption}\t{cols}\t{rows}\n".encode())
        self.process.stdin.flush()
        data = bytearray(b"\x1b[?25l")
        while True:
            char = self.process.stdout.read(1)
            if char == b"\0":
                return bytes(data).replace(b"\n", b"\r\n")
            if not char:
                raise RuntimeError("Boat renderer exited unexpectedly")
            data.extend(char)

    def close(self):
        self.process.stdin.close()
        self.process.wait(timeout=2)
        self.process.stdout.close()

    OVERLAY_ID = 0x3ffffffe

    @staticmethod
    def clear_overlay():
        return f'\x1b_Ga=d,d=I,i={Renderer.OVERLAY_ID},q=2\x1b\\'.encode()

    @staticmethod
    def overlay(frame, caption, cols, rows, height, offset=0):
        from newsboat_thumbnails import loading_png, transmit
        from PIL import Image
        import io
        width=max(1,min(34,cols-2));visible=max(0,width-offset)
        if not visible:return Renderer.clear_overlay()
        data=loading_png(frame % 96,caption=caption)
        if visible < width:
            with Image.open(io.BytesIO(data)) as source:
                clipped=source.crop((0,0,round(source.width*visible/width),source.height))
                output=io.BytesIO();clipped.save(output,format='PNG');data=output.getvalue()
        return (transmit(Renderer.OVERLAY_ID,data)+
                f'\x1b7\x1b[{min(2,rows)};{max(1,cols-width-1+offset)}H'
                f'\x1b_Ga=p,i={Renderer.OVERLAY_ID},p=1,c={visible},r={height},z=2,q=2\x1b\\\x1b8'.encode())

    @staticmethod
    def compact(frame, caption, cols, rows, height, offset=0):
        """Paint a small top-right toast, preserving Newsboat's cursor."""
        width = max(1, min(34, cols - 2))
        if height == 1:
            lines = ['🚢  ' + caption.splitlines()[-1][:max(0, width-4)]]
        else:
            inner = width - 2
            colors, art = zip(*ship_art(frame, inner))
            lines = [f'│\x1b[38;5;{color}m{line}\x1b[0m│' for color,line in zip(colors,art)]
            lines.extend('│' + line[:inner].center(inner) + '│' for line in caption.splitlines())
            lines = ['╭' + '─' * inner + '╮'] + lines + ['╰' + '─' * inner + '╯']
        visible = max(0, width-offset)
        if not visible:
            return b''
        output = bytearray(b'\x1b7')
        for index,line in enumerate(lines):
            # Clip the moving toast at the right margin without wrapping ANSI
            # colors or border characters onto the next terminal row.
            clipped = []
            remaining = visible
            for part in re.split(r'(\x1b\[[0-?]*[ -/]*[@-~])', line):
                if part.startswith('\x1b'):
                    clipped.append(part)
                elif remaining:
                    clipped.append(part[:remaining])
                    remaining -= len(part[:remaining])
            output.extend(f'\x1b[{min(2, rows)+index};{max(1, cols-width-1+offset)}H\x1b[0m\x1b[{visible}X'.encode())
            output.extend(''.join(clipped).encode())
        output.extend(b'\x1b[0m\x1b8')
        return bytes(output)


def nested_view_environment(directory):
    """Nested views share the wrapper's alternate screen instead of leaving it."""
    env = os.environ.copy()
    env.pop('NEWSBOAT_QUEUE_VIEW', None)
    term = env.get('TERM', 'xterm-256color')
    result = subprocess.run(['infocmp', '-1', term], capture_output=True, text=True, check=True)
    description = re.sub(r'^\s*(?:smcup|rmcup)=.*\n', '', result.stdout, flags=re.MULTILINE)
    terminfo = Path(directory)/'terminfo'
    terminfo.mkdir(exist_ok=True)
    source = Path(directory)/'nested.terminfo'
    source.write_text(description)
    subprocess.run(['tic', '-x', '-o', str(terminfo), str(source)], check=True, capture_output=True)
    env['TERMINFO'] = str(terminfo)
    return env
