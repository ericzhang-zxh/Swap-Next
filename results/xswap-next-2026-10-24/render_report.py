#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Render the published report from its frozen public spec; no runtime inputs."""
import importlib.util,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
p=ROOT/'.agents/skills/explaining-campaign-results/scripts/build_page.py'
s=importlib.util.spec_from_file_location('report_page',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
for kind in ['table','diff']:
    original=m.BLOCKS[kind]
    def collapsed(block,budget,original=original):
        return '<details><summary>'+m.esc(block['takeaway'])+'</summary>'+original(block,budget)+'</details>'
    m.BLOCKS[kind]=collapsed
page,budget=m.build(json.loads((HERE/'explainer.json').read_text()))
if budget.errors or budget.words>m.MAX_PAGE_WORDS:raise RuntimeError(budget.errors or budget.words)
scene=(HERE/'prefetch-scene.svg').read_text()+'<p class="chart-title">Compressed-object path: the second hypothesis</p>'+(HERE/'decompression-scene.svg').read_text()
page=page.replace('<section id="method">','<div class="card"><p class="chart-title">Locate each change, then compare its before/after mechanism</p>'+scene+'</div><section id="method">')
page=page.replace('</style>','details{max-width:100%;overflow-x:auto}.svg-scroll{overflow-x:auto;padding:0 4px}.svg-scroll svg{min-width:760px}@media(max-width:600px){.tiles{grid-template-columns:repeat(2,minmax(0,1fr))}.verdict{flex-direction:column;align-items:flex-start;font-size:18px}.svg-scroll:before{content:"Swipe to view chart";display:block;font-size:11px;color:var(--muted);margin-bottom:8px}}'+'</style>')
page=page.replace('<svg ','<div class="svg-scroll"><svg ').replace('</svg>','</svg></div>')
(HERE/'explainer.html').write_text(page)
print('Rendered public report:',budget.words,'prose words')
