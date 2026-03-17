from __future__ import annotations

"""All 19 activable augments."""

import time
import random
from app.logic.augments.base import BaseAugment, AugmentContext, BoardEntity


class SexoPermutation(BaseAugment):
    id = "sexo_permutation"
    name = "Sexo-permutation"
    description = "Votre roi et votre dame échangent leurs places"
    is_activable = True
    cooldown = 15.0
    target_type = "none"
    incompatible_with = ["transition"]

    def on_activate(self, ctx, target_row=None, target_col=None):
        king = queen = None
        for p in ctx.get_pieces(ctx.player_color):
            if p.piece_type.value == "king":
                king = p
            elif p.piece_type.value == "queen":
                queen = p
        if not king or not queen:
            return {"ok": False, "reason": "Roi ou dame manquant"}
        kr, kc = king.row, king.col
        qr, qc = queen.row, queen.col
        king.row, king.col = qr, qc
        queen.row, queen.col = kr, kc
        king.last_move_time = ctx.now
        queen.last_move_time = ctx.now
        return {"ok": True, "effects": [
            {"type": "swap", "piece1_id": king.piece_id, "piece2_id": queen.piece_id,
             "p1_row": qr, "p1_col": qc, "p2_row": kr, "p2_col": kc},
        ]}


class DuckChess(BaseAugment):
    id = "duck_chess"
    name = "Duck chess"
    description = "Placez un canard sur une case vide, il bloque déplacements et attaques"
    is_activable = True
    cooldown = 7.0
    target_type = "square"

    def on_activate(self, ctx, target_row=None, target_col=None):
        if target_row is None or target_col is None:
            return {"ok": False, "reason": "Cible requise"}
        if ctx.piece_at(target_row, target_col):
            return {"ok": False, "reason": "Case occupée par une pièce"}
        # Remove previous duck from this player
        for e in list(ctx.entities):
            if e.entity_type == "duck" and e.owner_color == ctx.player_color:
                ctx.remove_entity(e)
        duck = BoardEntity("duck", target_row, target_col, ctx.player_color, ctx.now)
        ctx.add_entity(duck)
        return {"ok": True, "effects": [
            {"type": "duck_place", "row": target_row, "col": target_col, "color": ctx.player_color},
        ]}


class Corruption(BaseAugment):
    id = "corruption"
    name = "Corruption"
    description = "Une pièce adverse au hasard devient vôtre (CD max)"
    is_activable = True
    cooldown = 20.0
    target_type = "none"

    def on_activate(self, ctx, target_row=None, target_col=None):
        from app.logic.board import Color, COOLDOWNS
        enemies = [p for p in ctx.get_pieces(ctx.opponent_color) if p.piece_type.value != "king"]
        if not enemies:
            return {"ok": False, "reason": "Aucune pièce adverse convertible"}
        target = random.choice(enemies)
        old_color = target.color.value
        target.color = Color.WHITE if ctx.player_color == "white" else Color.BLACK
        target.last_move_time = ctx.now  # max CD
        return {"ok": True, "effects": [
            {"type": "corruption", "piece_id": target.piece_id, "row": target.row, "col": target.col,
             "old_color": old_color, "new_color": ctx.player_color,
             "piece_type": target.piece_type.value},
        ]}


class SniperKing(BaseAugment):
    id = "sniper_king"
    name = "SniperKing"
    description = "Votre roi tire un projectile vers la ligne arrière adverse"
    is_activable = True
    cooldown = 13.0
    target_type = "none"

    def on_activate(self, ctx, target_row=None, target_col=None):
        king = None
        for p in ctx.get_pieces(ctx.player_color):
            if p.piece_type.value == "king":
                king = p
                break
        if not king:
            return {"ok": False, "reason": "Roi introuvable"}
        direction = 1 if ctx.player_color == "white" else -1
        hit_piece = None
        r = king.row + direction
        while 0 <= r <= 7:
            p = ctx.piece_at(r, king.col)
            if p:
                if p.color.value == ctx.player_color:
                    break  # blocked by ally
                hit_piece = p
                break
            r += direction
        effects = [{"type": "sniper_shot", "king_row": king.row, "king_col": king.col,
                     "direction": direction}]
        if hit_piece:
            hit_piece.alive = False
            effects.append({"type": "capture", "row": hit_piece.row, "col": hit_piece.col,
                            "piece_type": hit_piece.piece_type.value, "color": hit_piece.color.value})
        return {"ok": True, "effects": effects}


