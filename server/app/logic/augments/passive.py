from __future__ import annotations

"""All 25 passive augments."""

import time
import random
from app.logic.augments.base import BaseAugment, AugmentContext, BoardEntity


# ── CD Modifiers ─────────────────────────────────────────────────────────────

class ToursEnFolie(BaseAugment):
    id = "tours_en_folie"
    name = "Tours en folie"
    description = "-50% de cooldown pour vos tours"

    def modify_cooldown(self, piece, base_cd, ctx):
        if piece.color.value == ctx.player_color and piece.piece_type.value == "rook":
            return base_cd * 0.5
        return base_cd


class DroitDesFemmes(BaseAugment):
    id = "droit_des_femmes"
    name = "Droit des femmes"
    description = "-60% de cooldown pour votre dame"

    def modify_cooldown(self, piece, base_cd, ctx):
        if piece.color.value == ctx.player_color and piece.piece_type.value == "queen":
            return base_cd * 0.4
        return base_cd


class GradeDHonneur(BaseAugment):
    id = "grade_dhonneur"
    name = "Grade d'honneur"
    description = "-50% de cooldown pour vos cavaliers et fous"

    def modify_cooldown(self, piece, base_cd, ctx):
        if piece.color.value == ctx.player_color and piece.piece_type.value in ("knight", "bishop"):
            return base_cd * 0.5
        return base_cd


class AvantageDuRetard(BaseAugment):
    id = "avantage_du_retard"
    name = "Avantage du retard"
    description = "Si vous avez 3+ pièces de moins, -30% de CD global"

    def modify_cooldown(self, piece, base_cd, ctx):
        if piece.color.value != ctx.player_color:
            return base_cd
        my_count = ctx.count_alive(ctx.player_color)
        opp_count = ctx.count_alive(ctx.opponent_color)
        if opp_count - my_count >= 3:
            return base_cd * 0.7
        return base_cd


class CarreMagique(BaseAugment):
    id = "carre_magique"
    name = "Carré magique"
    description = "+20% de réduction de CD par pion allié dans les 4 cases centrales"

    def modify_cooldown(self, piece, base_cd, ctx):
        if piece.color.value != ctx.player_color:
            return base_cd
        center_squares = [(3, 3), (3, 4), (4, 3), (4, 4)]
        count = 0
        for r, c in center_squares:
            p = ctx.piece_at(r, c)
            if p and p.alive and p.color.value == ctx.player_color and p.piece_type.value == "pawn":
                count += 1
        if count > 0:
            reduction = min(count * 0.20, 0.80)
            return base_cd * (1.0 - reduction)
        return base_cd


class DanseDuSang(BaseAugment):
    id = "danse_du_sang"
    name = "Danse du sang"
    description = "Si une de vos pièces capture, son CD est réduit de 70% (sauf pions)"

    def on_piece_captured(self, captured, capturer, ctx):
        if capturer and capturer.color.value == ctx.player_color:
            if capturer.piece_type.value != "pawn":
                # Adjust last_move_time backward so effective CD is 30% of base
                from app.logic.board import COOLDOWNS
                base_cd = COOLDOWNS.get(capturer.piece_type, 1.0)
                reduced = base_cd * 0.3
                skip = base_cd - reduced
                capturer.last_move_time = max(0.0, capturer.last_move_time - skip)
        return []


class Revanchard(BaseAugment):
    id = "revanchard"
    name = "Revanchard"
    description = "Quand une pièce adverse capture une de vos pièces, son CD est doublé"

    def on_piece_captured(self, captured, capturer, ctx):
        if captured and captured.color.value == ctx.player_color and capturer:
            # Double the effective CD by pushing last_move_time forward
            from app.logic.board import COOLDOWNS
            base_cd = COOLDOWNS.get(capturer.piece_type, 1.0)
            capturer.last_move_time = capturer.last_move_time + base_cd
        return []


