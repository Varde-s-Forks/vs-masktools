from __future__ import annotations

from functools import partial

from vsexprtools import ExprOp, ExprToken, norm_expr
from vsrgtools.util import wmean_matrix
from vstools import check_variable, core, depth, get_depth, get_peak_value, get_y, iterate, plane, scale_thresh, vs

from vsmasks.morpho import Morpho

from .edge import EdgeDetect, FDoGTCanny, Prewitt

__all__ = [
    'ringing_mask',

    'luma_mask', 'luma_credit_mask'
]


def ringing_mask(
    clip: vs.VideoNode,
    rad: int = 2, brz: float = 0.35,
    thmi: float = 0.315, thma: float = 0.5,
    thlimi: float = 0.195, thlima: float = 0.392,
    credit_mask: vs.VideoNode | EdgeDetect = Prewitt()
) -> vs.VideoNode:
    assert check_variable(clip, ringing_mask)

    thmi, thma, thlimi, thlima = (
        scale_thresh(t, clip) for t in [thmi, thma, thlimi, thlima]
    )

    if isinstance(credit_mask, vs.VideoNode):
        edgemask = depth(credit_mask, get_depth(clip))  # type: ignore
    elif isinstance(credit_mask, EdgeDetect):
        edgemask = credit_mask.edgemask(plane(clip, 0))

    edgemask = plane(edgemask, 0).std.Limiter()

    light = norm_expr(edgemask, f'x {thlimi} - {thma - thmi} / {ExprToken.RangeMax} *')

    shrink = Morpho.dilation(light, rad)
    shrink = shrink.std.Binarize(scale_thresh(brz, clip))
    shrink = Morpho.erosion(shrink, 2)
    shrink = iterate(shrink, partial(core.std.Convolution, matrix=wmean_matrix), 2)

    strong = norm_expr(edgemask, f'x {thmi} - {thlima - thlimi} / {ExprToken.RangeMax} *')
    expand = Morpho.dilation(strong, rad)

    mask = norm_expr([expand, strong, shrink], 'x y z max -')

    return ExprOp.convolution('x', wmean_matrix, premultiply=2, multiply=2, clamp=True)(mask)


def luma_mask(clip: vs.VideoNode, thr_lo: float, thr_hi: float, invert: bool = True) -> vs.VideoNode:
    peak = get_peak_value(clip)

    lo, hi = (peak, 0) if invert else (0, peak)
    inv_pre, inv_post = (peak, '-') if invert else ('', '')

    return norm_expr(
        get_y(clip),
        f'x {thr_lo} < {lo} x {thr_hi} > {hi} {inv_pre} x {thr_lo} - {thr_lo} {thr_hi} - / {peak} * {inv_post} ? ?'
    )


def luma_credit_mask(
    clip: vs.VideoNode, thr: int = 230, edgemask: EdgeDetect = FDoGTCanny(), draft: bool = False
) -> vs.VideoNode:
    clip = get_y(clip)

    edge_mask = edgemask.edgemask(clip)

    credit_mask = norm_expr([edge_mask, clip], f'y {thr} > y 0 ? x min')

    if not draft:
        credit_mask = iterate(credit_mask, core.std.Maximum, 4)
        credit_mask = iterate(credit_mask, core.std.Inflate, 2)

    return credit_mask