class GardeDuCorps(BaseAugment):
    id = "garde_du_corps"
    name = "Garde du corps"
    description = "Des pions apparaissent sur les cases libres autour de votre roi"
    is_activable = True
    cooldown = 30.0
    target_type = "none"

    def on_activate(self, ctx, target_row=None, target_col=None):
        from app.logic.board import Piece, PieceType, Color
        king = None
        for p in ctx.get_pieces(ctx.player_color):
            if p.piece_type.value == "king":
                king = p
                break
        if not king:
            return {"ok": False, "reason": "Roi introuvable"}
        color_enum = Color.WHITE if ctx.player_color == "white" else Color.BLACK
        effects = []
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                r, c = king.row + dr, king.col + dc
                if 0 <= r <= 7 and 0 <= c <= 7:
                    if ctx.piece_at(r, c) is None and ctx.entity_at(r, c) is None:
                        pawn = Piece(
                            piece_id=ctx.board._next_piece_id,
                            piece_type=PieceType.PAWN,
                            color=color_enum,
                            row=r, col=c,
                            last_move_time=ctx.now,
                        )
                        pawn.tags["is_guard"] = True
                        ctx.board._next_piece_id += 1
                        ctx.board.pieces.append(pawn)
                        effects.append({"type": "spawn", "piece_type": "pawn", "color": ctx.player_color,
                                        "row": r, "col": c, "piece_id": pawn.piece_id})
        return {"ok": True, "effects": effects}


class FormationTortue(BaseAugment):
    id = "formation_tortue"
    name = "Formation tortue"
    description = "Transforme un pion allié en mur indestructible et immobile"
    is_activable = True
    cooldown = 25.0
    target_type = "ally_piece"

    def on_activate(self, ctx, target_row=None, target_col=None):
        if target_row is None or target_col is None:
            return {"ok": False, "reason": "Cible requise"}
        piece = ctx.piece_at(target_row, target_col)
        if not piece or piece.color.value != ctx.player_color or piece.piece_type.value != "pawn":
            return {"ok": False, "reason": "Pion allié requis"}
        piece.tags["is_wall"] = True
        piece.tags["transformed"] = "wall"
        return {"ok": True, "effects": [
            {"type": "transform", "piece_id": piece.piece_id, "visual": "wall",
             "row": target_row, "col": target_col},
        ]}

    def can_piece_move(self, piece, ctx):
        if piece.tags.get("is_wall"):
            return False
        return True

    def can_be_captured(self, piece, capturer, ctx):
        if piece.tags.get("is_wall") and piece.color.value == ctx.player_color:
            return False
        return True


class BarriereNoire(BaseAugment):
    id = "barriere_noire"
    name = "Barrière noire"
    description = "Rend une pièce invulnérable 5s, mais elle meurt après"
    is_activable = True
    cooldown = 20.0
    target_type = "ally_piece"

    def on_activate(self, ctx, target_row=None, target_col=None):
        if target_row is None or target_col is None:
            return {"ok": False, "reason": "Cible requise"}
        piece = ctx.piece_at(target_row, target_col)
        if not piece or piece.color.value != ctx.player_color:
            return {"ok": False, "reason": "Pièce alliée requise"}
        piece.tags["invulnerable_until"] = ctx.now + 5.0
        piece.tags["die_at"] = ctx.now + 5.0
        return {"ok": True, "effects": [
            {"type": "shield", "piece_id": piece.piece_id, "duration": 5.0,
             "row": target_row, "col": target_col},
        ]}

    def can_be_captured(self, piece, capturer, ctx):
        inv = piece.tags.get("invulnerable_until", 0)
        if inv > ctx.now and piece.color.value == ctx.player_color:
            return False
        return True

    def on_tick(self, ctx):
        effects = []
        for p in ctx.get_pieces(ctx.player_color):
            die_at = p.tags.get("die_at", 0)
            if die_at and ctx.now >= die_at:
                p.alive = False
                p.tags.pop("die_at", None)
                p.tags.pop("invulnerable_until", None)
                effects.append({"type": "capture", "row": p.row, "col": p.col,
                                "piece_type": p.piece_type.value, "color": p.color.value,
                                "reason": "barrier_expired"})
        return effects


class PiqureInsuline(BaseAugment):
    id = "piqure_insuline"
    name = "Piqûre d'insuline"
    description = "Réinitialise le CD d'une pièce alliée"
    is_activable = True
    cooldown = 6.0
    target_type = "ally_piece"

    def on_activate(self, ctx, target_row=None, target_col=None):
        if target_row is None or target_col is None:
            return {"ok": False, "reason": "Cible requise"}
        piece = ctx.piece_at(target_row, target_col)
        if not piece or piece.color.value != ctx.player_color:
            return {"ok": False, "reason": "Pièce alliée requise"}
        piece.last_move_time = 0.0
        return {"ok": True, "effects": [
            {"type": "cd_reset", "piece_id": piece.piece_id, "row": target_row, "col": target_col},
        ]}