# ── Movement Modifiers ───────────────────────────────────────────────────────

class Sprinteurs(BaseAugment):
    id = "sprinteurs"
    name = "Sprinteurs"
    description = "Vos pions peuvent se déplacer de 2 cases à chaque mouvement"

    def modify_moves(self, piece, moves, ctx):
        if piece.color.value != ctx.player_color or piece.piece_type.value != "pawn":
            return moves
        direction = 1 if piece.color.value == "white" else -1
        two_ahead_r = piece.row + 2 * direction
        one_ahead_r = piece.row + direction
        if 0 <= two_ahead_r <= 7:
            if (ctx.piece_at(one_ahead_r, piece.col) is None
                    and ctx.piece_at(two_ahead_r, piece.col) is None):
                moves.add((two_ahead_r, piece.col))
        return moves


class MarcheArriere(BaseAugment):
    id = "marche_arriere"
    name = "Marche arrière"
    description = "Vos pions peuvent se déplacer vers l'arrière"

    def modify_moves(self, piece, moves, ctx):
        if piece.color.value != ctx.player_color or piece.piece_type.value != "pawn":
            return moves
        backward = -1 if piece.color.value == "white" else 1
        back_r = piece.row + backward
        if 0 <= back_r <= 7:
            if ctx.piece_at(back_r, piece.col) is None:
                moves.add((back_r, piece.col))
            # Backward diagonal captures
            for dc in (-1, 1):
                c = piece.col + dc
                if 0 <= c <= 7:
                    target = ctx.piece_at(back_r, c)
                    if target and target.color.value != piece.color.value:
                        moves.add((back_r, c))
        return moves


class CouronneDeLauriers(BaseAugment):
    id = "couronne_de_lauriers"
    name = "Couronne de lauriers"
    description = "Votre roi se déplace de 2 cases dans n'importe quelle direction"

    def modify_moves(self, piece, moves, ctx):
        if piece.color.value != ctx.player_color or piece.piece_type.value != "king":
            return moves
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                if dr == 0 and dc == 0:
                    continue
                if abs(dr) <= 1 and abs(dc) <= 1:
                    continue  # already in standard moves
                r, c = piece.row + dr, piece.col + dc
                if not (0 <= r <= 7 and 0 <= c <= 7):
                    continue
                target = ctx.piece_at(r, c)
                if target and target.color.value == piece.color.value:
                    continue
                # Check entity blocking
                if ctx.entity_at(r, c):
                    ent = ctx.entity_at(r, c)
                    if ent.entity_type in ("duck", "wall"):
                        continue
                moves.add((r, c))
        return moves


class Transition(BaseAugment):
    id = "transition"
    name = "Transition"
    description = "Votre roi a les déplacements de la dame, votre dame a ceux du roi"
    incompatible_with = ["sexo_permutation"]

    def modify_moves(self, piece, moves, ctx):
        if piece.color.value != ctx.player_color:
            return moves
        if piece.piece_type.value == "king":
            # Replace king moves with queen moves (sliding + diagonal)
            moves.clear()
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]:
                for dist in range(1, 8):
                    r, c = piece.row + dr * dist, piece.col + dc * dist
                    if not (0 <= r <= 7 and 0 <= c <= 7):
                        break
                    target = ctx.piece_at(r, c)
                    ent = ctx.entity_at(r, c)
                    if ent and ent.entity_type in ("duck", "wall"):
                        break
                    if target:
                        if target.color.value != piece.color.value:
                            moves.add((r, c))
                        break
                    moves.add((r, c))
        elif piece.piece_type.value == "queen":
            # Replace queen moves with king moves (1 square)
            moves.clear()
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    r, c = piece.row + dr, piece.col + dc
                    if 0 <= r <= 7 and 0 <= c <= 7:
                        target = ctx.piece_at(r, c)
                        if not target or target.color.value != piece.color.value:
                            moves.add((r, c))
        return moves


