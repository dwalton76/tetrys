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
from pprint import pformat
import argparse
import atexit
import copy
import logging
import curses
from itertools import cycle, product
import os
import random
import signal
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

max_moves = {
    (1, 0) : (3, 3),
    (1, 1) : (4, 5),
    (2, 0) : (4, 4),
    (3, 0) : (3, 4),
    (3, 1) : (3, 5),
    (3, 2) : (3, 4),
    (3, 3) : (3, 5),
    (4, 0) : (3, 4),
    (4, 1) : (3, 5),
    (5, 0) : (3, 4),
    (5, 1) : (3, 5),
    (6, 0) : (3, 4),
    (6, 1) : (3, 5),
    (6, 2) : (2, 5),
    (6, 3) : (3, 5),
    (7, 0) : (3, 4),
    (7, 1) : (3, 5),
    (7, 2) : (2, 5),
    (7, 3) : (3, 5),
}


def moves_to_string(moves):
    result = []

    for x in moves:
        if x == curses.KEY_UP:
            result.append('KEY_UP')
        elif x == curses.KEY_DOWN:
            result.append('KEY_DOWN')
        elif x == curses.KEY_LEFT:
            result.append('KEY_LEFT')
        elif x == curses.KEY_RIGHT:
            result.append('KEY_RIGHT')

    return ', '.join(result)


def get_piece_height_width(piece):
    return len(piece), len(piece[0])


def get_max_rotations(piece):
    piece_type = piece[0][1]

    # No need to rotate the square
    if piece_type == 2:
        return 0

    # Only rotate the vertical line and S blocks one time
    if piece_type in (1, 4, 5):
        return 1

    # The L and T pieces can be rotated three times
    if piece_type in (3, 6, 7):
        return 3

    raise Exception("Unknown piece type %s for piece %s" % (piece_type, pformat(piece)))


def get_max_moves(piece, rotation_count):
    piece_type = piece[0][1]
    return max_moves[(piece_type, rotation_count)]


def piece_rotate(piece):
    return list(zip(*reversed(piece)))

def gen_p():
    while True:
        random.shuffle(Pieces)
        for piece in Pieces:
            yield piece
gen_p = gen_p()

FPS = 60
PIECE_COUNT = len(Pieces)
Speeds = [48, 45, 42, 39, 36, 33, 30, 27, 24, 21, 18, 15, 12, 10, 8, 6, 5, 4, 3, 2]