class Encouragements(BaseAugment):
    id = "encouragements"
    name = "Encouragements"
    description = "Réduit de 50% le CD de toutes vos pièces pendant 10s"
    is_activable = True
    cooldown = 30.0
    target_type = "none"

    def on_activate(self, ctx, target_row=None, target_col=None):
        ctx.match.tags[f"encouragements_{ctx.player_color}"] = ctx.now + 10.0
        return {"ok": True, "effects": [
            {"type": "encouragements", "color": ctx.player_color, "duration": 10.0},
        ]}

    def modify_cooldown(self, piece, base_cd, ctx):
        if piece.color.value != ctx.player_color:
            return base_cd
        until = ctx.match.tags.get(f"encouragements_{ctx.player_color}", 0)
        if ctx.now < until:
            return base_cd * 0.5
        return base_cd


class Meteore(BaseAugment):
    id = "meteore"
    name = "Météore"
    description = "Un météore s'écrase sur une case après 2s, détruisant toute pièce"
    is_activable = True
    cooldown = 15.0
    target_type = "square"

    def on_activate(self, ctx, target_row=None, target_col=None):
        if target_row is None or target_col is None:
            return {"ok": False, "reason": "Cible requise"}
        ctx.match.tags.setdefault("meteors", []).append({
            "row": target_row, "col": target_col,
            "impact_at": ctx.now + 2.0, "owner": ctx.player_color,
        })
        return {"ok": True, "effects": [
            {"type": "meteor_warning", "row": target_row, "col": target_col, "delay": 2.0},
        ]}

    def on_tick(self, ctx):
        effects = []
        meteors = ctx.match.tags.get("meteors", [])
        remaining = []
        for m in meteors:
            if ctx.now >= m["impact_at"]:
                piece = ctx.piece_at(m["row"], m["col"])
                if piece and piece.alive:
                    piece.alive = False
                    effects.append({"type": "meteor_impact", "row": m["row"], "col": m["col"],
                                    "captured_type": piece.piece_type.value,
                                    "captured_color": piece.color.value})
                else:
                    effects.append({"type": "meteor_impact", "row": m["row"], "col": m["col"]})
            else:
                remaining.append(m)
        ctx.match.tags["meteors"] = remaining
        return effects


class Valkirie(BaseAugment):
    id = "valkirie"
    name = "Valkyrie"
    description = "Votre dame capture toutes les pièces adverses dans un rayon de 1 case"
    is_activable = True
    cooldown = 15.0
    target_type = "none"

    def on_activate(self, ctx, target_row=None, target_col=None):
        queen = None
        for p in ctx.get_pieces(ctx.player_color):
            if p.piece_type.value == "queen":
                queen = p
                break
        if not queen:
            return {"ok": False, "reason": "Dame introuvable"}
        if queen.is_on_cooldown(ctx.now):
            return {"ok": False, "reason": "Dame en cooldown"}
        effects = []
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                r, c = queen.row + dr, queen.col + dc
                if 0 <= r <= 7 and 0 <= c <= 7:
                    target = ctx.piece_at(r, c)
                    if target and target.color.value != ctx.player_color and target.alive:
                        target.alive = False
                        effects.append({"type": "capture", "row": r, "col": c,
                                        "piece_type": target.piece_type.value,
                                        "color": target.color.value})
        queen.last_move_time = ctx.now
        return {"ok": True, "effects": effects}


class PiegeMortel(BaseAugment):
    id = "piege_mortel"
    name = "Piège mortel"
    description = "Placez un piège invisible sur une case vide, détruit la pièce adverse qui s'y pose"
    is_activable = True
    cooldown = 20.0
    target_type = "square"

    def on_activate(self, ctx, target_row=None, target_col=None):
        if target_row is None or target_col is None:
            return {"ok": False, "reason": "Cible requise"}
        if ctx.piece_at(target_row, target_col) or ctx.entity_at(target_row, target_col):
            return {"ok": False, "reason": "Case occupée"}
        trap = BoardEntity("trap", target_row, target_col, ctx.player_color, ctx.now)
        ctx.add_entity(trap)
        return {"ok": True, "effects": [
            {"type": "trap_place", "row": target_row, "col": target_col, "color": ctx.player_color},
        ]}

    def on_move_done(self, piece, from_sq, to_sq, captured, ctx):
        if piece.color.value == ctx.player_color:
            return []
        # Enemy piece landed on our trap
        for e in list(ctx.entities):
            if (e.entity_type == "trap" and e.owner_color == ctx.player_color
                    and e.row == to_sq[0] and e.col == to_sq[1]):
                piece.alive = False
                ctx.remove_entity(e)
                return [
                    {"type": "trap_trigger", "row": to_sq[0], "col": to_sq[1]},
                    {"type": "capture", "row": to_sq[0], "col": to_sq[1],
                     "piece_type": piece.piece_type.value, "color": piece.color.value},
                ]
        return []