class Licorne(BaseAugment):
    id = "licorne"
    name = "Licorne"
    description = "Vos cavaliers deviennent des licornes (cavalier + fou)"
    incompatible_with = ["assassins"]

    def on_round_start(self, ctx):
        effects = []
        for p in ctx.get_pieces(ctx.player_color):
            if p.piece_type.value == "knight":
                p.tags["transformed"] = "unicorn"
                effects.append({"type": "transform", "piece_id": p.piece_id, "visual": "unicorn"})
        return effects

    def modify_moves(self, piece, moves, ctx):
        if piece.color.value != ctx.player_color:
            return moves
        if piece.tags.get("transformed") != "unicorn":
            return moves
        # Add bishop moves
        for dr, dc in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
            for dist in range(1, 8):
                r, c = piece.row + dr * dist, piece.col + dc * dist
                if not (0 <= r <= 7 and 0 <= c <= 7):
                    break
                target = ctx.piece_at(r, c)
                ent = ctx.entity_at(r, c)
                if ent and ent.entity_type in ("duck", "wall"):
                    break
                if target:
                    if target.color.value != piece.color.value:
                        moves.add((r, c))
                    break
                moves.add((r, c))
        return moves


class Satanistes(BaseAugment):
    id = "satanistes"
    name = "Satanistes"
    description = "Vos fous peuvent aussi capturer vers l'avant de 1 ou 2 cases"
    incompatible_with = ["fantomes"]

    def on_round_start(self, ctx):
        effects = []
        for p in ctx.get_pieces(ctx.player_color):
            if p.piece_type.value == "bishop":
                p.tags["transformed"] = "satanist"
                effects.append({"type": "transform", "piece_id": p.piece_id, "visual": "satanist"})
        return effects

    def modify_moves(self, piece, moves, ctx):
        if piece.color.value != ctx.player_color or piece.tags.get("transformed") != "satanist":
            return moves
        direction = 1 if piece.color.value == "white" else -1
        for dist in (1, 2):
            r = piece.row + direction * dist
            if 0 <= r <= 7:
                target = ctx.piece_at(r, piece.col)
                if target and target.color.value != piece.color.value:
                    moves.add((r, piece.col))
                elif target:
                    break  # blocked by friendly
                # Can only go through if path clear for dist=2
                if dist == 2:
                    mid = ctx.piece_at(piece.row + direction, piece.col)
                    if mid:
                        moves.discard((r, piece.col))
        return moves


class ToursDArchers(BaseAugment):
    id = "tours_darchers"
    name = "Tours d'archers"
    description = "Vos tours peuvent aussi capturer en diagonale de 1 ou 2 cases"

    def on_round_start(self, ctx):
        effects = []
        for p in ctx.get_pieces(ctx.player_color):
            if p.piece_type.value == "rook":
                p.tags["transformed"] = "archer_tower"
                effects.append({"type": "transform", "piece_id": p.piece_id, "visual": "archer_tower"})
        return effects

    def modify_moves(self, piece, moves, ctx):
        if piece.color.value != ctx.player_color or piece.tags.get("transformed") != "archer_tower":
            return moves
        for dr, dc in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
            for dist in (1, 2):
                r, c = piece.row + dr * dist, piece.col + dc * dist
                if not (0 <= r <= 7 and 0 <= c <= 7):
                    break
                target = ctx.piece_at(r, c)
                if target:
                    if target.color.value != piece.color.value:
                        moves.add((r, c))
                    break
        return moves


