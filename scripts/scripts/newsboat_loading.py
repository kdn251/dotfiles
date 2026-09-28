"""Shared startup ship and refresh-toast renderer."""
import os
from pathlib import Path
import re
import subprocess


class GraphicsStream:
    """Keep Kitty APC packets intact when a PTY splits them across reads."""
    def __init__(self):
        self.pending = b''

    def feed(self, data):
        data = self.pending + data
        self.pending = b''
        offset = 0
        while True:
            positions = [pos for prefix in (b'\x1b_G',b'\x1bP') if (pos := data.find(prefix,offset)) >= 0]
            start = min(positions) if positions else -1
            if start < 0:
                keep = 2 if data.endswith(b'\x1b_') else int(data.endswith(b'\x1b'))
                if keep:
                    self.pending = data[-keep:]
                    return data[:-keep]
                return data
            end = data.find(b'\x1b\\', start+3)
            if end < 0:
                self.pending = data[start:]
                return data[:start]
            offset = end+2


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

    @staticmethod
    def compact(frame, caption, cols, rows, height, offset=0):
        """Paint a small top-right toast, preserving Newsboat's cursor."""
        width = max(1, min(34, cols - 2))
        if height == 1:
            lines = ['🚢  ' + caption.splitlines()[-1][:max(0, width-4)]]
        else:
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
            inner = width - 2
            art = [line.center(inner) for line in art[:-1]] + [(wave * 3)[shift:shift+inner]]
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