class Flashbang(BaseAugment):
    id = "flashbang"
    name = "Flashbang"
    description = "Stun une pièce adverse pendant 3s"
    is_activable = True
    cooldown = 15.0
    target_type = "enemy_piece"

    def on_activate(self, ctx, target_row=None, target_col=None):
        if target_row is None or target_col is None:
            return {"ok": False, "reason": "Cible requise"}
        piece = ctx.piece_at(target_row, target_col)
        if not piece or piece.color.value != ctx.opponent_color:
            return {"ok": False, "reason": "Pièce adverse requise"}
        piece.tags["stun_until"] = ctx.now + 3.0
        return {"ok": True, "effects": [
            {"type": "stun", "piece_id": piece.piece_id, "duration": 3.0,
             "row": target_row, "col": target_col},
        ]}

    def can_piece_move(self, piece, ctx):
        stun = piece.tags.get("stun_until", 0)
        if stun > ctx.now and piece.color.value == ctx.opponent_color:
            return False
        return True


class Amnesie(BaseAugment):
    id = "amnesie"
    name = "Amnésie"
    description = "Toutes les pièces adverses voient leur CD remis au maximum"
    is_activable = True
    cooldown = 35.0
    target_type = "none"

    def on_activate(self, ctx, target_row=None, target_col=None):
        effects = []
        for p in ctx.get_pieces(ctx.opponent_color):
            p.last_move_time = ctx.now
            effects.append({"type": "cd_max", "piece_id": p.piece_id})
        return {"ok": True, "effects": effects}


class Kamikaze(BaseAugment):
    id = "kamikaze"
    name = "Kamikaze"
    description = "Un pion allié s'auto-détruit et capture toutes les pièces adverses adjacentes"
    is_activable = True
    cooldown = 20.0
    target_type = "ally_piece"

    def on_activate(self, ctx, target_row=None, target_col=None):
        if target_row is None or target_col is None:
            return {"ok": False, "reason": "Cible requise"}
        piece = ctx.piece_at(target_row, target_col)
        if not piece or piece.color.value != ctx.player_color or piece.piece_type.value != "pawn":
            return {"ok": False, "reason": "Pion allié requis"}
        piece.alive = False
        effects = [{"type": "kamikaze", "row": target_row, "col": target_col}]
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                r, c = target_row + dr, target_col + dc
                if 0 <= r <= 7 and 0 <= c <= 7:
                    adj = ctx.piece_at(r, c)
                    if adj and adj.color.value != ctx.player_color and adj.alive:
                        adj.alive = False
                        effects.append({"type": "capture", "row": r, "col": c,
                                        "piece_type": adj.piece_type.value, "color": adj.color.value})
        return {"ok": True, "effects": effects}


class Reincarnation(BaseAugment):
    id = "reincarnation"
    name = "Réincarnation"
    description = "Votre roi se téléporte sur une case libre de votre rangée de départ"
    is_activable = True
    cooldown = 18.0
    target_type = "square"

    def on_activate(self, ctx, target_row=None, target_col=None):
        if target_row is None or target_col is None:
            return {"ok": False, "reason": "Cible requise"}
        back_rank = 0 if ctx.player_color == "white" else 7
        if target_row != back_rank:
            return {"ok": False, "reason": "Doit être sur votre rangée de départ"}
        if ctx.piece_at(target_row, target_col):
            return {"ok": False, "reason": "Case occupée"}
        king = None
        for p in ctx.get_pieces(ctx.player_color):
            if p.piece_type.value == "king":
                king = p
                break
        if not king:
            return {"ok": False, "reason": "Roi introuvable"}
        old_r, old_c = king.row, king.col
        king.row = target_row
        king.col = target_col
        king.last_move_time = ctx.now
        return {"ok": True, "effects": [
            {"type": "teleport", "piece_id": king.piece_id,
             "from_row": old_r, "from_col": old_c,
             "to_row": target_row, "to_col": target_col},
        ]}