class Fantomes(BaseAugment):
    id = "fantomes"
    name = "Fantômes"
    description = "Vos fous traversent les pièces ennemies et alliées"
    incompatible_with = ["satanistes"]

    def on_round_start(self, ctx):
        effects = []
        for p in ctx.get_pieces(ctx.player_color):
            if p.piece_type.value == "bishop":
                p.tags["transformed"] = "ghost"
                effects.append({"type": "transform", "piece_id": p.piece_id, "visual": "ghost"})
        return effects

    def modify_moves(self, piece, moves, ctx):
        if piece.color.value != ctx.player_color or piece.tags.get("transformed") != "ghost":
            return moves
        # Recalculate bishop moves ignoring blocking
        moves_to_add = set()
        for dr, dc in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
            for dist in range(1, 8):
                r, c = piece.row + dr * dist, piece.col + dc * dist
                if not (0 <= r <= 7 and 0 <= c <= 7):
                    break
                ent = ctx.entity_at(r, c)
                if ent and ent.entity_type in ("duck", "wall"):
                    break
                target = ctx.piece_at(r, c)
                if target:
                    if target.color.value != piece.color.value:
                        moves_to_add.add((r, c))
                    # Ghost passes through — continue
                else:
                    moves_to_add.add((r, c))
        # Replace standard bishop moves with ghost moves
        moves |= moves_to_add
        return moves


class Assassins(BaseAugment):
    id = "assassins"
    name = "Assassins"
    description = "Vos cavaliers peuvent aussi sauter sur la ligne arrière ennemie"
    incompatible_with = ["licorne"]

    def on_round_start(self, ctx):
        effects = []
        for p in ctx.get_pieces(ctx.player_color):
            if p.piece_type.value == "knight":
                p.tags["transformed"] = "assassin"
                effects.append({"type": "transform", "piece_id": p.piece_id, "visual": "assassin"})
        return effects

    def modify_moves(self, piece, moves, ctx):
        if piece.color.value != ctx.player_color or piece.tags.get("transformed") != "assassin":
            return moves
        back_rank = 0 if ctx.player_color == "white" else 7  # enemy back rank is opposite
        enemy_back = 7 if ctx.player_color == "white" else 0
        for c in range(8):
            target = ctx.piece_at(enemy_back, c)
            if target is None:
                moves.add((enemy_back, c))
        return moves


class MaitreEnPassant(BaseAugment):
    id = "maitre_en_passant"
    name = "Maître en passant"
    description = "Vos pions peuvent capturer en passant n'importe quel type de pièce adjacente"

    def modify_moves(self, piece, moves, ctx):
        if piece.color.value != ctx.player_color or piece.piece_type.value != "pawn":
            return moves
        direction = 1 if piece.color.value == "white" else -1
        for dc in (-1, 1):
            c = piece.col + dc
            if not (0 <= c <= 7):
                continue
            adjacent = ctx.piece_at(piece.row, c)
            if adjacent and adjacent.color.value != piece.color.value:
                capture_r = piece.row + direction
                if 0 <= capture_r <= 7 and ctx.piece_at(capture_r, c) is None:
                    moves.add((capture_r, c))
        return moves

    def on_move_done(self, piece, from_sq, to_sq, captured, ctx):
        if piece.color.value != ctx.player_color or piece.piece_type.value != "pawn":
            return []
        if from_sq[1] != to_sq[1] and captured is None:
            # Diagonal pawn move without capture = en passant style
            adjacent = ctx.piece_at(from_sq[0], to_sq[1])
            if adjacent and adjacent.color.value != piece.color.value:
                adjacent.alive = False
                return [{"type": "capture", "row": adjacent.row, "col": adjacent.col,
                         "piece_type": adjacent.piece_type.value, "color": adjacent.color.value}]
        return []


# ── Special Rules ────────────────────────────────────────────────────────────

class RoiDeLaColline(BaseAugment):
    id = "roi_de_la_colline"
    name = "Roi de la colline"
    description = "Gagnez si votre roi atteint la dernière rangée adverse"

    def check_win(self, ctx):
        target_row = 7 if ctx.player_color == "white" else 0
        for p in ctx.get_pieces(ctx.player_color):
            if p.piece_type.value == "king" and p.row == target_row:
                return ctx.player_color
        return None


