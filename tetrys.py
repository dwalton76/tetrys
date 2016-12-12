#!/usr/bin/env python
# vim: fileencoding=utf-8

# Copyright 2013 Antony Lee. All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   1. Redistributions of source code must retain the above copyright notice,
#      this list of conditions and the following disclaimer.
#
#   2. Redistributions in binary form must reproduce the above copyright
#      notice, this list of conditions and the following disclaimer in the
#      documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY ANTONY LEE ``AS IS'' AND ANY EXPRESS OR IMPLIED
# WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO
# EVENT SHALL ANTONY LEE OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT
# NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY
# OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE,
# EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""A curses-based Tetris implementation.  Use arrows to play, q to quit.

Music is based on X11 handling of BEL.
"""

from __future__ import division, print_function, unicode_literals

import atexit
import curses
from itertools import cycle, product
import os
import random
import sys
import threading
import time


Pieces = [
    [[1, 1, 1, 1]],
    [[2, 2], [2, 2]],
    [[3, 3, 3], [0, 3, 0]],
    [[4, 4, 0], [0, 4, 4]],
    [[0, 5, 5], [5, 5, 0]],
    [[6, 6, 6], [6, 0, 0]],
    [[7, 7, 7], [0, 0, 7]],
]


def p_hw(piece):
    return len(piece), len(piece[0])


def p_rotate(piece):
    return list(zip(*reversed(piece)))


def gen_p():
    while True:
        random.shuffle(Pieces)
        for piece in Pieces:
            yield piece
gen_p = gen_p()


FPS = 60
Speeds = [
    48, 45, 42, 39, 36, 33, 30, 27, 24, 21, 18, 15, 12, 10, 8, 6, 5, 4, 3, 2]


class Tetris:

    def __init__(self, height, width):
        self.height, self.width = height, width
        self.field = [[0 for _ in range(width)] for _ in range(height)]
        self.lines = 0
        self.level = 0
        self.score = 0
        self.current = None
        self.hoff = self.woff = 0
        self.drop_bonus = 0
        self.lock = threading.RLock()
        self.continues = True

    def curses_str(self):
        if sys.version_info >= (3,):
            edge = corner = bottom = "░"
        else:
            edge, corner, bottom = "|", "+", "-"
        return ("\n".join(
            edge + "".join(map(str, line)) + edge
            for line in reversed(self.field)) +
            "\n" + corner + bottom * self.width + corner)

    def new_p(self):
        cleared = 0
        redo = True
        while redo:
            redo = False
            for i in range(self.height):
                if all(self.field[i]):
                    cleared += 1
                    for j in range(i, self.height - 1):
                        self.field[j] = self.field[j + 1]
                    self.field[self.height - 1] = [0 for _ in range(self.width)]
                    redo = True
        if (self.lines + cleared) // 10 > self.lines:
            self.level = min(self.level + 1, len(Speeds) - 1)
        self.lines += cleared
        self.score += ([0, 40, 100, 300, 1200][cleared] * (self.level + 1) +
                       self.drop_bonus)
        self.drop_bonus = 0
        self.hoff = self.woff = 0
        piece = next(gen_p)
        ph, pw = p_hw(piece)
        i, j = self.height - ph, (self.width - pw) // 2
        if not self.add_p(piece, i, j):
            self.continues = False

    def remove_p(self, piece, i, j):
        ph, pw = p_hw(piece)
        for _i, _j in product(range(ph), range(pw)):
            self.field[_i + i][_j + j] &= ~piece[_i][_j]

    def add_p(self, piece, i, j):
        ph, pw = p_hw(piece)
        if j < 0 or j + pw > self.width:
            return False
        for _i, _j in product(range(ph), range(pw)):
            try:
                if piece[_i][_j] and self.field[_i + i][_j + j]:
                    return False
            except IndexError:
                return False
        for _i, _j in product(range(ph), range(pw)):
            self.field[_i + i][_j + j] |= piece[_i][_j]
        self.current = piece, i, j
        return True

    def tick(self):
        with self.lock:
            piece, i, j = self.current
            if i > 0:
                self.remove_p(piece, i, j)
                if self.add_p(piece, i - 1, j):
                    return
                else:
                    self.add_p(piece, i, j)
            self.new_p()
            return True

    def left(self):
        with self.lock:
            piece, i, j = self.current
            self.remove_p(piece, i, j)
            if not self.add_p(piece, i, j - 1):
                self.add_p(piece, i, j)

    def right(self):
        with self.lock:
            piece, i, j = self.current
            self.remove_p(piece, i, j)
            if not self.add_p(piece, i, j + 1):
                self.add_p(piece, i, j)

    def rotate(self):
        with self.lock:
            piece, i, j = self.current
            self.remove_p(piece, i, j)
            oh, ow = p_hw(piece)
            rotated = p_rotate(piece)
            nh, nw = p_hw(rotated)
            if not self.add_p(rotated,
                              i + (oh - nh + self.hoff % 2) // 2,
                              j + (ow - nw + self.woff % 2) // 2):
                self.add_p(piece, i, j)
            else:
                ph, pw = p_hw(rotated)
                self.hoff += ph % 2
                self.woff += pw % 2

    def down(self):
        with self.lock:
            self.drop_bonus += 1
            self.tick()

    def start(self):
        self.new_p()

        def target():
            while self.continues:
                time.sleep(FPS / Speeds[self.level])
                self.tick()
        threading.Thread(target=target).start()


def main(stdscr):
    curses.start_color()
    curses.init_color(7, 1000, 627, 0)
    curses.init_color(8, 1000, 1000, 1000)
    for i, j in enumerate([6, 3, 5, 2, 1, 4, 7, 8], 1):
        curses.init_pair(i, j, curses.COLOR_BLACK)
    curses.curs_set(0)
    curses.noecho()
    stdscr.nodelay(1)
    game = Tetris(20, 10)
    game.start()
    stdscr.clear()
    while game.continues:
        c = stdscr.getch()
        if c == ord("q"):
            game.continues = False
        elif c == curses.KEY_LEFT:
            game.left()
        elif c == curses.KEY_RIGHT:
            game.right()
        elif c == curses.KEY_UP:
            game.rotate()
        elif c == curses.KEY_DOWN:
            game.down()
        for i, line in enumerate(game.curses_str().splitlines()):
            for j, c in enumerate(line):
                if c == "0":
                    stdscr.addstr(i, j, " ")
                elif c.isdigit():
                    stdscr.addstr(i, j, "█" if sys.version_info >= (3,) else "X",
                                  curses.color_pair(int(c)))
                else:
                    stdscr.addstr(i, j, c, curses.color_pair(8))
        stdscr.addstr(22, 0, "Lines: {}".format(game.lines), curses.color_pair(8))
        stdscr.addstr(23, 0, "Level: {}".format(game.level), curses.color_pair(8))
        stdscr.addstr(24, 0, "Score: {}".format(game.score), curses.color_pair(8))
        stdscr.refresh()
    return game


def music():
    pct, fq, duration = [
        int(s) for s in os.popen("xset q | grep bell").read().split()
        if s.isdigit()]

    @atexit.register
    def register():
        os.popen("xset b {} {} {}".format(pct, fq, duration))
    pct = 50
    fqs = {"A": 220, "B": 246, "C": 262, "D": 294, "E": 330, "F": 349, "G": 392}
    korobeiniki = """EE B C DD C B AA A C EE D C BBB C DD EE CC AA AAAA
                     _ DD F ^AA G F EEE C EE D C BB B C DD EE CC AA AAAA
                     EEEE CCCC DDDD BBBB CCCC AAAA BBBB ____
                     EEEE CCCC DDDD BBBB CC EE ^AA ^AA GGGGs ____
                     EE B C DD C B AA A C EE D C BBB C DD EE CC AA AAAA
                     _ DD F ^AA G F EEE C EE D C BB B C DD EE CC ^AA ^AAAA"""
    katyusha = """AAA B CCC A C C B A BB vEE BBB C DDD B D D C B AAAA
                  EE ^AA GG ^A G F F E D EE AA _ FF D EEE C B vE C B AAAA
                  EE ^AA GG ^A G F F E D EE AA _ FF D EEE C B vE C B AAAA
                  4v AAA B CCC A C C B A BB vEE BBB C DDD B D D C B AAAA
                  EE ^AA GG ^A G F F E D EE AA _ FF D EEE C B vE C B AAAA
                  EE ^AA GG ^A G F F E D EE AA _ FF D EEE C B vE C B AAAA
                  3m^ AAA B CCC A C C B A BB vEE BBB C DDD B D D C B AAAA
                  EE ^AA GG ^A G F F E D EE AA _ FF D EEE C B vE C B AAAA
                  EE ^AA GG ^A G F F E D EE AA _ FF D EEE C B vE C B AAAA
                  4v AAA B CCC A C C B A BB vEE BBB C DDD B D D C B AAAA
                  EE ^AA GG ^A G F F E D EE AA _ FF D EEE C B vE C B AAAA
                  EE ^AA GG ^A G F F E D EE AA _ FF D EEE C B vE C B AAAA
                  5^"""
    kalinka = "DD B C DD B C DD C B AA E e e ddd c B C DD B C DD C B AA"
    pieces = [korobeiniki, katyusha, kalinka]
    previous = None

    while True:
        while True:
            piece = random.choice(pieces)
            if piece != previous:
                break
        transpose = 1
        for note in piece.split():
            t = time.time()
            duration = 0
            if note[0].isdigit():
                transpose *= {"3m^": 6 / 5, "4v": 3 / 4, "5^": 3 / 2}[note]
            elif note.startswith("_"):
                os.popen("xset b 0").read()
                duration = 200 * len(note)
            else:
                mul = transpose
                if note[0] == "^":
                    note = note[1:]
                    mul *= 2
                elif note[0] == "v":
                    note = note[1:]
                    mul /= 2
                if note[-1] == "s":
                    note = note[:-1]
                    mul *= 1.0595
                fq = int(fqs[note[0].upper()] * mul)
                duration = 200 * len(note) // (2 if note[0].islower() else 1)
                os.popen("xset b {} {} {}".format(pct, fq, duration)).read()
                print("\a")
                sys.stdout.softspace = 0
            time.sleep(max(t + duration / 1000 - time.time(), 0))


if __name__ == "__main__":
    thread = threading.Thread(target=music)
    thread.daemon = True
    thread.start()
    game = curses.wrapper(main)
    print("Game over!")
    print("Lines: {}, Level: {}, Score: {}".format(game.lines, game.level, game.score))
