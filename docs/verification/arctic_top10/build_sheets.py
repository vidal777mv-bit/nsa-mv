import json, os, re, struct, zlib, unicodedata
import numpy as np

ROOT = r"C:\SpaceApps2026_Hackathon"
OUT = os.path.join(ROOT, "docs", "verification", "arctic_top10")
TERR = os.path.join(ROOT, "site", "data", "terrain")
THUMB = 180
CELL_W = 196
LABEL_H = 76
CELL_H = THUMB + LABEL_H + 6
COLS = 7
GAP = 6

SHORT = {
    "apollo17_taurus_littrow": "A17 TAURUS", "cabeus_b_peak": "CABEUS B", "de_gerlache_rim_2": "DE GERLACHE",
    "gale": "GALE", "haworth": "HAWORTH", "im1_odysseus": "IM1 ODYSSEUS", "im2_athena": "IM2 ATHENA",
    "insight_elysium": "INSIGHT", "jezero": "JEZERO", "malapert_massif": "MALAPERT",
    "mons_mouton_plateau": "MONS MOUTON", "nobile_rim_1": "NOBILE 1", "nobile_rim_2": "NOBILE 2",
    "oxia_planum": "OXIA",
}

# 5x7 bitmap font (uppercase only; lowercase is uppercased)
FONT = {
    "A": ["01110","10001","10001","11111","10001","10001","10001"],
    "B": ["11110","10001","10001","11110","10001","10001","11110"],
    "C": ["01110","10001","10000","10000","10000","10001","01110"],
    "D": ["11100","10010","10001","10001","10001","10010","11100"],
    "E": ["11111","10000","10000","11110","10000","10000","11111"],
    "F": ["11111","10000","10000","11110","10000","10000","10000"],
    "G": ["01110","10001","10000","10111","10001","10001","01111"],
    "H": ["10001","10001","10001","11111","10001","10001","10001"],
    "I": ["01110","00100","00100","00100","00100","00100","01110"],
    "J": ["00111","00010","00010","00010","00010","10010","01100"],
    "K": ["10001","10010","10100","11000","10100","10010","10001"],
    "L": ["10000","10000","10000","10000","10000","10000","11111"],
    "M": ["10001","11011","10101","10101","10001","10001","10001"],
    "N": ["10001","10001","11001","10101","10011","10001","10001"],
    "O": ["01110","10001","10001","10001","10001","10001","01110"],
    "P": ["11110","10001","10001","11110","10000","10000","10000"],
    "Q": ["01110","10001","10001","10001","10101","10010","01101"],
    "R": ["11110","10001","10001","11110","10100","10010","10001"],
    "S": ["01111","10000","10000","01110","00001","00001","11110"],
    "T": ["11111","00100","00100","00100","00100","00100","00100"],
    "U": ["10001","10001","10001","10001","10001","10001","01110"],
    "V": ["10001","10001","10001","10001","10001","01010","00100"],
    "W": ["10001","10001","10001","10101","10101","10101","01010"],
    "X": ["10001","10001","01010","00100","01010","10001","10001"],
    "Y": ["10001","10001","10001","01010","00100","00100","00100"],
    "Z": ["11111","00001","00010","00100","01000","10000","11111"],
    "0": ["01110","10001","10011","10101","11001","10001","01110"],
    "1": ["00100","01100","00100","00100","00100","00100","01110"],
    "2": ["01110","10001","00001","00010","00100","01000","11111"],
    "3": ["11111","00010","00100","00010","00001","10001","01110"],
    "4": ["00010","00110","01010","10010","11111","00010","00010"],
    "5": ["11111","10000","11110","00001","00001","10001","01110"],
    "6": ["00110","01000","10000","11110","10001","10001","01110"],
    "7": ["11111","00001","00010","00100","01000","01000","01000"],
    "8": ["01110","10001","10001","01110","10001","10001","01110"],
    "9": ["01110","10001","10001","01111","00001","00010","01100"],
    " ": ["00000"] * 7,
    ".": ["00000","00000","00000","00000","00000","01100","01100"],
    ",": ["00000","00000","00000","00000","01100","00100","01000"],
    "-": ["00000","00000","00000","11111","00000","00000","00000"],
    "#": ["01010","01010","11111","01010","11111","01010","01010"],
    "'": ["00100","00100","01000","00000","00000","00000","00000"],
    "/": ["00001","00010","00010","00100","01000","01000","10000"],
    "=": ["00000","00000","11111","00000","11111","00000","00000"],
    ":": ["00000","01100","01100","00000","01100","01100","00000"],
    "_": ["00000","00000","00000","00000","00000","00000","11111"],
}