class AscensionEnPassant(BaseAugment):
    id = "ascension_en_passant"
    name = "Ascension en passant"
    description = "Si votre pion capture en passant, il se transforme en dame"

    def on_move_done(self, piece, from_sq, to_sq, captured, ctx):
        if piece.color.value != ctx.player_color or piece.piece_type.value != "pawn":
            return []
        # En passant: diagonal move, captured piece was on different row
        if from_sq[1] != to_sq[1] and captured is not None:
            if captured.row != to_sq[0]:  # EP capture — captured pawn was not on landing square
                from app.logic.board import PieceType
                piece.piece_type = PieceType.QUEEN
                piece.tags["promoted_by_ep"] = True
                return [{"type": "promote", "piece_id": piece.piece_id, "to": "queen",
                         "row": to_sq[0], "col": to_sq[1]}]
        return []


class PouvoirAuPeuple(BaseAugment):
    id = "pouvoir_au_peuple"
    name = "Pouvoir au peuple"
    description = "Vos pions peuvent promouvoir en roi (multi-roi : tous doivent être capturés)"

    # This augment is tracked via a tag; the handler checks it for promotion choices
    def on_round_start(self, ctx):
        ctx.match.tags[f"multi_king_{ctx.player_color}"] = True
        return []


class BrouillardDeGuerre(BaseAugment):
    id = "brouillard_de_guerre"
    name = "Brouillard de guerre"
    description = "Les 10 premières secondes, l'adversaire ne voit pas vos pièces"

    def on_round_start(self, ctx):
        ctx.match.tags[f"fog_{ctx.player_color}"] = ctx.now + 10.0
        return [{"type": "fog_start", "color": ctx.player_color, "duration": 10.0}]

    def modify_visibility(self, state, viewer_color, ctx):
        fog_until = ctx.match.tags.get(f"fog_{ctx.player_color}", 0)
        if ctx.now < fog_until and viewer_color != ctx.player_color:
            # Mark pieces on owner's half as fog-hidden (don't remove — client needs them for moves)
            half_rows = {0, 1, 2, 3} if ctx.player_color == "white" else {4, 5, 6, 7}
            for p in state:
                if p["color"] == ctx.player_color and p["row"] in half_rows:
                    p["fog_hidden"] = True
        return state


class SecondeChance(BaseAugment):
    id = "seconde_chance"
    name = "Seconde chance"
    description = "La 1ère fois que votre roi est capturé, il survit et tue la pièce qui le capture (stun 8s)"

    # No can_be_captured override — we let the capture happen, then revive in on_piece_captured

    def on_piece_captured(self, captured, capturer, ctx):
        if (captured.color.value == ctx.player_color
                and captured.piece_type.value == "king"
                and not captured.tags.get("second_chance_used")):
            # King survives — revive it
            captured.alive = True
            captured.tags["second_chance_used"] = True
            captured.tags["stun_until"] = ctx.now + 8.0
            # Capturer dies
            effects = [
                {"type": "second_chance", "king_id": captured.piece_id,
                 "row": captured.row, "col": captured.col},
                {"type": "stun", "piece_id": captured.piece_id, "duration": 8.0},
            ]
            if capturer:
                capturer.alive = False
                effects.append(
                    {"type": "capture", "row": capturer.row, "col": capturer.col,
                     "piece_type": capturer.piece_type.value, "color": capturer.color.value},
                )
            return effects
        return []


