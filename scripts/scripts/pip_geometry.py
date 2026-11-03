"""Logical monitor work-area geometry for application-aligned PiP windows."""
import json
import subprocess


def monitor_size(monitor):
    width,height=monitor['width'],monitor['height']
    if monitor.get('transform',0)%2:width,height=height,width
    return round(width/monitor.get('scale',1)),round(height/monitor.get('scale',1))


def bounds(monitor,gaps,border):
    width,height=monitor_size(monitor)
    left,top,right,bottom=monitor.get('reserved',[0,0,0,0])
    gt,gr,gb,gl=gaps
    return (monitor['x']+left+gl+border,monitor['y']+top+gt+border,
            monitor['x']+width-right-gr-border,monitor['y']+height-bottom-gb-border)


def settings():
    def get(option):
        return json.loads(subprocess.check_output(['hyprctl','-j','getoption',option],text=True,timeout=2))
    raw=get('general:gaps_out')
    gaps=[int(float(n)) for n in raw.get('css',raw.get('custom','12 12 12 12')).split()]
    if len(gaps)==1:gaps*=4
    elif len(gaps)==2:gaps*=2
    elif len(gaps)==3:gaps.append(gaps[1])
    return gaps,get('general:border_size')['int']


def bottom_right(monitor,size,gaps,border):
    x0,y0,x1,y1=bounds(monitor,gaps,border)
    return [round(max(x0,x1-size[0])),round(max(y0,y1-size[1]))]


def align_default(player,monitor,gaps,border):
    """Correct the old launch inset without undoing intentional manual placement."""
    width,height=monitor_size(monitor)
    old=[round(monitor['x']+width-player['size'][0]-13),
         round(monitor['y']+height-player['size'][1]-13)]
    if all(abs(a-b)<=2 for a,b in zip(player['at'],old)):
        return bottom_right(monitor,player['size'],gaps,border)
    return player['at']