def read_png_gray(path):
    data = open(path, "rb").read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", path
    pos = 8
    idat = b""
    while pos < len(data):
        ln, = struct.unpack(">I", data[pos:pos + 4])
        typ = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w, h, bd, ct, _, _, il = struct.unpack(">IIBBBBB", body)
        elif typ == b"IDAT":
            idat += body
        pos += 12 + ln
    assert bd == 8 and il == 0 and ct in (0, 2, 4, 6), (path, bd, ct, il)
    ch = {0: 1, 2: 3, 4: 2, 6: 4}[ct]
    raw = zlib.decompress(idat)
    stride = w * ch
    out = np.zeros((h, stride), dtype=np.uint8)
    prev = np.zeros(stride, dtype=np.int32)
    p = 0
    for y in range(h):
        f = raw[p]
        line = np.frombuffer(raw[p + 1:p + 1 + stride], dtype=np.uint8).astype(np.int32)
        p += 1 + stride
        cur = np.zeros(stride, dtype=np.int32)
        if f == 0:
            cur = line
        elif f == 2:
            cur = (line + prev) & 255
        elif f == 1:
            cur = line.copy()
            for i in range(ch, stride):
                cur[i] = (line[i] + cur[i - ch]) & 255
        elif f == 3:
            cur = line.copy()
            for i in range(stride):
                left = cur[i - ch] if i >= ch else 0
                cur[i] = (line[i] + (left + prev[i]) // 2) & 255
        elif f == 4:
            cur = line.copy()
            for i in range(stride):
                a = cur[i - ch] if i >= ch else 0
                b = prev[i]
                c = prev[i - ch] if i >= ch else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                cur[i] = (line[i] + pr) & 255
        out[y] = cur
        prev = cur
    arr = out.reshape(h, w, ch).astype(np.float32)
    if ch >= 3:
        arr = arr[:, :, :3].mean(axis=2)
    else:
        arr = arr[:, :, 0]
    return arr.astype(np.uint8)


def resize_nn(a, n):
    h, w = a.shape
    yi = np.minimum((np.arange(n) + 0.5) * h / n, h - 1).astype(int)
    xi = np.minimum((np.arange(n) + 0.5) * w / n, w - 1).astype(int)
    return a[np.ix_(yi, xi)]


def draw_text(img, x, y, text, color, scale=2):
    text = text.upper()
    cx = x
    for ch in text:
        g = FONT.get(ch, FONT[" "])
        for ry, row in enumerate(g):
            for rx, bit in enumerate(row):
                if bit == "1":
                    img[y + ry * scale:y + (ry + 1) * scale, cx + rx * scale:cx + (rx + 1) * scale] = color
        cx += 6 * scale


def write_png(path, rgb):
    h, w, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[y].tobytes() for y in range(h))

    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    open(path, "wb").write(png)


def ascii_clean(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def place_short(name):
    base = ascii_clean(name or "").split(",")[0].strip().upper()
    return base[:15]


def draw_cell(sheet, r0, c0, thumb, border, lines):
    x0 = c0 * (CELL_W + GAP)
    y0 = r0 * (CELL_H + GAP)
    sheet[y0:y0 + CELL_H, x0:x0 + CELL_W] = (34, 34, 34)
    x_img = x0 + (CELL_W - THUMB) // 2
    sheet[y0:y0 + THUMB, x_img:x_img + THUMB] = np.stack([thumb] * 3, axis=2)
    if border is not None:
        b = 3
        sheet[y0:y0 + b, x_img:x_img + THUMB] = border
        sheet[y0 + THUMB - b:y0 + THUMB, x_img:x_img + THUMB] = border
        sheet[y0:y0 + THUMB, x_img:x_img + b] = border
        sheet[y0:y0 + THUMB, x_img + THUMB - b:x_img + THUMB] = border
    for i, (txt, col) in enumerate(lines):
        draw_text(sheet, x0 + 6, y0 + THUMB + 4 + i * 17, txt, col, scale=2)


def main():
    rows = json.load(open(os.path.join(OUT, "_list_stage.json"), encoding="utf-8"))
    bodies = {}
    for s in sorted({r["site"] for r in rows}):
        bodies[s] = json.load(open(os.path.join(TERR, s, "meta.json"), encoding="utf-8"))["body"]

    cache = {}

    def thumb_of(folder):
        if folder not in cache:
            src = read_png_gray(os.path.join(TERR, folder, "hillshade.png"))
            cache[folder] = resize_nn(src, THUMB)
        return cache[folder]

    WHITE = (235, 235, 235)
    YEL = (255, 210, 90)
    RED = (220, 60, 60)
    GRN = (110, 200, 120)

    for body, fname in (("moon", "moon.png"), ("mars", "mars.png")):
        sites = [s for s in sorted(bodies) if bodies[s] == body]
        blocks = []
        for s in sites:
            tw = sorted([r for r in rows if r["site"] == s], key=lambda r: r["rank"])
            blocks.append((s, tw))
        n_cells = sum(1 + len(tw) for _, tw in blocks)
        # each site starts on a new row
        grid_rows = 0
        for _, tw in blocks:
            grid_rows += -(-(1 + len(tw)) // COLS)
        H = grid_rows * (CELL_H + GAP)
        W = COLS * (CELL_W + GAP)
        sheet = np.full((H, W, 3), 20, dtype=np.uint8)
        gr = 0
        for s, tw in blocks:
            cells = [("REF", s)] + [("TW", r) for r in tw]
            for i, (kind, item) in enumerate(cells):
                rr = gr + i // COLS
                cc = i % COLS
                if kind == "REF":
                    thumb = thumb_of(s)
                    lines = [("REF " + SHORT.get(s, s.upper()), YEL), ("SITE HILLSHADE", WHITE),
                             (body.upper(), WHITE), ("", WHITE)]
                    draw_cell(sheet, rr, cc, thumb, None, lines)
                else:
                    r = item
                    thumb = thumb_of(r["analog_id"])
                    border = RED if r.get("greenland_name") else None
                    ice = r["ice_share"]
                    l1 = ("#%d %s" % (r["rank"], SHORT.get(s, s.upper())))[:15]
                    lines = [(l1, YEL),
                             (r["analog_id"].replace("pool__pool_", "POOL ").upper(), WHITE),
                             (place_short(r["analog_place"]), WHITE),
                             ("ICE %.2f" % ice if ice is not None else "ICE NA", GRN)]
                    draw_cell(sheet, rr, cc, thumb, border, lines)
            gr += -(-(1 + len(tw)) // COLS)
        write_png(os.path.join(OUT, fname), sheet)
        print(fname, "cells", n_cells, "sites", len(sites), "size", W, H)


if __name__ == "__main__":
    main()