class Micmic(BaseAugment):
    id = "micmic"
    name = "Micmic"
    description = "Un pion piégé : s'il est capturé, la pièce qui le capture est détruite et toutes les pièces ennemies sont stun 5s"

    def on_round_start(self, ctx):
        pawns = [p for p in ctx.get_pieces(ctx.player_color) if p.piece_type.value == "pawn"]
        if pawns:
            trap_pawn = random.choice(pawns)
            trap_pawn.tags["booby_trapped"] = True
            return [{"type": "micmic_mark", "piece_id": trap_pawn.piece_id, "color": ctx.player_color}]
        return []

    def on_piece_captured(self, captured, capturer, ctx):
        if (captured.color.value == ctx.player_color
                and captured.tags.get("booby_trapped") and capturer):
            # Capturer is destroyed
            capturer.alive = False
            effects = [
                {"type": "micmic_explode", "row": captured.row, "col": captured.col},
                {"type": "capture", "row": capturer.row, "col": capturer.col,
                 "piece_type": capturer.piece_type.value, "color": capturer.color.value},
            ]
            # Stun all enemy pieces
            for p in ctx.get_pieces(ctx.opponent_color):
                if p.alive:
                    p.tags["stun_until"] = ctx.now + 5.0
                    effects.append({"type": "stun", "piece_id": p.piece_id, "duration": 5.0})
            return effects
        return []


class Dedoublement(BaseAugment):
    id = "dedoublement"
    name = "Dédoublement de personnalité"
    description = "Quand un pion peut capturer 2 pièces et en capture une, un clone capture l'autre"

    def on_move_done(self, piece, from_sq, to_sq, captured, ctx):
        if piece.color.value != ctx.player_color or piece.piece_type.value != "pawn" or not captured:
            return []
        direction = 1 if piece.color.value == "white" else -1
        # Check if there was another capture possible from the original position
        other_captures = []
        for dc in (-1, 1):
            c = from_sq[1] + dc
            r = from_sq[0] + direction
            if (r, c) == to_sq:
                continue  # this is the move we just did
            if 0 <= r <= 7 and 0 <= c <= 7:
                target = ctx.piece_at(r, c)
                if target and target.color.value != piece.color.value and target.alive:
                    other_captures.append((r, c, target))
        if other_captures:
            r, c, target = other_captures[0]
            target.alive = False
            # Create clone pawn at the capture position
            from app.logic.board import Piece, PieceType, Color
            color_enum = Color.WHITE if ctx.player_color == "white" else Color.BLACK
            clone = Piece(
                piece_id=ctx.board._next_piece_id,
                piece_type=PieceType.PAWN,
                color=color_enum,
                row=r, col=c,
                last_move_time=ctx.now,
            )
            clone.tags["is_clone"] = True
            # Copy relevant tags from original
            for tag in ("transformed", "booby_trapped"):
                if tag in piece.tags:
                    clone.tags[tag] = piece.tags[tag]
            ctx.board._next_piece_id += 1
            ctx.board.pieces.append(clone)
            return [
                {"type": "clone_capture", "clone_row": r, "clone_col": c,
                 "clone_color": ctx.player_color,
                 "captured_row": target.row, "captured_col": target.col,
                 "piece_type": target.piece_type.value, "color": target.color.value},
            ]
        return []


class AuraFarming(BaseAugment):
    id = "aura_farming"
    name = "Aura farming"
    description = "Ne fait rien, mais si vous gagnez la manche, vous aurez des rerolls infinis et l'adversaire n'aura pas d'augment au prochain tour"

    # Effect handled in match management logic, not via hooks


# ── Collect all passive augments ─────────────────────────────────────────────

PASSIVE_AUGMENTS: list[BaseAugment] = [
    ToursEnFolie(), DroitDesFemmes(), GradeDHonneur(), AvantageDuRetard(),
    CarreMagique(), DanseDuSang(), Revanchard(),
    Sprinteurs(), MarcheArriere(), CouronneDeLauriers(), Transition(),
    Licorne(), Satanistes(), ToursDArchers(), Fantomes(), Assassins(), MaitreEnPassant(),
    RoiDeLaColline(), AscensionEnPassant(), PouvoirAuPeuple(),
    BrouillardDeGuerre(), SecondeChance(), Micmic(), Dedoublement(), AuraFarming(),
]
