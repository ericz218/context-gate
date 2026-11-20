"""Sidebar reflows must redraw the chart without requiring a window resize."""
import shutil
import subprocess
import unittest
from console.app import PAGE


class SidebarChartResizeTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is needed for the browser callback check')
    def test_container_resize_redraws_after_settling_and_skips_hidden_chart(self):
        start = PAGE.index('let chartResizeTimer;')
        end = PAGE.index('let lastWorkbench=', start)
        script = r'''
const assert=require('node:assert/strict');
let width=900,draws=0,resize,observed,observer,timerId=0;
const pending=new Map(),lastData={};
const $=id=>id==='chart'?{getBoundingClientRect:()=>({width})}:id;
function renderChart(){draws++;}
function setTimeout(fn){pending.set(++timerId,fn);return timerId;}
function clearTimeout(id){pending.delete(id);}
const window={addEventListener:(name,fn)=>{if(name==='resize')resize=fn;}};
class ResizeObserver{constructor(fn){observer=fn;}observe(el){observed=el;}}
''' + PAGE[start:end] + r'''
assert.equal(observed,'chartwrap');
observer();observer();observer();assert.equal(pending.size,1);
[...pending.values()][0]();pending.clear();assert.equal(draws,1);
width=0;observer();[...pending.values()][0]();pending.clear();assert.equal(draws,1);
width=900;resize();[...pending.values()][0]();assert.equal(draws,2);
'''
        subprocess.run(['node', '-e', script], check=True, capture_output=True, text=True)


if __name__ == '__main__':
    unittest.main()
