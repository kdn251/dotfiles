# Painted Sisyphus study

A new illustrated figure based on the original bronze Sisyphus composition.
Generated as an eight-frame transparent sprite sheet with ImageGen; the delivered
layout is two columns by four rows. Preserve sheet.png as the source.

Frames are extracted without retouching, in row-major order. Waybar study A loops
at eight frames per second. B and C retain the preceding vector studies for comparison.
The looping motion remains a draft for visual review; this does not replace the
live status indicator or Telegram asset.

Rebuild frames:

```sh
ffmpeg -y -loop 1 -i sheet.png -vf 'crop=iw/2:ih/4:mod(n\,2)*iw/2:floor(n/2)*ih/4' -frames:v 8 -start_number 0 frame-%d.png
```
