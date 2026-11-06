path = '/home/ps5/PS5-14.10-Jailbreak-Research/probes/index.html'
html = open(path).read()
# Add STG5 spray=100 link after the existing STG5 link
old = '<a href="canvas-uaf/v592.html?stage=5&noretry=1&cb=24">2) STG5 - trigger + spray + post-read (NO pre-read)</a>'
new = old + '\n<a href="canvas-uaf/v592.html?stage=5&spray=100&noretry=1&cb=25">2b) STG5 spray=100 - reduced spray (OOM fix)</a>'
html = html.replace(old, new, 1)
open(path, 'w').write(html)
print('done')
