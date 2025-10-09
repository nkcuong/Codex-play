"""Simple Tetris clone built with pygame."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pygame

# Grid configuration
COLUMNS = 10
ROWS = 20
BLOCK_SIZE = 32

# Derived layout measurements
PLAYFIELD_WIDTH = COLUMNS * BLOCK_SIZE
PLAYFIELD_HEIGHT = ROWS * BLOCK_SIZE
SIDE_PANEL_WIDTH = 180

# Game pacing
BASE_FALL_DELAY = 700  # milliseconds between automatic drops at level 1
SOFT_DROP_DELAY = 60
FAST_FALL_MULTIPLIER = 0.85  # speeds up per level
LOCK_DELAY = 500  # give the player a short window before locking

# Styling
BACKGROUND_COLOR = (18, 18, 24)
GRID_LINE_COLOR = (40, 40, 52)
TEXT_COLOR = (228, 228, 241)

# Tetromino color palette (NES-style)
SHAPE_COLORS: Dict[str, Tuple[int, int, int]] = {
    "I": (80, 227, 230),
    "J": (36, 95, 223),
    "L": (223, 173, 36),
    "O": (242, 242, 60),
    "S": (83, 218, 63),
    "T": (177, 83, 226),
    "Z": (227, 78, 78),
}

# Coordinate definitions for each rotation. Each entry is a sequence of (x, y) offsets
# inside a 4x4 bounding box, with the spawn position at the top middle of the playfield.
SHAPES: Dict[str, List[List[Tuple[int, int]]]] = {
    "I": [
        [(0, 1), (1, 1), (2, 1), (3, 1)],
        [(2, 0), (2, 1), (2, 2), (2, 3)],
    ],
    "J": [
        [(0, 0), (0, 1), (1, 1), (2, 1)],
        [(1, 0), (2, 0), (1, 1), (1, 2)],
        [(0, 1), (1, 1), (2, 1), (2, 2)],
        [(1, 0), (1, 1), (0, 2), (1, 2)],
    ],
    "L": [
        [(2, 0), (0, 1), (1, 1), (2, 1)],
        [(1, 0), (1, 1), (1, 2), (2, 2)],
        [(0, 1), (1, 1), (2, 1), (0, 2)],
        [(0, 0), (1, 0), (1, 1), (1, 2)],
    ],
    "O": [
        [(1, 0), (2, 0), (1, 1), (2, 1)],
    ],
    "S": [
        [(1, 0), (2, 0), (0, 1), (1, 1)],
        [(1, 0), (1, 1), (2, 1), (2, 2)],
    ],
    "T": [
        [(1, 0), (0, 1), (1, 1), (2, 1)],
        [(1, 0), (1, 1), (2, 1), (1, 2)],
        [(0, 1), (1, 1), (2, 1), (1, 2)],
        [(1, 0), (0, 1), (1, 1), (1, 2)],
    ],
    "Z": [
        [(0, 0), (1, 0), (1, 1), (2, 1)],
        [(2, 0), (1, 1), (2, 1), (1, 2)],
    ],
}

SpawnOffsets = Tuple[int, int]


def spawn_offset_for_shape(piece: str) -> SpawnOffsets:
    """Place the piece near the center horizontally and just above the visible playfield."""
    if piece == "I":
        return COLUMNS // 2 - 2, -1
    if piece == "O":
        return COLUMNS // 2 - 2, 0
    return COLUMNS // 2 - 2, 0


@dataclass
class Tetromino:
    """Represents a falling tetromino."""

    kind: str
    rotation: int = 0
    x: int = 0
    y: int = 0

    def cells(self) -> List[Tuple[int, int]]:
        """Return the absolute grid coordinates occupied by the tetromino."""
        shape_rotations = SHAPES[self.kind]
        rotation_index = self.rotation % len(shape_rotations)
        return [(self.x + dx, self.y + dy) for dx, dy in shape_rotations[rotation_index]]

    def rotated(self, direction: int) -> "Tetromino":
        """Return a copy rotated by the provided direction (1 clockwise, -1 counter-clockwise)."""
        return Tetromino(
            kind=self.kind,
            rotation=(self.rotation + direction) % len(SHAPES[self.kind]),
            x=self.x,
            y=self.y,
        )

    def moved(self, dx: int, dy: int) -> "Tetromino":
        """Return a copy shifted by the provided deltas."""
        return Tetromino(
            kind=self.kind,
            rotation=self.rotation,
            x=self.x + dx,
            y=self.y + dy,
        )


class Board:
    """Playfield grid for Tetris."""

    def __init__(self) -> None:
        self.grid: List[List[Optional[str]]] = [[None for _ in range(COLUMNS)] for _ in range(ROWS)]
        self.lines_cleared = 0

    def inside(self, x: int, y: int) -> bool:
        return 0 <= x < COLUMNS and y < ROWS

    def cell_empty(self, x: int, y: int) -> bool:
        if y < 0:
            return True  # Allow spawning above the playfield
        return self.grid[y][x] is None

    def valid_position(self, piece: Tetromino) -> bool:
        for x, y in piece.cells():
            if not self.inside(x, y):
                return False
            if not self.cell_empty(x, y):
                return False
        return True

    def lock_piece(self, piece: Tetromino) -> int:
        """Lock the piece into the grid and return the number of cleared lines."""
        for x, y in piece.cells():
            if 0 <= y < ROWS:
                self.grid[y][x] = piece.kind
            else:
                # Piece locked outside the visible field -> game over
                raise RuntimeError("Game over")
        cleared = self._clear_lines()
        self.lines_cleared += cleared
        return cleared

    def _clear_lines(self) -> int:
        new_rows = [row for row in self.grid if any(cell is None for cell in row)]
        cleared = ROWS - len(new_rows)
        if cleared:
            self.grid = [[None for _ in range(COLUMNS)] for _ in range(cleared)] + new_rows
        return cleared

    def reset(self) -> None:
        self.grid = [[None for _ in range(COLUMNS)] for _ in range(ROWS)]
        self.lines_cleared = 0


class PieceQueue:
    """Implements a 7-bag queue for fair tetromino distribution."""

    def __init__(self) -> None:
        self._bag: List[str] = []

    def next_piece(self) -> Tetromino:
        if not self._bag:
            self._bag = list(SHAPES.keys())
            random.shuffle(self._bag)
        kind = self._bag.pop()
        x, y = spawn_offset_for_shape(kind)
        return Tetromino(kind=kind, x=x, y=y)


class TetrisGame:
    """Main game controller."""

    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("Tetris in Python")
        self.surface = pygame.display.set_mode((PLAYFIELD_WIDTH + SIDE_PANEL_WIDTH, PLAYFIELD_HEIGHT))
        self.clock = pygame.time.Clock()
        self.font_large = pygame.font.SysFont("Helvetica", 32)
        self.font_small = pygame.font.SysFont("Helvetica", 20)

        self.board = Board()
        self.queue = PieceQueue()
        self.drop_timer = 0
        self.lock_timer: Optional[int] = None
        self.current_piece = self.queue.next_piece()
        self.next_piece = self.queue.next_piece()
        self.score = 0
        self.level = 1
        self.soft_drop_active = False

    def reset(self) -> None:
        self.board.reset()
        self.queue = PieceQueue()
        self.current_piece = self.queue.next_piece()
        self.next_piece = self.queue.next_piece()
        self.drop_timer = 0
        self.lock_timer = None
        self.score = 0
        self.level = 1
        self.soft_drop_active = False

    def auto_drop_delay(self) -> int:
        base = BASE_FALL_DELAY * (FAST_FALL_MULTIPLIER ** (self.level - 1))
        return max(80, int(base))

    def update_level(self) -> None:
        self.level = 1 + self.board.lines_cleared // 10

    def scoring_for_clears(self, lines: int) -> int:
        table = {0: 0, 1: 100, 2: 300, 3: 500, 4: 800}
        return table.get(lines, 0) * self.level

    def attempt_move(self, piece: Tetromino) -> bool:
        if self.board.valid_position(piece):
            self.current_piece = piece
            self.lock_timer = None
            return True
        return False

    def attempt_rotation(self, direction: int) -> None:
        rotated = self.current_piece.rotated(direction)
        if self.board.valid_position(rotated):
            self.current_piece = rotated
            self.lock_timer = None
            return
        # Simple wall kick attempts: shift left/right
        for dx in (-1, 1, -2, 2):
            kicked = rotated.moved(dx, 0)
            if self.board.valid_position(kicked):
                self.current_piece = kicked
                self.lock_timer = None
                return

    def hard_drop(self) -> None:
        piece = self.current_piece
        distance = 0
        while True:
            moved = piece.moved(0, 1)
            if self.board.valid_position(moved):
                piece = moved
                distance += 1
            else:
                break
        self.current_piece = piece
        self.score += distance * 2
        self.lock_current_piece()

    def lock_current_piece(self) -> None:
        try:
            cleared = self.board.lock_piece(self.current_piece)
        except RuntimeError:
            self.game_over()
            return
        self.score += self.scoring_for_clears(cleared)
        if cleared:
            self.update_level()
        self.current_piece = self.next_piece
        self.next_piece = self.queue.next_piece()
        if not self.board.valid_position(self.current_piece):
            self.game_over()
        self.drop_timer = 0
        self.lock_timer = None

    def game_over(self) -> None:
        self.draw()
        pygame.display.flip()
        self.show_message("Game Over - Press R", size="large")
        pygame.display.flip()

        waiting = True
        while waiting:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    raise SystemExit
                if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                    self.reset()
                    waiting = False
            self.clock.tick(15)

    def run(self) -> None:
        while True:
            dt = self.clock.tick(60)
            self.handle_events()
            self.update(dt)
            self.draw()
            pygame.display.flip()

    def handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    raise SystemExit
                if event.key == pygame.K_LEFT:
                    self.attempt_move(self.current_piece.moved(-1, 0))
                if event.key == pygame.K_RIGHT:
                    self.attempt_move(self.current_piece.moved(1, 0))
                if event.key == pygame.K_DOWN:
                    self.soft_drop_active = True
                if event.key == pygame.K_UP:
                    self.attempt_rotation(1)
                if event.key == pygame.K_z:
                    self.attempt_rotation(-1)
                if event.key == pygame.K_SPACE:
                    self.hard_drop()
                if event.key == pygame.K_r:
                    self.reset()
            if event.type == pygame.KEYUP and event.key == pygame.K_DOWN:
                self.soft_drop_active = False

    def update(self, dt: int) -> None:
        delay = SOFT_DROP_DELAY if self.soft_drop_active else self.auto_drop_delay()
        self.drop_timer += dt

        if self.board.valid_position(self.current_piece.moved(0, 1)):
            if self.drop_timer >= delay:
                self.current_piece = self.current_piece.moved(0, 1)
                self.drop_timer = 0
        else:
            if self.lock_timer is None:
                self.lock_timer = 0
            self.lock_timer += dt
            if self.lock_timer >= LOCK_DELAY or self.drop_timer >= delay:
                self.lock_current_piece()

    def draw(self) -> None:
        self.surface.fill(BACKGROUND_COLOR)
        self.draw_grid()
        self.draw_board()
        self.draw_piece(self.current_piece)
        self.draw_next_piece()
        self.draw_hud()

    def draw_grid(self) -> None:
        for x in range(COLUMNS + 1):
            pygame.draw.line(
                self.surface,
                GRID_LINE_COLOR,
                (x * BLOCK_SIZE, 0),
                (x * BLOCK_SIZE, PLAYFIELD_HEIGHT),
                1,
            )
        for y in range(ROWS + 1):
            pygame.draw.line(
                self.surface,
                GRID_LINE_COLOR,
                (0, y * BLOCK_SIZE),
                (PLAYFIELD_WIDTH, y * BLOCK_SIZE),
                1,
            )

    def draw_board(self) -> None:
        for y, row in enumerate(self.board.grid):
            for x, cell in enumerate(row):
                if cell:
                    color = SHAPE_COLORS[cell]
                    rect = pygame.Rect(x * BLOCK_SIZE, y * BLOCK_SIZE, BLOCK_SIZE, BLOCK_SIZE)
                    pygame.draw.rect(self.surface, color, rect)
                    pygame.draw.rect(self.surface, (24, 24, 28), rect, 2)

    def draw_piece(self, piece: Tetromino, offset: Tuple[int, int] = (0, 0)) -> None:
        ox, oy = offset
        for x, y in piece.cells():
            if y < 0:
                continue
            rect = pygame.Rect(
                ox + x * BLOCK_SIZE,
                oy + y * BLOCK_SIZE,
                BLOCK_SIZE,
                BLOCK_SIZE,
            )
            pygame.draw.rect(self.surface, SHAPE_COLORS[piece.kind], rect)
            pygame.draw.rect(self.surface, (24, 24, 28), rect, 2)

    def draw_next_piece(self) -> None:
        preview_x = PLAYFIELD_WIDTH + 40
        preview_y = 80
        label = self.font_large.render("Next", True, TEXT_COLOR)
        self.surface.blit(label, (preview_x - 10, 30))
        ghost = self.next_piece
        preview_piece = Tetromino(kind=ghost.kind, rotation=0, x=0, y=0)
        # Center inside preview box
        for dx, dy in preview_piece.cells():
            rect = pygame.Rect(
                preview_x + dx * BLOCK_SIZE,
                preview_y + dy * BLOCK_SIZE,
                BLOCK_SIZE,
                BLOCK_SIZE,
            )
            pygame.draw.rect(self.surface, SHAPE_COLORS[ghost.kind], rect)
            pygame.draw.rect(self.surface, (24, 24, 28), rect, 2)

    def draw_hud(self) -> None:
        base_x = PLAYFIELD_WIDTH + 30
        score_label = self.font_small.render(f"Score: {self.score}", True, TEXT_COLOR)
        level_label = self.font_small.render(f"Level: {self.level}", True, TEXT_COLOR)
        lines_label = self.font_small.render(f"Lines: {self.board.lines_cleared}", True, TEXT_COLOR)
        controls = [
            " ← → : Move",
            " ↑ / Z : Rotate",
            " ↓ : Soft drop",
            " Space : Hard drop",
            " R : Reset",
            " Esc : Quit",
        ]

        self.surface.blit(score_label, (base_x, 260))
        self.surface.blit(level_label, (base_x, 290))
        self.surface.blit(lines_label, (base_x, 320))
        control_label = self.font_small.render("Controls:", True, TEXT_COLOR)
        self.surface.blit(control_label, (base_x, 360))
        for index, text in enumerate(controls):
            line = self.font_small.render(text, True, TEXT_COLOR)
            self.surface.blit(line, (base_x, 390 + index * 22))

    def show_message(self, message: str, size: str = "large") -> None:
        font = self.font_large if size == "large" else self.font_small
        text = font.render(message, True, TEXT_COLOR)
        rect = text.get_rect(center=(PLAYFIELD_WIDTH // 2, PLAYFIELD_HEIGHT // 2))
        self.surface.blit(text, rect)


def main() -> None:
    game = TetrisGame()
    game.run()


if __name__ == "__main__":
    main()
