"""Simple two-player chess built with pygame."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import copy
import pygame

# Board and UI constants
BOARD_SIZE = 8
SQUARE_SIZE = 80
WINDOW_SIZE = BOARD_SIZE * SQUARE_SIZE
FPS = 60

LIGHT_SQUARE_COLOR = (240, 217, 181)
DARK_SQUARE_COLOR = (181, 136, 99)
HIGHLIGHT_COLOR = (186, 202, 68)
MOVE_HINT_COLOR = (94, 140, 49)
CHECK_COLOR = (205, 92, 92)
BACKGROUND_COLOR = (30, 30, 30)

PIECE_COLORS = {"white": (240, 240, 240), "black": (48, 48, 48)}
PIECE_STROKE_COLORS = {"white": (120, 120, 120), "black": (220, 220, 220)}
PIECE_ACCENT_COLORS = {"white": (255, 255, 255), "black": (120, 120, 120)}


@dataclass(frozen=True)
class Piece:
    color: str  # "white" or "black"
    kind: str  # "K", "Q", "R", "B", "N", "P"


@dataclass(frozen=True)
class Move:
    start: Tuple[int, int]
    end: Tuple[int, int]
    promotion: Optional[str] = None
    is_castle: bool = False
    is_en_passant: bool = False


class GameState:
    def __init__(self) -> None:
        self.board: List[List[Optional[Piece]]] = [
            [None for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)
        ]
        self.turn: str = "white"
        self.castling_rights: Dict[str, bool] = {
            "white_kingside": True,
            "white_queenside": True,
            "black_kingside": True,
            "black_queenside": True,
        }
        self.en_passant_target: Optional[Tuple[int, int]] = None
        self.halfmove_clock = 0
        self.fullmove_number = 1
        self.move_history: List[Move] = []
        self.status_message: Optional[str] = None
        self.reset()

    def reset(self) -> None:
        self.board = [
            [
                Piece("black", "R"),
                Piece("black", "N"),
                Piece("black", "B"),
                Piece("black", "Q"),
                Piece("black", "K"),
                Piece("black", "B"),
                Piece("black", "N"),
                Piece("black", "R"),
            ],
            [Piece("black", "P")] * BOARD_SIZE,
            [None] * BOARD_SIZE,
            [None] * BOARD_SIZE,
            [None] * BOARD_SIZE,
            [None] * BOARD_SIZE,
            [Piece("white", "P")] * BOARD_SIZE,
            [
                Piece("white", "R"),
                Piece("white", "N"),
                Piece("white", "B"),
                Piece("white", "Q"),
                Piece("white", "K"),
                Piece("white", "B"),
                Piece("white", "N"),
                Piece("white", "R"),
            ],
        ]
        self.turn = "white"
        self.castling_rights = {
            "white_kingside": True,
            "white_queenside": True,
            "black_kingside": True,
            "black_queenside": True,
        }
        self.en_passant_target = None
        self.halfmove_clock = 0
        self.fullmove_number = 1
        self.move_history = []
        self.status_message = None

    def clone(self) -> "GameState":
        clone_state = GameState.__new__(GameState)
        clone_state.board = copy.deepcopy(self.board)
        clone_state.turn = self.turn
        clone_state.castling_rights = self.castling_rights.copy()
        clone_state.en_passant_target = self.en_passant_target
        clone_state.halfmove_clock = self.halfmove_clock
        clone_state.fullmove_number = self.fullmove_number
        clone_state.move_history = self.move_history.copy()
        clone_state.status_message = self.status_message
        return clone_state

    def inside(self, x: int, y: int) -> bool:
        return 0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE

    def piece_at(self, x: int, y: int) -> Optional[Piece]:
        if not self.inside(x, y):
            return None
        return self.board[y][x]

    def apply_move(self, move: Move, *, update_status: bool = True, record_history: bool = True) -> None:
        sx, sy = move.start
        tx, ty = move.end
        moving_piece = self.board[sy][sx]
        if moving_piece is None:
            return

        if record_history:
            self.move_history.append(move)

        # Update halfmove clock
        target_piece = self.board[ty][tx]
        if moving_piece.kind == "P" or target_piece is not None:
            self.halfmove_clock = 0
        else:
            self.halfmove_clock += 1

        # Handle en passant capture
        if move.is_en_passant and moving_piece.kind == "P":
            direction = -1 if moving_piece.color == "white" else 1
            self.board[ty - direction][tx] = None

        # Move the piece
        self.board[sy][sx] = None

        promoted_piece = self._get_promoted_piece(move, moving_piece)
        self.board[ty][tx] = promoted_piece

        # Handle castling rook movement
        if move.is_castle and moving_piece.kind == "K":
            if tx == 6:  # King side
                rook_from = (7, sy)
                rook_to = (5, sy)
            else:  # Queen side
                rook_from = (0, sy)
                rook_to = (3, sy)
            rx, ry = rook_from
            rtx, rty = rook_to
            self.board[rty][rtx] = self.board[ry][rx]
            self.board[ry][rx] = None

        # Update castling rights
        self._update_castling_rights(moving_piece, move, target_piece)

        # Update target for en passant
        self.en_passant_target = None
        if moving_piece.kind == "P" and abs(ty - sy) == 2:
            middle = (sx, (sy + ty) // 2)
            self.en_passant_target = middle

        # Switch turn and update move counters
        self.turn = "black" if self.turn == "white" else "white"
        if self.turn == "white":
            self.fullmove_number += 1

        if update_status:
            self._update_game_status()

    @staticmethod
    def _get_promoted_piece(move: Move, piece: Piece) -> Piece:
        if piece.kind == "P":
            if piece.color == "white" and move.end[1] == 0:
                return Piece(piece.color, move.promotion or "Q")
            if piece.color == "black" and move.end[1] == BOARD_SIZE - 1:
                return Piece(piece.color, move.promotion or "Q")
        return piece

    def _update_castling_rights(self, piece: Piece, move: Move, captured_piece: Optional[Piece]) -> None:
        sx, sy = move.start
        tx, ty = move.end

        if piece.kind == "K":
            if piece.color == "white":
                self.castling_rights["white_kingside"] = False
                self.castling_rights["white_queenside"] = False
            else:
                self.castling_rights["black_kingside"] = False
                self.castling_rights["black_queenside"] = False

        if piece.kind == "R":
            if piece.color == "white":
                if sx == 0 and sy == 7:
                    self.castling_rights["white_queenside"] = False
                if sx == 7 and sy == 7:
                    self.castling_rights["white_kingside"] = False
            else:
                if sx == 0 and sy == 0:
                    self.castling_rights["black_queenside"] = False
                if sx == 7 and sy == 0:
                    self.castling_rights["black_kingside"] = False

        # Captured rook affects castling
        if captured_piece and captured_piece.kind == "R":
            if captured_piece.color == "white":
                if tx == 0 and ty == 7:
                    self.castling_rights["white_queenside"] = False
                if tx == 7 and ty == 7:
                    self.castling_rights["white_kingside"] = False
            else:
                if tx == 0 and ty == 0:
                    self.castling_rights["black_queenside"] = False
                if tx == 7 and ty == 0:
                    self.castling_rights["black_kingside"] = False

    def _update_game_status(self) -> None:
        legal_moves = self.legal_moves(self.turn)
        in_check = self.is_in_check(self.turn)
        if in_check and not legal_moves:
            self.status_message = f"Checkmate! {'White' if self.turn == 'black' else 'Black'} wins."
        elif not in_check and not legal_moves:
            self.status_message = "Stalemate!"
        elif in_check:
            self.status_message = f"{self.turn.title()} in check."
        else:
            self.status_message = None

    def legal_moves(self, color: str) -> List[Move]:
        moves: List[Move] = []
        for y in range(BOARD_SIZE):
            for x in range(BOARD_SIZE):
                piece = self.board[y][x]
                if piece and piece.color == color:
                    moves.extend(self.legal_moves_from_square(x, y))
        return moves

    def legal_moves_from_square(self, x: int, y: int) -> List[Move]:
        piece = self.board[y][x]
        if piece is None:
            return []
        pseudo_moves = self.pseudo_moves(x, y)
        legal: List[Move] = []
        for move in pseudo_moves:
            clone = self.clone()
            clone.apply_move(move, update_status=False, record_history=False)
            if not clone.is_in_check(piece.color):
                legal.append(move)
        return legal

    def pseudo_moves(self, x: int, y: int) -> List[Move]:
        piece = self.board[y][x]
        if piece is None:
            return []
        moves: List[Move] = []
        if piece.kind == "P":
            moves.extend(self._pawn_moves(x, y, piece))
        elif piece.kind == "N":
            moves.extend(self._knight_moves(x, y, piece))
        elif piece.kind == "B":
            moves.extend(self._sliding_moves(x, y, piece, directions=[(-1, -1), (-1, 1), (1, -1), (1, 1)]))
        elif piece.kind == "R":
            moves.extend(self._sliding_moves(x, y, piece, directions=[(0, -1), (0, 1), (-1, 0), (1, 0)]))
        elif piece.kind == "Q":
            moves.extend(
                self._sliding_moves(
                    x,
                    y,
                    piece,
                    directions=[
                        (-1, -1),
                        (-1, 1),
                        (1, -1),
                        (1, 1),
                        (0, -1),
                        (0, 1),
                        (-1, 0),
                        (1, 0),
                    ],
                )
            )
        elif piece.kind == "K":
            moves.extend(self._king_moves(x, y, piece))
        return moves

    def _pawn_moves(self, x: int, y: int, piece: Piece) -> List[Move]:
        moves: List[Move] = []
        direction = -1 if piece.color == "white" else 1
        start_rank = 6 if piece.color == "white" else 1

        one_forward = (x, y + direction)
        if self._is_empty_square(*one_forward):
            moves.append(Move((x, y), one_forward))
            two_forward = (x, y + 2 * direction)
            if y == start_rank and self._is_empty_square(*two_forward):
                moves.append(Move((x, y), two_forward))

        # Captures
        for dx in (-1, 1):
            target = (x + dx, y + direction)
            if not self.inside(*target):
                continue
            target_piece = self.piece_at(*target)
            if target_piece and target_piece.color != piece.color:
                moves.append(Move((x, y), target))

        # En passant
        if self.en_passant_target:
            ep_x, ep_y = self.en_passant_target
            if ep_y == y + direction and abs(ep_x - x) == 1:
                moves.append(Move((x, y), (ep_x, ep_y), is_en_passant=True))

        return moves

    def _knight_moves(self, x: int, y: int, piece: Piece) -> List[Move]:
        moves: List[Move] = []
        for dx, dy in [
            (-2, -1),
            (-2, 1),
            (-1, -2),
            (-1, 2),
            (1, -2),
            (1, 2),
            (2, -1),
            (2, 1),
        ]:
            target = (x + dx, y + dy)
            if not self.inside(*target):
                continue
            target_piece = self.piece_at(*target)
            if target_piece is None or target_piece.color != piece.color:
                moves.append(Move((x, y), target))
        return moves

    def _sliding_moves(self, x: int, y: int, piece: Piece, directions: List[Tuple[int, int]]) -> List[Move]:
        moves: List[Move] = []
        for dx, dy in directions:
            tx, ty = x + dx, y + dy
            while self.inside(tx, ty):
                target_piece = self.piece_at(tx, ty)
                if target_piece is None:
                    moves.append(Move((x, y), (tx, ty)))
                else:
                    if target_piece.color != piece.color:
                        moves.append(Move((x, y), (tx, ty)))
                    break
                tx += dx
                ty += dy
        return moves

    def _king_moves(self, x: int, y: int, piece: Piece) -> List[Move]:
        moves: List[Move] = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                target = (x + dx, y + dy)
                if not self.inside(*target):
                    continue
                target_piece = self.piece_at(*target)
                if target_piece is None or target_piece.color != piece.color:
                    moves.append(Move((x, y), target))
        moves.extend(self._castling_moves(x, y, piece))
        return moves

    def _castling_moves(self, x: int, y: int, piece: Piece) -> List[Move]:
        moves: List[Move] = []
        if self.is_in_check(piece.color):
            return moves
        rank = 7 if piece.color == "white" else 0
        opponent = "black" if piece.color == "white" else "white"

        if piece.color == "white":
            king_side_right = self.castling_rights["white_kingside"]
            queen_side_right = self.castling_rights["white_queenside"]
        else:
            king_side_right = self.castling_rights["black_kingside"]
            queen_side_right = self.castling_rights["black_queenside"]

        # King-side castling
        rook_square = self.piece_at(7, rank)
        if king_side_right and rook_square and rook_square.kind == "R" and rook_square.color == piece.color:
            if (
                self._is_empty_square(5, rank)
                and self._is_empty_square(6, rank)
                and not self.is_square_attacked(5, rank, opponent)
                and not self.is_square_attacked(6, rank, opponent)
            ):
                moves.append(Move((x, y), (6, rank), is_castle=True))

        # Queen-side castling
        rook_square = self.piece_at(0, rank)
        if queen_side_right and rook_square and rook_square.kind == "R" and rook_square.color == piece.color:
            if (
                self._is_empty_square(1, rank)
                and self._is_empty_square(2, rank)
                and self._is_empty_square(3, rank)
                and not self.is_square_attacked(2, rank, opponent)
                and not self.is_square_attacked(3, rank, opponent)
            ):
                moves.append(Move((x, y), (2, rank), is_castle=True))

        return moves

    def _is_empty_square(self, x: int, y: int) -> bool:
        return self.inside(x, y) and self.piece_at(x, y) is None

    def is_in_check(self, color: str) -> bool:
        king_position = self._find_king(color)
        if king_position is None:
            return False
        opponent = "black" if color == "white" else "white"
        return self.is_square_attacked(*king_position, attacker=opponent)

    def _find_king(self, color: str) -> Optional[Tuple[int, int]]:
        for y in range(BOARD_SIZE):
            for x in range(BOARD_SIZE):
                piece = self.board[y][x]
                if piece and piece.color == color and piece.kind == "K":
                    return (x, y)
        return None

    def is_square_attacked(self, x: int, y: int, attacker: str) -> bool:
        # Pawn attacks
        if attacker == "white":
            pawn_sources = [(x - 1, y + 1), (x + 1, y + 1)]
        else:
            pawn_sources = [(x - 1, y - 1), (x + 1, y - 1)]
        for px, py in pawn_sources:
            if self.inside(px, py):
                piece = self.board[py][px]
                if piece and piece.color == attacker and piece.kind == "P":
                    return True

        # Knight attacks
        for dx, dy in [
            (-2, -1),
            (-2, 1),
            (-1, -2),
            (-1, 2),
            (1, -2),
            (1, 2),
            (2, -1),
            (2, 1),
        ]:
            nx, ny = x + dx, y + dy
            if self.inside(nx, ny):
                piece = self.board[ny][nx]
                if piece and piece.color == attacker and piece.kind == "N":
                    return True

        # Sliding pieces
        for dx, dy, kinds in [
            (-1, 0, ("R", "Q")),
            (1, 0, ("R", "Q")),
            (0, -1, ("R", "Q")),
            (0, 1, ("R", "Q")),
            (-1, -1, ("B", "Q")),
            (-1, 1, ("B", "Q")),
            (1, -1, ("B", "Q")),
            (1, 1, ("B", "Q")),
        ]:
            tx, ty = x + dx, y + dy
            while self.inside(tx, ty):
                piece = self.board[ty][tx]
                if piece:
                    if piece.color == attacker and piece.kind in kinds:
                        return True
                    break
                tx += dx
                ty += dy

        # King attacks
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                kx, ky = x + dx, y + dy
                if self.inside(kx, ky):
                    piece = self.board[ky][kx]
                    if piece and piece.color == attacker and piece.kind == "K":
                        return True

        return False


class ChessGame:
    def __init__(self) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_SIZE, WINDOW_SIZE + 80))
        pygame.display.set_caption("Chess in Python")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Helvetica", 32, bold=True)
        self.small_font = pygame.font.SysFont("Helvetica", 20)
        self.piece_images = self._generate_piece_images()
        self.state = GameState()
        self.selected_square: Optional[Tuple[int, int]] = None
        self.legal_targets: List[Move] = []
        self.running = True

    def reset(self) -> None:
        self.state.reset()
        self.selected_square = None
        self.legal_targets = []

    def run(self) -> None:
        while self.running:
            self.clock.tick(FPS)
            self.handle_events()
            self.draw()
            pygame.display.flip()

    def handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                if event.key == pygame.K_r:
                    self.reset()
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.handle_click(event.pos)

    def handle_click(self, position: Tuple[int, int]) -> None:
        x, y = position
        if y > WINDOW_SIZE:
            return
        board_x = x // SQUARE_SIZE
        board_y = y // SQUARE_SIZE
        if not self.state.inside(board_x, board_y):
            return

        if self.selected_square:
            # Attempt to move if target matches legal move
            for move in self.legal_targets:
                if move.end == (board_x, board_y):
                    # Promotion dialog simplified: auto-promote to queen, hold Shift for Knight
                    if (
                        self.state.piece_at(*self.selected_square).kind == "P"  # type: ignore[union-attr]
                        and (board_y == 0 or board_y == BOARD_SIZE - 1)
                    ):
                        mods = pygame.key.get_mods()
                        promotion = "N" if mods & pygame.KMOD_SHIFT else "Q"
                        move = Move(move.start, move.end, promotion=promotion, is_castle=move.is_castle, is_en_passant=move.is_en_passant)
                    self.state.apply_move(move)
                    self.selected_square = None
                    self.legal_targets = []
                    return

            # Clicking elsewhere cancels selection / selects new square
            self.selected_square = None
            self.legal_targets = []

        piece = self.state.piece_at(board_x, board_y)
        if piece and piece.color == self.state.turn:
            self.selected_square = (board_x, board_y)
            self.legal_targets = self.state.legal_moves_from_square(board_x, board_y)

    def draw(self) -> None:
        self.screen.fill(BACKGROUND_COLOR)
        self.draw_board()
        self.draw_pieces()
        self.draw_status()

    def draw_board(self) -> None:
        for y in range(BOARD_SIZE):
            for x in range(BOARD_SIZE):
                color = LIGHT_SQUARE_COLOR if (x + y) % 2 == 0 else DARK_SQUARE_COLOR
                rect = pygame.Rect(x * SQUARE_SIZE, y * SQUARE_SIZE, SQUARE_SIZE, SQUARE_SIZE)
                pygame.draw.rect(self.screen, color, rect)

        # Highlight last move
        if self.state.move_history:
            last_move = self.state.move_history[-1]
            for square in (last_move.start, last_move.end):
                self._draw_square_overlay(square, HIGHLIGHT_COLOR, alpha=100)

        # Highlight selection
        if self.selected_square:
            self._draw_square_overlay(self.selected_square, HIGHLIGHT_COLOR, alpha=160)
            for move in self.legal_targets:
                self._draw_square_overlay(move.end, MOVE_HINT_COLOR, alpha=150)

        # Highlight checks
        for color in ("white", "black"):
            if self.state.is_in_check(color):
                king_pos = self.state._find_king(color)
                if king_pos:
                    self._draw_square_overlay(king_pos, CHECK_COLOR, alpha=160)

    def _draw_square_overlay(self, square: Tuple[int, int], color: Tuple[int, int, int], alpha: int) -> None:
        overlay = pygame.Surface((SQUARE_SIZE, SQUARE_SIZE), pygame.SRCALPHA)
        overlay.fill((*color, alpha))
        x, y = square
        self.screen.blit(overlay, (x * SQUARE_SIZE, y * SQUARE_SIZE))

    def draw_pieces(self) -> None:
        for y in range(BOARD_SIZE):
            for x in range(BOARD_SIZE):
                piece = self.state.board[y][x]
                if piece:
                    self.draw_piece(piece, x, y)

    def draw_piece(self, piece: Piece, x: int, y: int) -> None:
        image = self.piece_images[(piece.color, piece.kind)]
        rect = image.get_rect()
        rect.topleft = (x * SQUARE_SIZE, y * SQUARE_SIZE)
        self.screen.blit(image, rect)

    def draw_status(self) -> None:
        panel_rect = pygame.Rect(0, WINDOW_SIZE, WINDOW_SIZE, 80)
        pygame.draw.rect(self.screen, (45, 45, 45), panel_rect)
        turn_text = self.small_font.render(f"Turn: {self.state.turn.title()}", True, (240, 240, 240))
        self.screen.blit(turn_text, (20, WINDOW_SIZE + 20))
        move_text = self.small_font.render(f"Move: {self.state.fullmove_number}", True, (240, 240, 240))
        self.screen.blit(move_text, (20, WINDOW_SIZE + 45))

        if self.state.status_message:
            message = self.small_font.render(self.state.status_message, True, (255, 215, 0))
            self.screen.blit(message, (200, WINDOW_SIZE + 30))

    def _generate_piece_images(self) -> Dict[Tuple[str, str], pygame.Surface]:
        images: Dict[Tuple[str, str], pygame.Surface] = {}
        draw_map = {
            "K": self._draw_king_sprite,
            "Q": self._draw_queen_sprite,
            "R": self._draw_rook_sprite,
            "B": self._draw_bishop_sprite,
            "N": self._draw_knight_sprite,
            "P": self._draw_pawn_sprite,
        }
        for color in ("white", "black"):
            for kind in ("K", "Q", "R", "B", "N", "P"):
                surface = pygame.Surface((SQUARE_SIZE, SQUARE_SIZE), pygame.SRCALPHA)
                draw_method = draw_map[kind]
                draw_method(surface, color)
                images[(color, kind)] = surface
        return images

    def _colors_for_piece(self, color: str) -> Tuple[Tuple[int, int, int], Tuple[int, int, int], Tuple[int, int, int]]:
        return (
            PIECE_COLORS[color],
            PIECE_STROKE_COLORS[color],
            PIECE_ACCENT_COLORS[color],
        )

    def _draw_p_sprite_base(self, surface: pygame.Surface, color: str) -> None:
        fill, stroke, accent = self._colors_for_piece(color)
        s = SQUARE_SIZE
        base_rect = pygame.Rect(int(s * 0.3), int(s * 0.55), int(s * 0.4), int(s * 0.32))
        pygame.draw.rect(surface, fill, base_rect, border_radius=int(s * 0.06))
        pygame.draw.rect(surface, stroke, base_rect, width=3, border_radius=int(s * 0.06))
        top_circle_center = (s // 2, int(s * 0.35))
        top_circle_radius = int(s * 0.18)
        pygame.draw.circle(surface, fill, top_circle_center, top_circle_radius)
        pygame.draw.circle(surface, stroke, top_circle_center, top_circle_radius, 3)
        collar_rect = pygame.Rect(int(s * 0.28), int(s * 0.48), int(s * 0.44), int(s * 0.08))
        pygame.draw.rect(surface, fill, collar_rect, border_radius=int(s * 0.04))
        pygame.draw.rect(surface, stroke, collar_rect, width=2, border_radius=int(s * 0.04))
        if color == "white":
            highlight = pygame.Rect(int(s * 0.42), int(s * 0.24), int(s * 0.06), int(s * 0.08))
            pygame.draw.rect(surface, accent, highlight, border_radius=int(s * 0.02))

    def _draw_p_sprite_finishing(self, surface: pygame.Surface, color: str) -> None:
        fill, stroke, accent = self._colors_for_piece(color)
        s = SQUARE_SIZE
        base_plate = pygame.Rect(int(s * 0.22), int(s * 0.82), int(s * 0.56), int(s * 0.12))
        pygame.draw.rect(surface, fill, base_plate, border_radius=int(s * 0.06))
        pygame.draw.rect(surface, stroke, base_plate, width=3, border_radius=int(s * 0.06))
        pygame.draw.line(
            surface,
            accent,
            (int(s * 0.35), int(s * 0.6)),
            (int(s * 0.65), int(s * 0.6)),
            2,
        )

    def _draw_p_sprite(self, surface: pygame.Surface, color: str) -> None:
        self._draw_p_sprite_base(surface, color)
        self._draw_p_sprite_finishing(surface, color)

    def _draw_pawn_sprite(self, surface: pygame.Surface, color: str) -> None:
        self._draw_p_sprite(surface, color)

    def _draw_rook_sprite(self, surface: pygame.Surface, color: str) -> None:
        fill, stroke, accent = self._colors_for_piece(color)
        s = SQUARE_SIZE
        tower_rect = pygame.Rect(int(s * 0.25), int(s * 0.32), int(s * 0.5), int(s * 0.5))
        pygame.draw.rect(surface, fill, tower_rect, border_radius=int(s * 0.06))
        pygame.draw.rect(surface, stroke, tower_rect, width=3, border_radius=int(s * 0.06))
        top_rect = pygame.Rect(int(s * 0.18), int(s * 0.22), int(s * 0.64), int(s * 0.12))
        pygame.draw.rect(surface, fill, top_rect, border_radius=int(s * 0.06))
        pygame.draw.rect(surface, stroke, top_rect, width=3, border_radius=int(s * 0.06))
        crenel_width = int(s * 0.16)
        gap = int(s * 0.06)
        for i in range(3):
            crenel = pygame.Rect(int(s * 0.2) + i * (crenel_width + gap), int(s * 0.18), crenel_width, int(s * 0.08))
            pygame.draw.rect(surface, fill, crenel, border_radius=int(s * 0.04))
            pygame.draw.rect(surface, stroke, crenel, width=2, border_radius=int(s * 0.04))
        base_plate = pygame.Rect(int(s * 0.18), int(s * 0.82), int(s * 0.64), int(s * 0.12))
        pygame.draw.rect(surface, fill, base_plate, border_radius=int(s * 0.08))
        pygame.draw.rect(surface, stroke, base_plate, width=3, border_radius=int(s * 0.08))
        pygame.draw.line(surface, accent, (int(s * 0.28), int(s * 0.54)), (int(s * 0.72), int(s * 0.54)), 2)

    def _draw_bishop_sprite(self, surface: pygame.Surface, color: str) -> None:
        fill, stroke, accent = self._colors_for_piece(color)
        s = SQUARE_SIZE
        body_rect = pygame.Rect(int(s * 0.3), int(s * 0.34), int(s * 0.4), int(s * 0.5))
        pygame.draw.ellipse(surface, fill, body_rect)
        pygame.draw.ellipse(surface, stroke, body_rect, 3)
        mitre_rect = pygame.Rect(int(s * 0.36), int(s * 0.18), int(s * 0.28), int(s * 0.32))
        pygame.draw.ellipse(surface, fill, mitre_rect)
        pygame.draw.ellipse(surface, stroke, mitre_rect, 3)
        pygame.draw.line(
            surface,
            accent,
            (int(s * 0.5), int(s * 0.22)),
            (int(s * 0.64), int(s * 0.38)),
            3,
        )
        collar_rect = pygame.Rect(int(s * 0.28), int(s * 0.52), int(s * 0.44), int(s * 0.08))
        pygame.draw.rect(surface, fill, collar_rect, border_radius=int(s * 0.04))
        pygame.draw.rect(surface, stroke, collar_rect, width=2, border_radius=int(s * 0.04))
        base_plate = pygame.Rect(int(s * 0.2), int(s * 0.82), int(s * 0.6), int(s * 0.12))
        pygame.draw.rect(surface, fill, base_plate, border_radius=int(s * 0.06))
        pygame.draw.rect(surface, stroke, base_plate, width=3, border_radius=int(s * 0.06))

    def _draw_knight_sprite(self, surface: pygame.Surface, color: str) -> None:
        fill, stroke, accent = self._colors_for_piece(color)
        s = SQUARE_SIZE
        horse_points = [
            (int(s * 0.28), int(s * 0.78)),
            (int(s * 0.28), int(s * 0.45)),
            (int(s * 0.32), int(s * 0.34)),
            (int(s * 0.48), int(s * 0.22)),
            (int(s * 0.58), int(s * 0.18)),
            (int(s * 0.62), int(s * 0.32)),
            (int(s * 0.68), int(s * 0.4)),
            (int(s * 0.6), int(s * 0.46)),
            (int(s * 0.7), int(s * 0.6)),
            (int(s * 0.64), int(s * 0.78)),
        ]
        pygame.draw.polygon(surface, fill, horse_points)
        pygame.draw.polygon(surface, stroke, horse_points, 3)
        eye_center = (int(s * 0.55), int(s * 0.33))
        pygame.draw.circle(surface, accent, eye_center, int(s * 0.03))
        mane_points = [
            (int(s * 0.42), int(s * 0.26)),
            (int(s * 0.36), int(s * 0.18)),
            (int(s * 0.32), int(s * 0.28)),
            (int(s * 0.28), int(s * 0.2)),
        ]
        pygame.draw.lines(surface, stroke, False, mane_points, 3)
        base_plate = pygame.Rect(int(s * 0.2), int(s * 0.82), int(s * 0.6), int(s * 0.12))
        pygame.draw.rect(surface, fill, base_plate, border_radius=int(s * 0.06))
        pygame.draw.rect(surface, stroke, base_plate, width=3, border_radius=int(s * 0.06))

    def _draw_queen_sprite(self, surface: pygame.Surface, color: str) -> None:
        fill, stroke, accent = self._colors_for_piece(color)
        s = SQUARE_SIZE
        skirt_rect = pygame.Rect(int(s * 0.24), int(s * 0.42), int(s * 0.52), int(s * 0.46))
        pygame.draw.ellipse(surface, fill, skirt_rect)
        pygame.draw.ellipse(surface, stroke, skirt_rect, 3)
        waist_rect = pygame.Rect(int(s * 0.34), int(s * 0.36), int(s * 0.32), int(s * 0.24))
        pygame.draw.ellipse(surface, fill, waist_rect)
        pygame.draw.ellipse(surface, stroke, waist_rect, 3)
        crown_base = pygame.Rect(int(s * 0.3), int(s * 0.2), int(s * 0.4), int(s * 0.18))
        pygame.draw.ellipse(surface, fill, crown_base)
        pygame.draw.ellipse(surface, stroke, crown_base, 3)
        for i in range(3):
            jewel_center = (int(s * (0.38 + i * 0.12)), int(s * 0.2))
            pygame.draw.circle(surface, accent, jewel_center, int(s * 0.04))
            pygame.draw.circle(surface, stroke, jewel_center, int(s * 0.04), 2)
        base_plate = pygame.Rect(int(s * 0.2), int(s * 0.82), int(s * 0.6), int(s * 0.12))
        pygame.draw.rect(surface, fill, base_plate, border_radius=int(s * 0.06))
        pygame.draw.rect(surface, stroke, base_plate, width=3, border_radius=int(s * 0.06))

    def _draw_king_sprite(self, surface: pygame.Surface, color: str) -> None:
        fill, stroke, accent = self._colors_for_piece(color)
        s = SQUARE_SIZE
        robe_rect = pygame.Rect(int(s * 0.28), int(s * 0.34), int(s * 0.44), int(s * 0.5))
        pygame.draw.rect(surface, fill, robe_rect, border_radius=int(s * 0.08))
        pygame.draw.rect(surface, stroke, robe_rect, width=3, border_radius=int(s * 0.08))
        collar_rect = pygame.Rect(int(s * 0.3), int(s * 0.28), int(s * 0.4), int(s * 0.1))
        pygame.draw.rect(surface, fill, collar_rect, border_radius=int(s * 0.04))
        pygame.draw.rect(surface, stroke, collar_rect, width=2, border_radius=int(s * 0.04))
        cross_height = int(s * 0.18)
        cross_width = int(s * 0.08)
        center_x = s // 2
        pygame.draw.rect(
            surface,
            fill,
            pygame.Rect(center_x - cross_width // 2, int(s * 0.14), cross_width, cross_height),
            border_radius=int(s * 0.04),
        )
        pygame.draw.rect(
            surface,
            stroke,
            pygame.Rect(center_x - cross_width // 2, int(s * 0.14), cross_width, cross_height),
            width=2,
            border_radius=int(s * 0.04),
        )
        pygame.draw.rect(
            surface,
            fill,
            pygame.Rect(center_x - int(s * 0.12), int(s * 0.2), int(s * 0.24), int(s * 0.06)),
            border_radius=int(s * 0.04),
        )
        pygame.draw.rect(
            surface,
            stroke,
            pygame.Rect(center_x - int(s * 0.12), int(s * 0.2), int(s * 0.24), int(s * 0.06)),
            width=2,
            border_radius=int(s * 0.04),
        )
        crown_rect = pygame.Rect(int(s * 0.3), int(s * 0.22), int(s * 0.4), int(s * 0.2))
        pygame.draw.ellipse(surface, fill, crown_rect)
        pygame.draw.ellipse(surface, stroke, crown_rect, 3)
        base_plate = pygame.Rect(int(s * 0.2), int(s * 0.82), int(s * 0.6), int(s * 0.12))
        pygame.draw.rect(surface, fill, base_plate, border_radius=int(s * 0.06))
        pygame.draw.rect(surface, stroke, base_plate, width=3, border_radius=int(s * 0.06))



def main() -> None:
    game = ChessGame()
    game.run()
    pygame.quit()


if __name__ == "__main__":
    main()