class OmbreJumelle(BaseAugment):
    id = "ombre_jumelle"
    name = "Ombre jumelle"
    description = "Le prochain coup (sauf roi) laisse une copie de la pièce sur la case de départ"
    is_activable = True
    cooldown = 20.0
    target_type = "none"

    def on_activate(self, ctx, target_row=None, target_col=None):
        ctx.match.tags[f"shadow_clone_{ctx.player_color}"] = True
        return {"ok": True, "effects": [
            {"type": "shadow_ready", "color": ctx.player_color},
        ]}

    def on_move_done(self, piece, from_sq, to_sq, captured, ctx):
        key = f"shadow_clone_{ctx.player_color}"
        if not ctx.match.tags.get(key):
            return []
        if piece.color.value != ctx.player_color or piece.piece_type.value == "king":
            return []
        ctx.match.tags[key] = False
        from app.logic.board import Piece, Color
        color_enum = Color.WHITE if ctx.player_color == "white" else Color.BLACK
        clone = Piece(
            piece_id=ctx.board._next_piece_id,
            piece_type=piece.piece_type,
            color=color_enum,
            row=from_sq[0], col=from_sq[1],
            last_move_time=ctx.now,
        )
        clone.tags["is_clone"] = True
        clone.tags.update({k: v for k, v in piece.tags.items() if k != "is_clone"})
        ctx.board._next_piece_id += 1
        ctx.board.pieces.append(clone)
        return [{"type": "shadow_clone", "piece_type": piece.piece_type.value,
                 "color": ctx.player_color, "row": from_sq[0], "col": from_sq[1],
                 "piece_id": clone.piece_id}]


class BrouilleurCible(BaseAugment):
    id = "brouilleur_cible"
    name = "Brouilleur ciblé"
    description = "Marque une pièce ennemie 8s, son prochain mouvement prend +2s de CD"
    is_activable = True
    cooldown = 16.0
    target_type = "enemy_piece"

    def on_activate(self, ctx, target_row=None, target_col=None):
        if target_row is None or target_col is None:
            return {"ok": False, "reason": "Cible requise"}
        piece = ctx.piece_at(target_row, target_col)
        if not piece or piece.color.value != ctx.opponent_color:
            return {"ok": False, "reason": "Pièce adverse requise"}
        piece.tags["marked_until"] = ctx.now + 8.0
        piece.tags["marked_extra_cd_next"] = 2.0
        return {"ok": True, "effects": [
            {"type": "mark", "piece_id": piece.piece_id, "duration": 8.0,
             "row": target_row, "col": target_col},
        ]}

    def on_move_done(self, piece, from_sq, to_sq, captured, ctx):
        """When a marked enemy piece moves, extend its CD and consume the mark."""
        if piece.color.value != ctx.opponent_color:
            return []
        extra = piece.tags.get("marked_extra_cd_next")
        mark_until = piece.tags.get("marked_until", 0)
        if extra and ctx.now < mark_until:
            # Push last_move_time forward so the effective CD is base_cd + extra
            piece.last_move_time += extra
            piece.tags.pop("marked_extra_cd_next", None)
            piece.tags.pop("marked_until", None)
        return []


class SilenceTactique(BaseAugment):
    id = "silence_tactique"
    name = "Silence tactique"
    description = "5s : l'adversaire ne voit pas les CD et ne peut pas lancer d'activables"
    is_activable = True
    cooldown = 30.0
    target_type = "none"

    def on_activate(self, ctx, target_row=None, target_col=None):
        ctx.match.tags[f"silence_{ctx.opponent_color}"] = ctx.now + 5.0
        return {"ok": True, "effects": [
            {"type": "silence", "target_color": ctx.opponent_color, "duration": 5.0},
        ]}

    def modify_visibility(self, state, viewer_color, ctx):
        silence_until = ctx.match.tags.get(f"silence_{viewer_color}", 0)
        if ctx.now < silence_until:
            for p in state:
                if p["color"] == viewer_color:
                    p["cooldown_remaining"] = -1  # -1 = hidden
        return state


# ── Collect all activable augments ───────────────────────────────────────────

ACTIVABLE_AUGMENTS: list[BaseAugment] = [
    SexoPermutation(), DuckChess(), Corruption(), SniperKing(), GardeDuCorps(),
    FormationTortue(), BarriereNoire(), PiqureInsuline(), Encouragements(), Meteore(),
    Valkirie(), PiegeMortel(), Flashbang(), Amnesie(), Kamikaze(), Reincarnation(),
    OmbreJumelle(), BrouilleurCible(), SilenceTactique(),
]
