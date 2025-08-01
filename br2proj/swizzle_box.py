#Based on https://github.com/bartlomiejduda/ReverseBox/blob/f95e768749c4b8301bfa02507916db23b0230f17/reversebox/image/swizzling/swizzle_ps2.py#L21
def unswizzle_ps2_palette(palette: bytes | bytearray) -> bytearray:
    converted = bytearray()
    bpp = 4
    stripes = 2
    colors = 8
    blocks = 2
    parts = len(palette) // (bpp*blocks*stripes*colors)
    for part in range(parts):
        for block in range(blocks):
            for stripe in range(stripes):
                for color in range(colors):
                    off = (
                        part * colors * stripes * blocks
                        + block * colors
                        + stripe * stripes * colors
                        + color)*bpp
                    converted+=palette[off:off+bpp]

    assert len(converted)==len(palette)
    return converted