class Tetris:

    def __init__(self, height, width):
        self.height, self.width = height, width
        self.field = [[0 for _ in range(width)] for _ in range(height)]
        self.lines = 0
        self.level = 0
        self.score = 0
        self.pieces_placed = 0
        self.current_piece = None
        self.next_piece = None
        self.piece_index = 0
        self.hoff = 0
        self.woff = 0
        self.cleared = 0
        self.landing_height = 0
        self.drop_bonus = 0
        self.lock = threading.RLock()
        self.continues = True
        self.shutdown = False
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def signal_handler(self, signal, frame):
        log.info("RXed SIGINT or SIGTERM")
        self.shutdown = True

    def save_state(self):
        self.save_field = [copy.copy(i) for i in self.field]
        self.save_lines = copy.copy(self.lines)
        self.save_level = copy.copy(self.level)
        self.save_score = copy.copy(self.score)
        self.save_current_piece = copy.copy(self.current_piece)
        self.save_next_piece = copy.copy(self.next_piece)
        self.save_piece_index = copy.copy(self.piece_index)
        self.save_pieces_placed = copy.copy(self.pieces_placed)
        self.save_hoff = copy.copy(self.hoff)
        self.save_woff = copy.copy(self.woff)
        self.save_cleared = copy.copy(self.cleared)
        self.save_landing_height = copy.copy(self.landing_height)
        self.save_drop_bonus = copy.copy(self.drop_bonus)
        self.save_continues = copy.copy(self.continues)

    def load_state(self):
        self.field = [copy.copy(i) for i in self.save_field]
        self.lines = copy.copy(self.save_lines)
        self.level = copy.copy(self.save_level)
        self.score = copy.copy(self.save_score)
        self.current_piece = copy.copy(self.save_current_piece)
        self.next_piece = copy.copy(self.save_next_piece)
        self.piece_index = copy.copy(self.save_piece_index)
        self.pieces_placed = copy.copy(self.save_pieces_placed)
        self.hoff = copy.copy(self.save_hoff)
        self.woff = copy.copy(self.save_woff)
        self.cleared = copy.copy(self.save_cleared)
        self.landing_height = copy.copy(self.save_landing_height)
        self.drop_bonus = copy.copy(self.save_drop_bonus)
        self.continues = copy.copy(self.save_continues)

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
        log.debug("Adding new piece")
        self.cleared = 0
        redo = True

        # Look to see if any rows should be cleared
        while redo:
            redo = False

            for i in range(self.height):
                if all(self.field[i]):
                    self.cleared += 1

                    for j in range(i, self.height - 1):
                        self.field[j] = self.field[j + 1]

                    self.field[self.height - 1] = [0 for _ in range(self.width)]
                    redo = True

        if ((self.lines + self.cleared) // 10) > (self.lines // 10):
            self.level = min(self.level + 1, len(Speeds) - 1)

        self.lines += self.cleared
        self.score += ([0, 40, 100, 300, 1200][self.cleared] * (self.level + 1) +
                       self.drop_bonus)
        self.drop_bonus = 0
        self.hoff = self.woff = 0

        # Add a new piece at the very top of the board
        piece = self.next_piece
        self.next_piece = next(gen_p)
        ph, pw = get_piece_height_width(piece)
        i, j = self.height - ph, (self.width - pw) // 2

        if not self.add_p(piece, i, j):
            self.continues = False
            log.info("cannot add a new piece - GAME OVER")

    def remove_p(self, piece, i, j):
        ph, pw = get_piece_height_width(piece)

        for _i, _j in product(range(ph), range(pw)):
            self.field[_i + i][_j + j] &= ~piece[_i][_j]

    def record_landing_height(self):
        (piece, i, j) = self.current_piece
        ph, pw = get_piece_height_width(piece)
        self.landing_height = i + (ph / 2.0)
        # log.info("set landing_height piece %s: i %d, lh %s" % (pformat(piece), i, self.landing_height))

    def add_p(self, piece, i, j):
        """
        Return True if we were able to add the piece
        """
        ph, pw = get_piece_height_width(piece)

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

        self.current_piece = piece, i, j
        return True

    def tick(self, add_next_piece):
        """
        Returns True if the piece hit the bottom
        """
        with self.lock:
            piece, i, j = self.current_piece

            if i > 0:
                self.remove_p(piece, i, j)

                if self.add_p(piece, i - 1, j):
                    self.record_landing_height()
                    return False
                else:
                    self.add_p(piece, i, j)
                    self.record_landing_height()

            if add_next_piece:
                self.new_p()

            return True

    def left(self):
        """
        Return True if we could move left
        """
        with self.lock:
            piece, i, j = self.current_piece
            self.remove_p(piece, i, j)

            if not self.add_p(piece, i, j - 1):
                self.add_p(piece, i, j)
                return False

            return True

    def right(self):
        """
        Return True if we could move right
        """
        with self.lock:
            piece, i, j = self.current_piece
            self.remove_p(piece, i, j)

            if not self.add_p(piece, i, j + 1):
                self.add_p(piece, i, j)
                return False

            return True

    def rotate(self):
        """
        Return True if we could rotate
        """
        with self.lock:
            piece, i, j = self.current_piece
            self.remove_p(piece, i, j)
            oh, ow = get_piece_height_width(piece)
            rotated = piece_rotate(piece)
            nh, nw = get_piece_height_width(rotated)

            if not self.add_p(rotated,
                              i + (oh - nh + self.hoff % 2) // 2,
                              j + (ow - nw + self.woff % 2) // 2):
                self.add_p(piece, i, j)
                return False
            else:
                ph, pw = get_piece_height_width(rotated)
                self.hoff += ph % 2
                self.woff += pw % 2
                return True

    def down(self, add_next_piece):
        with self.lock:
            self.drop_bonus += 1
            return self.tick(add_next_piece)

    def start(self, use_ai):
        self.next_piece = next(gen_p)
        self.new_p()

        def target():
            while self.continues:
                time.sleep(FPS / Speeds[self.level])
                self.tick(True)

        # No need to FPS drop if we are using AI...it is fast as hell
        if not use_ai:
            threading.Thread(target=target).start()

    def get_field_by_column(self):
        tmp = {}
        for (line_number, line) in enumerate(reversed(self.field)):
            for (column_index, block) in enumerate(line):
                if column_index not in tmp:
                    tmp[column_index] = []
                tmp[column_index].append(block)

        result = []
        for (column_index, column) in tmp.iteritems():
            result.append(column)
        return result

    def get_holes(self, data):
        count = 0

        for column in data:
            found_first_block = False

            for block in column:
                if block:
                    found_first_block = True
                else:
                    if found_first_block:
                        count += 1

        # log.info("get_holes()           %d" % count)
        return count

    def get_landing_height(self):
        # log.info("get_landing_height()  %s" % self.landing_height)
        return self.landing_height

    def get_row_transitions(self):
        count = 0
        prev_block = True

        for row in reversed(self.field):
            for block in row:
                if block and not prev_block:
                    count += 1
                elif not block and prev_block:
                    count += 1
                prev_block = True if block else False

            if not block:
                count += 1
            prev_block = True

        # log.info("get_row_transitions() %d" % count)
        return count

    def get_col_transitions(self, data):
        count = 0
        prev_block = True

        for column in data:
            for block in column:
                if block and not prev_block:
                    count += 1
                elif not block and prev_block:
                    count += 1

                prev_block = True if block else False
            prev_block = True

        # log.info("get_col_transitions() %d" % count)
        return count

    def get_well_sums(self, data):
        count = 0

        for (column_index, column) in enumerate(data):
            found_first_block = False
            well_count = 0

            for (row_index, block) in enumerate(column):
                if block or (found_first_block is False and row_index == self.height - 1):
                    if block:
                        found_first_block = True

                    # first column
                    if column_index == 0:
                        next_column = data[column_index + 1]
                        for (next_column_row_index, next_column_block) in enumerate(next_column):
                            if next_column_row_index < row_index:
                                if next_column_block:
                                    well_count += 1
                            elif next_column_row_index == row_index:
                                break

                    # last column
                    elif column_index == self.width - 1:
                        prev_column = data[column_index - 1]

                        for (prev_column_row_index, prev_column_block) in enumerate(prev_column):
                            if prev_column_row_index < row_index:
                                if prev_column_block:
                                    well_count += 1
                            elif prev_column_row_index == row_index:
                                break

                    # middle column
                    else:
                        next_column = data[column_index + 1]
                        prev_column = data[column_index - 1]
                        prev_column_row_index = 0

                        for (prev_column_block, next_column_block) in zip(prev_column, next_column):
                            if prev_column_row_index < row_index:
                                if prev_column_block and next_column_block:
                                    well_count += 1
                            elif prev_column_row_index == row_index:
                                break
                            prev_column_row_index += 1

                    break

            # For a well of length n, we define the well sums as 1 + 2 + 3 + ... + n.
            # This gives more significance to deeper holes
            if well_count:
                # https://www.programiz.com/python-programming/examples/sum-natural-number
                count += (well_count * (well_count+1)) / 2.0

        # log.info("get_well_sums()       %d" % count)
        return count

    def get_ai_score(self):
        data = self.get_field_by_column()

        score = ((self.get_landing_height()      * -4.500158825082766)  +
                 (self.cleared                   *  3.4181268101392694) +
                 (self.get_row_transitions()     * -3.2178882868487753) +
                 (self.get_col_transitions(data) * -9.348695305445199)  +
                 (self.get_holes(data)           * -7.899265427351652)  +
                 (self.get_well_sums(data)       * -3.3855972247263626))

        # log.info("get_ai_score()        %s" % score)
        # log.info("\nCURRENT BOARD\n%s\n" % self.field_to_string())
        return score

    def field_to_string(self):
        result = []
        for (line_number, line) in enumerate(reversed(self.field)):
            line_str = []
            for block in line:
                if block:
                    line_str.append(str(block))
                else:
                    line_str.append(' ')

            result.append("%2d|%s|" % (self.height - line_number, ''.join(line_str)))
        return '\n'.join(result)

    def get_ai_score_for_moves(self, moves_sequence):
        (rotation_count, left_move_count, right_move_count) = moves_sequence

        moves = []
        self.load_state()

        # Move down once so we have room to rotate
        self.down(False)
        moves.append(curses.KEY_DOWN)

        # rotate
        for x in range(rotation_count):
            self.rotate()
            moves.append(curses.KEY_UP)

        # move left
        for x in range(left_move_count):
            self.left()
            moves.append(curses.KEY_LEFT)

        for x in range(right_move_count):
            self.right()
            moves.append(curses.KEY_RIGHT)

        # Drop the piece all the way to the bottom
        moves.append('DROP')
        while not self.down(False):
            pass

        score = self.get_ai_score()
        return (score, moves)

    def ai_next_moves(self):
        """
        Return a sequence of moves consisting of
        curses.KEY_LEFT
        curses.KEY_RIGHT
        curses.KEY_UP
        curses.KEY_DOWN
        x - to drop all the way to the bottom
        """
        best_score = None
        best_score_moves = []
        self.save_state()

        max_rotations = get_max_rotations(self.current_piece[0])
        moves_to_try = []

        for rotation_count in range(max_rotations + 1):
            (max_left_moves, max_right_moves) = get_max_moves(self.current_piece[0], rotation_count)

            for left_moves in range(max_left_moves + 1):
                moves_to_try.append((rotation_count, left_moves, 0))

            for right_moves in range(max_right_moves + 1):
                moves_to_try.append((rotation_count, 0, right_moves))

        # log.info("ai_next_moves() %d moves_to_try" % len(moves_to_try))

        for seq in moves_to_try:
            (score, moves) = self.get_ai_score_for_moves(seq)

            if best_score is None or score > best_score:
                best_score = score
                best_score_moves = moves
            elif score == best_score:
                if len(moves) < len(best_score_moves):
                    best_score = score
                    best_score_moves = moves

        if not best_score_moves:
            log.info("ai_next_moves: score %s, moves %s" % (best_score, best_score_moves))
            self.continues = False
            raise Exception("no best_score_moves")

        # log.info("ai_next_moves: score %s, moves %s" % (best_score, moves_to_string(best_score_moves)))
        self.load_state()
        return best_score_moves


def main(stdscr, use_ai):
    curses.start_color()
    curses.init_color(7, 1000, 627, 0)
    curses.init_color(8, 1000, 1000, 1000)
    for i, j in enumerate([6, 3, 5, 2, 1, 4, 7, 8], 1):
        curses.init_pair(i, j, curses.COLOR_BLACK)
    curses.curs_set(0)
    curses.noecho()
    stdscr.nodelay(1)
    game = Tetris(20, 10)
    game.start(use_ai)
    stdscr.clear()

    while game.continues and not game.shutdown:
        if use_ai:
            moves = game.ai_next_moves()
            moves.append(curses.KEY_DOWN)
        else:
            moves = [stdscr.getch(), ]

        for c in moves:
            # uncomment to sleep between moves to see what is happening
            #if use_ai:
            #    time.sleep(0.1)

            if c == ord("q"):
                game.continues = False
                log.info("User hit 'q'")

            elif c == curses.KEY_LEFT:
                log.debug('Move LEFT')
                game.left()

            elif c == curses.KEY_RIGHT:
                log.debug('Move RIGHT')
                game.right()

            elif c == curses.KEY_UP:
                log.debug('Move UP')
                game.rotate()

            elif c == curses.KEY_DOWN:
                log.debug('Move DOWN')
                game.down(True)

            # Drop the piece all the way to the bottom
            # elif c == curses.KEY_SPACEBAR:
            elif c == ord("x") or c == 'DROP':
                log.debug('Move DROP')
                while not game.down(True):
                    pass

            for i, line in enumerate(game.curses_str().splitlines()):
                for j, c in enumerate(line):
                    if c == "0":
                        stdscr.addstr(i, j, " ")
                    elif c.isdigit():
                        stdscr.addstr(i, j, "█" if sys.version_info >= (3,) else "X",
                                      curses.color_pair(int(c)))
                    else:
                        stdscr.addstr(i, j, c, curses.color_pair(8))

            stdscr.addstr(22, 0, "Lines:  {}".format(game.lines), curses.color_pair(8))
            stdscr.addstr(23, 0, "Level:  {}".format(game.level), curses.color_pair(8))
            stdscr.addstr(24, 0, "Score:  {}".format(game.score), curses.color_pair(8))
            stdscr.addstr(25, 0, "Pieces: {}".format(game.pieces_placed), curses.color_pair(8))
            stdscr.refresh()

        game.pieces_placed += 1
        log.info("%d pieces, %d lines" % (game.pieces_placed, game.lines))
        # log.info("\nCURRENT BOARD\n%s\n" % game.field_to_string())

    # raw_input('Game Over...Paused') # this locks up...but does allow you to see the board when the game ended
    return game


if __name__ == "__main__":

    logging.basicConfig(filename='/tmp/tetris.log',
                        level=logging.INFO,
                        format='%(asctime)s %(levelname)7s %(filename)12s: %(message)s')
    log = logging.getLogger(__name__)

    # Color the errors and warnings in red
    logging.addLevelName(logging.ERROR, "\033[91m  %s\033[0m" % logging.getLevelName(logging.ERROR))
    logging.addLevelName(logging.WARNING, "\033[91m%s\033[0m" % logging.getLevelName(logging.WARNING))

    parser = argparse.ArgumentParser()
    parser.add_argument('--ai', action='store_true', help='Use AI to auto play', default=False)
    args = parser.parse_args()

    try:
        game = curses.wrapper(main, args.ai)
        print("Game over!")
        print("Lines: {}, Level: {}, Score: {}".format(game.lines, game.level, game.score))
    except Exception as e:
        log.exception(e)
