#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#pylint:disable=W0301
#  
#  Copyright 2018- William Martinez Bas <metfar@gmail.com>
#  
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#  
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#  
#
#import warnings;
#warnings.filterwarnings("ignore", category=UserWarning);
from dataclasses import dataclass;

try:
    from sumcore.charset import ASC;
except ImportError:
    ASC = ();

@dataclass(frozen=True)
class BorderGlyphs:
    tl: str; t: str; tr: str; l: str; x: str; r: str; bl: str; b: str; br: str; h: str; v: str;

_STYLES = {
    "single": BorderGlyphs("┌","┬","┐","├","┼","┤","└","┴","┘","─","│"),
    "thick": BorderGlyphs("┏","┳","┓","┣","╋","┫","┗","┻","┛","━","┃"),
};

def border_names():
    return ("none", "single", "thick");

def glyphs(name):
    key = str(name or "none").lower();
    if key == "none": return None;
    result = _STYLES.get(key, _STYLES["single"]);
    # The canonical SUM charset owns these glyphs.  Fail loudly only when a
    # charset is present but incomplete; installations without sumcore keep a
    # Unicode fallback so SES remains usable during bootstrap.
    if ASC:
        missing = [ch for ch in vars(result).values() if ch not in ASC];
        if missing: raise RuntimeError("SUM charset is missing border glyphs: " + " ".join(missing));
    return result;
